"""Queue phase 2: a kexp experiment's claim, cold and warm, compiled offline.

A real Base experiment (diagnostic cameras on, the APD path so the pickoff
stage is asked to move) is prepared with EVERY network client stubbed and
every claim step recorded, then its run() kernel is compiled the way
artiq_compile does (no core-device connection).

* cold (no WAXX_QUEUE_WARM): the claim runs once, at the end of
  finish_prepare, in the order stage -> SLM -> wavemeter -> camera connects
  -> liveOD INIT_RUN -> announce -> device-state stamp; nothing claim-ish
  happens before it; the kernel compiles.
* warm (WAXX_QUEUE_WARM set, the placeholder queue_gate): prepare() claims
  nothing (only liveOD RESERVE_RUN; the monitor's state-file reconcile is
  skipped); the kernel compiles; the Core hook's GO + run_claim then runs
  the claim once (liveOD START_RUN with the reservation). Every attribute
  the compiled kernel embeds (= what ARTIQ bakes in and writes back) has
  the same value after the claim as before it: the claim sets nothing a
  kernel reads.

Isolation: no socket may leave this machine (a guard makes any non-loopback
connect / sendto raise), the monitor's server client and liveOD client are
recording fakes, the cameras are in-memory streams, the device-state file
goes to pytest's temp dir. Each compile takes ~10 s. Skipped when %db% /
%code% are not set.
"""
import json
import os
import socket
import time
from types import SimpleNamespace

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

EXPT = '''
from artiq.experiment import *
from kexp import Base, cameras
import numpy as np

class ClaimSplitCompile(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self, setup_camera=True, camera_select=cameras.apd,
                      save_data=False, warmup_shots=1)
        self.xvar('t_tof', np.linspace(1.e-3, 2.e-3, 2))
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.diag.mot_2d()
        self.diag.mot_beams()
        self.diag.mot_fluorescence(1.)
        self.diag.gm_fluorescence()
        self.diag.gm_beams()
        self.diag.tweezer_load()
        self.diag.tweezer_evap()
        delay(self.p.t_tof)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''

CLAIM_EVENTS = ("pdxc", "slm", "wavemeter", "cam_connect", "liveod_init", "liveod_start",
                "announce", "stamp")


class _NoDatasets:
    def __getattr__(self, name):
        raise RuntimeError(f"compile test: dataset access ({name})")


class _Frame:
    def __init__(self, seq, rev, shape=(10, 12)):
        self.image = np.zeros(shape, dtype=np.uint8)
        self.seq = seq
        self.settings_rev = rev
        self.settings = {}


class _FakeStream:
    """beacon.camera.stream.CameraStream as a triggered client uses it."""

    def __init__(self, serial):
        self.entry = SimpleNamespace(host="127.0.0.1")
        self.server_id = "camera_server:fake"
        self.camera_id = f"basler:{serial}"
        self._settings = {"exposure_time": 300e-6, "gain": 12.0,
                          "trigger_mode": "Off", "trigger_source": "Line1"}
        self.rev = 1
        self._seq = 0
        self.live = False

    def snap(self, timeout=5.0, policy="restart", require_rev=None):
        self._seq += 1
        return _Frame(self._seq, self.rev)

    def get_settings(self):
        return dict(self._settings), self.rev

    def set(self, **values):
        self.rev += 1
        self._settings.update(values)
        rb = {k: {"value": v, "origin": "applied", "requested": v} for k, v in values.items()}
        return {"readback": rb, "settings_rev": self.rev, "errors": {}}

    def start_live(self):
        self.live = True

    def stop_live(self):
        self.live = False

    def status(self, refresh=True):
        return SimpleNamespace(state="streaming" if self.live else "idle",
                               instance="inst", raw={"seq": self._seq})

    def latest(self, after_seq=None, timeout=2.0, sources=("live",), include_run=False):
        time.sleep(min(timeout, 0.02))
        return None

    def close(self):
        pass


class _FakeLiveOD:
    """LiveODClient as the experiment uses it, recording into ``events``.
    ``reserve`` / ``start``: whether it has the phase-2 requests."""

    def __init__(self, events, reserve=True, start=True):
        self.events = events
        self.server_features = {}
        self.payloads = {}
        if not reserve:
            self.reserve_run = None
        if not start:
            self.start_run = None
        self.released = []

    def supports(self, feature):
        return bool(self.server_features.get(feature))

    def cameras(self):
        return {}

    def _reply(self):
        self.server_features = {"put_data": True, "reserve": True}
        return {"ok": True, "run_id": 4242, "filepath": "C:/nowhere/run.hdf5",
                "run_token": "tok", "features": dict(self.server_features)}

    def init_run(self, payload):
        self.events.append(("liveod_init",))
        self.payloads["init"] = payload
        return self._reply()

    def reserve_run(self, payload, ttl_s=900.0):
        self.events.append(("liveod_reserve",))
        self.payloads["reserve"] = payload
        return {"ok": True, "reservation": "res-1", "features": {"reserve": True},
                "ttl_s": ttl_s, "warnings": []}

    def start_run(self, payload, *, reservation, require_features=(), go_reset_count=None):
        self.events.append(("liveod_start", reservation, tuple(require_features),
                            go_reset_count))
        self.payloads["start"] = payload
        r = self._reply()
        r.update(run_date_str="2026-10-14", run_datetime_str="2026-10-14_18-30-05")
        return r

    def release_reservation(self, reservation):
        self.released.append(reservation)
        return {"ok": True}

    def __getattr__(self, name):            # anything else the run might call
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: None


class _RecordingMonitorClient:
    def __init__(self, events):
        self.events = events

    def announce_run(self, **kw):
        self.events.append(("announce", kw.get("run_id")))
        return {"status": "ok"}

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def no_outbound_sockets(monkeypatch):
    """Any connect / sendto to a non-loopback address raises (beacon UDP on
    50099, a server, the core device): a stub that is missing fails the test
    instead of reaching the lab."""
    def _local(addr):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        return host in ("127.0.0.1", "localhost", "::1")

    real_connect, real_sendto = socket.socket.connect, socket.socket.sendto

    def connect(self, addr):
        if not _local(addr):
            raise AssertionError(f"test tried to connect to {addr}")
        return real_connect(self, addr)

    def sendto(self, data, *args):
        addr = args[-1]
        if not _local(addr):
            raise AssertionError(f"test tried to send to {addr}")
        return real_sendto(self, data, *args)

    def create_connection(addr, *a, **k):
        raise AssertionError(f"test tried to connect to {addr}")

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket, "create_connection", create_connection)


FEEDBACK_EXPT = '''
from artiq.experiment import *
from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
import numpy as np

class FeedbackClaimCompile(EnvExperiment, FeedbackExpt):
    def prepare(self):
        FeedbackExpt.__init__(self, save_data=False)
        self.p.cal_enabled = 1
        self.p.cal_every_n_shots = 2
        self.p.N_pulses = 3
        self.p.N_repeats = 1
        self.xvar('feedback_fractional_initial_offset', np.array([0., 1., 2.]))
        self.finish_prepare(shuffle=False)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''


class _StubScope:
    """Stands in for the Siglent driver."""
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


def _build(monkeypatch, tmp_path, warm, liveod_kw=None, source=None):
    from waxx.base import monitor as wmon
    from waxx.base.expt import Expt
    from waxx.control.cameras import camera_stream_client as csc
    from waxx.control.slm.slm import SLM
    from waxx.util.device_state import queue_gate
    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id
    from kexp.base.base import Base

    events = []
    state = tmp_path / "device_state.json"

    monkeypatch.setattr(wmon, "MonitorClient", lambda *a, **k: _RecordingMonitorClient(events))
    monkeypatch.setattr(kclients, "Monitor", lambda expt, device_state_json_path=None:
                        wmon.Monitor(expt, device_state_json_path=str(state)))
    monkeypatch.setattr(kclients, "APDStageClient", lambda *a, **k: SimpleNamespace(
        set_apd_stage=lambda s=None: events.append(("pdxc", s))))
    monkeypatch.setattr(kclients, "HMRClient", kclients.HMRDummy)
    monkeypatch.setattr(kclients, "BristolAverageReader",
                        lambda *a, **k: SimpleNamespace(get_average=lambda *a, **k: None))
    liveod = _FakeLiveOD(events, **(liveod_kw or {}))
    monkeypatch.setattr(kclients, "LiveODClient", lambda *a, **k: liveod)
    monkeypatch.setattr(SLM, "reinit_if_due", lambda self, **kw: (
        events.append(("slm",)) or {"result": "compile test", "by": kw.get("by")}))

    class _NoWavemeter(wavemeter_id.WavemeterController):
        def __init__(self, *a, **k):
            events.append(("wavemeter",))
            raise RuntimeError("compile test: no wavemeter connection")

    monkeypatch.setattr(wavemeter_id, "WavemeterController", _NoWavemeter)
    # WavemeterController caches one instance per address (class-wide): a
    # fresh cache, or an earlier test's instance is handed back unrecorded
    monkeypatch.setattr(wavemeter_id.WavemeterController, "_instances", {})

    def _resolve(self, directory):
        events.append(("cam_connect", self.key))
        return _FakeStream(self.serial)

    monkeypatch.setattr(csc.CameraStreamClient, "_resolve_and_connect", _resolve)
    monkeypatch.setattr(csc.CameraStreamClient, "_read_server_defaults",
                        lambda self: {"exposure_time": 1e-3, "gain": 0.0, "roi": None})

    real_stamp = Base._stamp_device_state

    def stamp(self):
        events.append(("stamp",))
        return real_stamp(self)

    monkeypatch.setattr(Base, "_stamp_device_state", stamp)

    real_claim = Expt.claim

    def claim(self):
        events.append(("claim",))
        return real_claim(self)

    monkeypatch.setattr(Expt, "claim", claim)

    queue_gate._reset_for_tests()
    if warm:
        monkeypatch.setenv("WAXX_QUEUE_WARM", "warm-token-test")
    else:
        monkeypatch.delenv("WAXX_QUEUE_WARM", raising=False)

    from artiq.master.databases import DeviceDB
    from artiq.master.worker_db import DeviceManager
    from artiq.language.environment import ProcessArgumentManager
    from artiq.tools import file_import, get_experiment

    import waxx.control.misc.oscilloscopes as osc
    monkeypatch.setattr(osc, "SiglentSDS2000X_Base", _StubScope)

    path = tmp_path / f"claim_split_compile_{'warm' if warm else 'cold'}.py"
    path.write_text(source or EXPT)
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(str(path), prefix="compile_test_")
    cls = get_experiment(module)
    exp = cls((device_mgr, _NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return SimpleNamespace(cls=cls, exp=exp, device_mgr=device_mgr, events=events,
                           liveod=liveod, state=state, queue_gate=queue_gate)


def _compile(b):
    # Never call run(): it would compile AND run on the core device. Writeback
    # ON, as the warm Core compiles: the embedded attributes are what it writes back.
    b.events.append(("compile",))
    return b.exp.core.compile(b.cls.run, [b.exp], {}, attribute_writeback=True,
                              print_as_rpc=False)


def _freeze(v, depth=0):
    if isinstance(v, np.ndarray):
        return ("nd", str(v.dtype), v.shape, v.tobytes())
    if isinstance(v, (list, tuple)) and depth < 3:
        return (type(v).__name__, tuple(_freeze(x, depth + 1) for x in v))
    if isinstance(v, (bool, int, float, str, bytes, np.generic)) or v is None:
        return ("v", repr(v))
    return ("obj", id(v))


def _kernel_view(embedding_map):
    """{(object, attribute): frozen value} of every attribute the compiled
    kernel embeds -- exactly what ARTIQ bakes in and writes back."""
    out = {}
    for obj_id, obj, typ in embedding_map.iter_objects():
        for attr in getattr(typ, "attributes", {}):
            if attr.startswith("__"):
                continue
            try:
                val = getattr(obj, attr)
            except Exception:
                continue
            if callable(val) and not isinstance(val, np.ndarray) and not hasattr(val, "__dict__"):
                continue
            out[(f"{type(obj).__name__}#{obj_id}", attr)] = _freeze(val)
    return out


def _claim_events(events):
    return [e for e in events if e[0] in CLAIM_EVENTS]


def _cleanup(b):
    for cs in list(getattr(b.exp, "camera_streams", ())):
        try:
            cs._atexit_cleanup()
        except Exception:
            pass
    b.device_mgr.close_devices()


def _assert_claim_order(events):
    names = [e[0] for e in _claim_events(events)]
    first = {n: names.index(n) for n in set(names)}
    order = ["pdxc", "slm", "wavemeter", "cam_connect"]
    for a, c in zip(order, order[1:]):
        assert first[a] < first[c], names
    start = first.get("liveod_init", first.get("liveod_start"))
    last_cam = max(i for i, n in enumerate(names) if n == "cam_connect")
    assert last_cam < start < first["announce"] < first["stamp"], names


def test_cold_claims_once_at_finish_prepare_and_compiles(monkeypatch, tmp_path,
                                                         no_outbound_sockets):
    b = _build(monkeypatch, tmp_path, warm=False)
    try:
        ev = b.events
        assert [e for e in ev if e[0] == "claim"] == [("claim",)]
        i_claim = ev.index(("claim",))
        assert _claim_events(ev[:i_claim]) == []           # nothing claim-ish before it
        _assert_claim_order(ev)
        assert ("pdxc", True) in ev                         # the APD path: stage in
        assert ("liveod_reserve",) not in ev and not any(e[0] == "liveod_start" for e in ev)
        n_streams = sum(1 for e in ev if e[0] == "cam_connect")
        assert n_streams == len([s for s in b.exp.diag.streams.values()
                                 if hasattr(s, "connect")]) > 0
        assert all(s.live for s in b.exp.diag.streams.values() if hasattr(s, "connect"))
        # the liveOD payload carries the probe frames' shapes, not the provisional one
        shapes = b.liveod.payloads["init"]["datavault_shapes"]
        for s in b.exp.diag.streams.values():
            if hasattr(s, "connect"):
                assert shapes[s.keys[0]]["shape"][1:] == s._frame_shape != (1,)
        assert b.exp.run_info.run_id == 4242
        assert "slm_at_start" in b.exp._extra_file_texts
        assert b.state.exists()                              # cold: reconcile ran
        _compile(b)
        b.exp.claim()                                        # idempotent
        assert [e for e in b.events if e[0] == "claim"] == [("claim",), ("claim",)]
        assert len(_claim_events(b.events)) == len(_claim_events(ev[:len(ev)]))
    finally:
        _cleanup(b)


def test_warm_claims_nothing_before_go_and_the_claim_changes_no_kernel_value(
        monkeypatch, tmp_path, no_outbound_sockets):
    b = _build(monkeypatch, tmp_path, warm=True)
    try:
        qg = b.queue_gate
        assert qg.is_warm() and "WAXX_QUEUE_WARM" not in os.environ   # popped
        assert not any(e[0] == "claim" for e in b.events)
        assert _claim_events(b.events) == []                 # nothing claimed pre-GO
        assert ("liveod_reserve",) in b.events
        assert not b.state.exists()                          # warm: no reconcile write
        assert not any(getattr(s, "live", False) for s in b.exp.camera_streams)
        assert b.exp._reservation == "res-1"

        embedding_map = _compile(b)[0]
        before = _kernel_view(embedding_map)
        assert before                                       # the audit sees something

        # what waxx.util.artiq.core's hook does after the compile
        qg.ensure_go()
        qg.run_claim()
        qg.run_claim()                                       # once only
        ev = b.events
        assert [e for e in ev if e[0] == "claim"] == [("claim",)]
        i_compile = ev.index(("compile",))
        assert _claim_events(ev[:i_compile]) == []
        _assert_claim_order(ev)
        start = [e for e in ev if e[0] == "liveod_start"]
        assert start == [("liveod_start", "res-1", ("reserve",), None)]
        assert ("liveod_init",) not in ev
        assert b.exp.run_info.run_id == 4242
        assert b.exp.run_info.run_datetime_str == "2026-10-14_18-30-05"
        assert b.exp.run_info.run_date_str == "2026-10-14"
        assert all(s.live for s in b.exp.diag.streams.values() if hasattr(s, "connect"))

        after = _kernel_view(embedding_map)
        changed = sorted(k for k in before if after.get(k) != before[k])
        assert changed == [], f"the claim changed kernel-embedded attributes: {changed}"

        _compile(b)                                          # still compiles after it
    finally:
        _cleanup(b)


def test_warm_against_an_old_liveod_falls_back_to_init_run(monkeypatch, tmp_path,
                                                           no_outbound_sockets):
    b = _build(monkeypatch, tmp_path, warm=True,
               liveod_kw={"reserve": False, "start": False})
    try:
        assert b.exp._reservation is None
        _compile(b)
        b.queue_gate.ensure_go()
        b.queue_gate.run_claim()
        assert ("liveod_init",) in b.events
        assert not any(e[0] == "liveod_start" for e in b.events)
        assert b.exp.run_info.run_id == 4242
    finally:
        _cleanup(b)


def test_the_audit_catches_a_claim_that_sets_a_kernel_value(monkeypatch, tmp_path,
                                                            no_outbound_sockets):
    """Negative control: a claim that sets an attribute the kernel reads
    (init_kernel reads _verbosity) is reported by the audit above."""
    from kexp.base.base import Base
    real = Base.claim_after_start

    def bad(self):
        real(self)
        self._verbosity = 7

    monkeypatch.setattr(Base, "claim_after_start", bad)
    b = _build(monkeypatch, tmp_path, warm=True)
    try:
        embedding_map = _compile(b)[0]
        before = _kernel_view(embedding_map)
        b.queue_gate.ensure_go()
        b.queue_gate.run_claim()
        after = _kernel_view(embedding_map)
        changed = sorted(k[1] for k in before if after.get(k) != before[k])
        assert changed == ["_verbosity"]
    finally:
        _cleanup(b)


def test_warm_feedback_run_with_its_sub_scan_and_the_claim_changes_no_kernel_value(
        monkeypatch, tmp_path, no_outbound_sockets):
    """The feedback family (sub-scan on, the heaviest kernel): the same audit."""
    b = _build(monkeypatch, tmp_path, warm=True, source=FEEDBACK_EXPT)
    try:
        assert _claim_events(b.events) == []
        assert b.exp._subscan is not None and b.exp._subscan_enabled
        embedding_map = _compile(b)[0]
        before = _kernel_view(embedding_map)
        b.queue_gate.ensure_go()
        b.queue_gate.run_claim()
        assert ("liveod_start", "res-1", ("reserve",), None) in b.events
        assert b.exp._subscan.enabled                  # this liveOD takes PUT_DATA
        after = _kernel_view(embedding_map)
        changed = sorted(k for k in before if after.get(k) != before[k])
        assert changed == [], f"the claim changed kernel-embedded attributes: {changed}"
    finally:
        _cleanup(b)
