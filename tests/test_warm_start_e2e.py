"""Queue phase 2 (warm start), end to end in one process: the REAL parts together.

Real: the run queue (``waxx.util.device_state.run_queue.RunQueue``) with the
test fakes of test_run_queue.py for its processes, spawner and clock; the real
``queue_gate`` whose transport calls ``RunQueue.warm_request`` in-process (what
the monitor server's ``warm`` action does), JSON round-tripped like the wire;
the real liveOD server's request handlers (``LiveODServer`` never started: no
socket, no beacon) with the real ``DataSaver`` rooted in pytest's tmp_path, and
a recording camera-host stand-in; the real ``LiveODClient`` (experiment side
AND the queue's poller, ``run_loop._LiveOD``) whose two transport methods go
to that server's dispatcher, pickled like the wire; a real kexp ``Base``
experiment built the way artiq_run builds it, with the device_db of this tree,
so its core is ``waxx.util.artiq.core.Core`` (armed by the real environment
variable); the real ``Core.run`` up to ``_run_compiled``, which is replaced by
a recorder (nothing ever connects to the core device).

Simulated: only the process boundary. The queue's spawner is the fake of
test_run_queue.py; the test takes the environment it was handed
(WAXX_QUEUE_WARM, WAXX_QUEUE_JOB, WAXX_LAUNCHER, WAXX_OWNER), runs the
experiment in this process with it (prepare on the test thread, run() on a
thread of its own), and "exits" the process by running the atexit handlers
the experiment's own code registered (waxx / kexp ones) and setting the fake
process's exit code -- the queue sees nothing else of it. The lab's other
clients (monitor server, stage, SLM, wavemeter, magnetometer, cameras) are the
stubs of test_claim_split_compiles.py, and no socket may leave this machine
(its ``no_outbound_sockets`` guard).

Each test compiles the kernel once (~10 s). Skipped without %db% / %code%.
"""
import atexit as _atexit_module
import json
import os
import pickle
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import waxx

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

# the waxx test helpers (fakes of the queue, the tmp DataSaver, Qt hygiene)
_WAXX_TESTS = str(Path(waxx.__file__).resolve().parents[1] / "tests")
if _WAXX_TESTS not in sys.path:
    sys.path.append(_WAXX_TESTS)

from test_run_queue import Clock, Journal, Spawner                     # noqa: E402
from live_od_data_fakes import patch_payload_stash, tmp_data_saver      # noqa: E402
import liveod_qt_helpers as qt                                          # noqa: E402
from test_claim_split_compiles import (_FakeStream, _NoDatasets,         # noqa: E402,F401
                                       _RecordingMonitorClient, _StubScope,
                                       no_outbound_sockets)

#: the warm process's own clock is set this far back while it prepares: the
#: file must be named by liveOD's START time, never by the warm process's
WARM_CLOCK_GAP_S = 2 * 3600.0
#: bound on every wait (a bug must fail the test, never hang the suite)
WAIT_S = 120.0
NEW_TAGS = ("RESERVE_RUN", "START_RUN", "RELEASE_RESERVATION")

EXPT = '''
from artiq.experiment import *
from kexp import Base, cameras
import numpy as np
from {helper} import T_TOF

class WarmE2E(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self, setup_camera=True, camera_select=cameras.apd,
                      save_data=True, warmup_shots=1)
        self.xvar('t_tof', np.array(T_TOF))
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.diag.img_2dmot.trigger()
        self.diag.img_tweezer_evap_x.trigger()
        delay(self.p.t_tof)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''


@pytest.fixture(scope="module")
def app():
    return qt.session_app()


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """The queue's folders are the test's own (the k-exp conftest does not set
    them); no launcher variable leaks in from this shell (settings.json sets
    WAXX_OWNER); queue_gate starts and ends forgotten."""
    from waxx.util.device_state import queue_gate
    monkeypatch.setenv("WAXX_RUN_QUEUE_DIR", str(tmp_path / "run_queue_default"))
    monkeypatch.setenv("WAXX_RUN_QUEUE_ROOTS", str(tmp_path))
    for name in ("WAXX_QUEUE_WARM", "WAXX_QUEUE_JOB", "WAXX_LAUNCHER", "WAXX_OWNER"):
        monkeypatch.delenv(name, raising=False)
    queue_gate._reset_for_tests()
    yield
    queue_gate._reset_for_tests()


# ------------------------------------------------------------------ liveOD side

class RecordingHost:
    """liveOD's camera host, recording: a lock is begin_run. Nothing else."""

    def __init__(self):
        self.previews, self.begun, self.ended = [], [], []

    def preview_run(self, camera_key, capture_images, camera_params):
        self.previews.append(camera_key)
        return {"camera_key": camera_key, "refusals": [], "not_carried": {}, "overrides": {}}

    def begin_run(self, token, camera_key, capture_images, camera_params=None,
                  images_shape=None):
        self.begun.append((token, camera_key))
        return SimpleNamespace(camera_key=camera_key, refused={}, persist_on=False,
                               overrides={}, persist_since=None)

    def note_run_id(self, token, run_id):
        pass

    def arm_run(self, *a, **k):
        raise AssertionError("nothing in this test arms a camera")

    def end_run(self, token, reason="END_RUN"):
        self.ended.append((token, reason))
        return SimpleNamespace(overrides={}, problems=[], camera_key="", persist_since=None)

    def poll_cameras(self):
        return {}


def _no_discovery(self, server_id, discovery_timeout=None, **kw):
    """NetClient.__init__ without discovery: an address nothing answers on
    (TEST-NET); the transport below never uses it."""
    self.server_id = server_id
    self.host, self.port = "192.0.2.1", 9


def make_client_class():
    from waxx.util.live_od import live_od_client as loc

    class InProcessLiveODClient(loc.LiveODClient):
        """The real LiveODClient; only its two transport methods are replaced:
        each request is pickled, handed to the server's own dispatcher in
        this process, and the reply pickled back (no ZMQ, no discovery)."""

        def __init__(self, lab, old=False, who="experiment"):
            self._lab, self._old, self._who = lab, old, who
            with mock.patch.object(loc.NetClient, "__init__", _no_discovery), \
                    mock.patch.object(loc, "resolve_scoped_server_id", lambda b: b + ":test"):
                super().__init__(timeout_ms=3000, discovery_timeout=0.1)

        def _send_recv(self, payload, rcvtimeo_ms=None):
            return self._lab.dispatch(payload, old=self._old, who=self._who)

        def _send_once(self, payload, timeout_ms):
            return self._lab.dispatch(payload, old=self._old, who=self._who)

        def put_data(self, specs):
            raise AssertionError("no PUT_DATA in this test (no shot runs)")

        def close(self):
            pass

    return InProcessLiveODClient


# ------------------------------------------------------------------ the queue link

class QueueLink:
    """queue_gate's transport: the monitor server's ``warm`` action, i.e.
    ``RunQueue.warm_request`` in-process, JSON round-tripped. A GO reply is
    checked against queue.json ON DISK at the moment it is handed out."""

    def __init__(self, lab):
        self.lab = lab
        self.sent = []               # (stage, pid) per request
        self.go_on_disk = []         # the job's warm.go as queue.json had it at each GO reply
        self.on_go = None            # called once after the first GO reply (scenario 4)
        self.cut = ""                # teardown: answer abort, so a stuck process exits

    def request(self, obj, timeout=None, attempts=None):
        obj = json.loads(json.dumps(obj))
        assert obj["type"] == "run_queue" and obj["action"] == "warm"
        self.sent.append((obj["stage"], obj["pid"]))
        if self.cut:
            return {"status": "ok", "abort": self.cut}
        reply = json.loads(json.dumps(self.lab.q.warm_request(obj)))
        if reply.get("go"):
            jid = int(str(obj["job"]).split(":")[0])
            with open(os.path.join(self.lab.q.directory, "queue.json"), encoding="utf-8") as f:
                jobs = {j["id"]: j for j in json.load(f)["jobs"]}
            self.go_on_disk.append((jobs[jid].get("warm") or {}).get("go"))
            hook, self.on_go = self.on_go, None
            if hook is not None:
                hook()
        return reply


# ------------------------------------------------------------------ the lab

class Lab:
    """liveOD (handlers only), the run queue, recorders, and the slot job."""

    def __init__(self, tmp_path, monkeypatch, warm_ahead=True, old_liveod=False,
                 expt_old_liveod=False):
        from waxx.util.device_state import run_loop
        from waxx.util.device_state.run_queue import RunQueue
        from waxx.util.live_od import live_od_client as loc
        from waxx.util.live_od.data import run_file
        from waxx.util.live_od.live_od_server import LiveODServer
        from waxx.util.live_od.log import get_log_buffer

        self.tmp = tmp_path
        self.mp = monkeypatch
        self.old_liveod = old_liveod
        # the experiment's client alone talks to a liveOD from before phase 2
        # (liveOD replaced by an older one after the queue's warm launch)
        self.expt_old_liveod = expt_old_liveod
        self.events = []             # (name, ...) in order, across liveOD / experiment / claim
        self.requests = []           # (who, tag) every liveOD request
        self.replies = {}            # tag -> the last reply
        self.compiled_runs = []

        patch_payload_stash(monkeypatch, run_file, [])
        get_log_buffer().clear()
        self.data_dir = tmp_path / "data"
        self.data_dir.mkdir()
        self.saver = tmp_data_saver(self.data_dir)
        self.srv = LiveODServer(server_talk=None, data_saver=self.saver)    # never started
        self.host = RecordingHost()
        self.srv.set_camera_host(self.host)

        self.Client = make_client_class()
        # nothing may build a real (discovering) LiveODClient from here on
        monkeypatch.setattr(loc, "LiveODClient", _refuse("a real LiveODClient"))
        self.poller = run_loop._LiveOD()
        self.poller._client = self.Client(self, old=old_liveod, who="queue")

        self.expts = tmp_path / "expts"
        self.expts.mkdir()
        for name in ("slot", "person"):       # stand-ins: never run, only scheduled
            (self.expts / f"{name}.py").write_text(f'"""{name}."""\nclass {name}: pass\n')
        self.helper = f"e2e_helper_{uuid.uuid4().hex[:8]}"
        (self.expts / f"{self.helper}.py").write_text("T_TOF = [1.e-3, 2.e-3]\n")
        (self.expts / "warm_e2e.py").write_text(EXPT.format(helper=self.helper))

        self.spawner, self.journal = Spawner(), Journal()
        self.clock = Clock(time.time())
        self.priorities, self.monitor_starts = [], []
        self.q = RunQueue(
            str(tmp_path / "queue"), poll=self.poller,
            run_exited=lambda run_id, why: self.poller.run_exited(run_id, why),
            live_od_reset=lambda **kw: self.poller.reset(**kw), fence=lambda: None,
            monitor_state=lambda: 2, server_busy=lambda: "", loops={},
            start_monitor=self.monitor_starts.append, journal=self.journal,
            spawn=self.spawner, adopt=lambda pid, started: None, clock=self.clock,
            poll_every_s=0.0, gap_s=0.0, outcome_wait_s=0.0, roots=[str(tmp_path)],
            client_name="kong", warm_ahead=warm_ahead,
            set_priority=lambda pid, started: self.priorities.append((pid, started)) or True)
        self.link = QueueLink(self)
        self.slot_token = None
        self.procs = []

    # -- liveOD transport

    def dispatch(self, payload, old=False, who="experiment"):
        tag = payload.get("tag")
        self.requests.append((who, tag))
        if old and tag in NEW_TAGS:
            reply = {"ok": False, "error": f"Unknown tag: {tag}"}      # a liveOD before phase 2
        else:
            raw = self.srv._dispatch([pickle.dumps(payload)])
            reply = pickle.loads(pickle.dumps(raw))
        if old and isinstance(reply.get("features"), dict):
            reply["features"].pop("reserve", None)
            reply.pop("reservation", None)
        if tag in ("INIT_RUN", "START_RUN", "RESERVE_RUN", "RELEASE_RESERVATION") \
                and who == "experiment":
            self.events.append((tag, reply.get("ok"), reply.get("run_id")))
        self.replies[tag] = reply
        return reply

    def poll(self):
        return self.srv._handle_poll({"tag": "POLL"})

    def hdf5_files(self):
        out = []
        for root, _, names in os.walk(str(self.data_dir)):
            out += [os.path.join(root, n) for n in names if n.endswith(".hdf5")]
        return sorted(out)

    def run_state(self):
        s = self.srv
        return (s._current_run_id, s._run_token, s._run_in_progress, s._run_state,
                s._reset_requested, dict(s._current_client), s._run_file.filepath,
                self.saver.server_talk.next_id)

    # -- queue helpers

    def submit(self, name, owner="agent", **kw):
        reply = self.q.submit(dict({"path": str(self.expts / f"{name}.py"), "by": "e2e",
                                    "owner": owner}, **kw))
        assert reply["status"] == "ok", reply
        return reply["ids"][0]

    def job(self, jid):
        return self.q.describe({"id": jid})["job"]

    def qj(self, jid):
        return f"{jid}:{self.job(jid)['token']}"

    def tick(self, n=1):
        for _ in range(n):
            self.q.tick()

    def start_slot_run(self, jid, n_shots_expected=3):
        """The slot job's experiment, as liveOD sees it: INIT_RUN (launcher kq,
        its queue_job; a client on another PC) and its first shot."""
        reply = self.dispatch({
            "tag": "INIT_RUN", "save_data": True, "capture_images": False, "camera_key": "",
            "params": {"N_img": 1, "t_tof": 1e-3}, "N_shots_with_repeats": n_shots_expected,
            "expt_class": "slot", "expt_file": "slot", "xvarnames": ["t_tof"],
            "run_date_str": time.strftime("%Y-%m-%d"),
            "run_datetime_str": time.strftime("%Y-%m-%d_%H-%M-%S"),
            "client_pid": 4242, "client_host": "slot-pc", "launcher": "kq",
            "queue_job": self.qj(jid)}, who="slot")
        assert reply["ok"], reply
        self.slot_token = reply["run_token"]
        self.slot_run_id = reply["run_id"]
        shot = self.dispatch({"tag": "SHOT_COMPLETE", "run_token": self.slot_token,
                              "shot_idx": 0, "N_shots_total": n_shots_expected}, who="slot")
        assert shot["ok"], shot
        return reply

    def end_slot_run(self):
        """The slot job's experiment ends its run (END_RUN) and liveOD saves it."""
        reply = self.dispatch({"tag": "END_RUN", "run_token": self.slot_token}, who="slot")
        assert reply.get("ok"), reply
        wait_for(lambda: not self.poll()["run_in_progress"], "the slot run's save")
        return reply

    def close(self):
        self.link.cut = "test teardown"
        for p in self.procs:
            p.teardown()
        try:
            self.srv._run_file.finish_writer()
            self.srv._run_file.writer_done.wait(10)
        except Exception:
            pass


def _refuse(what):
    def refuse(*a, **k):
        raise AssertionError(f"the test built {what}")
    return refuse


def wait_for(cond, what, timeout=WAIT_S, step=0.05):
    t0 = time.monotonic()
    while not cond():
        if time.monotonic() - t0 > timeout:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(step)


# ------------------------------------------------------------------ the experiment process

class SimProcess:
    """One experiment process, played in this one. The environment is exactly
    what the queue's spawner was handed (the four launcher variables); exit =
    the atexit handlers waxx / kexp registered, then the fake process's code."""

    ENV_KEYS = ("WAXX_QUEUE_WARM", "WAXX_QUEUE_JOB", "WAXX_LAUNCHER", "WAXX_OWNER")

    def __init__(self, lab, call_index):
        from waxx.util.device_state import queue_gate
        self.lab = lab
        self.call = lab.spawner.calls[call_index]
        self.proc = lab.spawner.procs[call_index]
        self.qg = queue_gate
        self.atexit_handlers = []
        self.thread = None
        self.result = None           # ("return", value) | ("exit", code) | ("raise", exc)
        self.exited = False
        lab.procs.append(self)
        mp = lab.mp
        for key in self.ENV_KEYS:
            if key in self.call["env"]:
                mp.setenv(key, self.call["env"][key])
            else:
                mp.delenv(key, raising=False)
        # the manifest's roots as a real launch has them: the code tree (%code%,
        # this worktree; read-only stats) and the folder the job's file is in
        mp.setenv("WAXX_RUN_QUEUE_ROOTS", os.pathsep.join([str(lab.tmp), os.environ["code"]]))
        queue_gate._reset_for_tests()
        queue_gate.set_transport(lab.link)
        self.priority_raised = []
        mp.setattr(queue_gate, "_raise_own_priority",
                   lambda: self.priority_raised.append(time.time()) or True)
        real_register = _atexit_module.register

        def register(fn, *args, **kwargs):
            mod = getattr(fn, "__module__", "") or ""
            if mod.split(".")[0] in ("waxx", "kexp", "waxa"):
                self.atexit_handlers.append((fn, args, kwargs))
                return fn
            return real_register(fn, *args, **kwargs)
        mp.setattr(_atexit_module, "register", register)

    def prepare(self, monkeypatch, tmp_path):
        """artiq_run's build + prepare, with this process's clock behind
        (WARM_CLOCK_GAP_S) while it builds: RunInfo stamps the start then."""
        from artiq.language.environment import ProcessArgumentManager
        from artiq.master.databases import DeviceDB
        from artiq.master.worker_db import DeviceManager
        from artiq.tools import file_import, get_experiment
        import waxa.data.run_info as run_info_mod

        _stub_lab_clients(monkeypatch, tmp_path, self.lab)
        behind = SimpleNamespace(time=lambda: time.time() - WARM_CLOCK_GAP_S,
                                 localtime=time.localtime, strftime=time.strftime)
        self.device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
        module = file_import(str(self.lab.expts / "warm_e2e.py"), prefix="e2e_")
        self.cls = get_experiment(module)
        with mock.patch.object(run_info_mod, "time", behind):
            self.exp = self.cls((self.device_mgr, _NoDatasets(), ProcessArgumentManager({}),
                                 {}))
            self.exp.prepare()
        self.warm_stamp = self.exp.run_info.run_datetime_str
        return self.exp

    def _body(self):
        try:
            self.result = ("return", self.exp.run())
        except SystemExit as e:
            self.result = ("exit", e.code)
        except BaseException as e:                      # noqa: BLE001
            self.result = ("raise", e)

    def start_run(self):
        self.thread = threading.Thread(target=self._body, daemon=True, name="e2e-expt-run")
        self.thread.start()

    def join(self, timeout=WAIT_S):
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "the experiment's run() did not finish"
        return self.result

    def exit(self, code=None):
        """The process ends: its atexit handlers (LIFO), then the exit code the
        queue reads."""
        if self.exited:
            return
        self.exited = True
        # artiq_run's finally: the devices close (the core's gated comm included;
        # an error here is the test's to see), then the interpreter's atexit
        self.device_mgr.close_devices()
        for fn, args, kwargs in reversed(self.atexit_handlers):
            try:
                fn(*args, **kwargs)
            except Exception:
                pass
        if code is None:
            kind, value = self.result or ("return", None)
            code = 0 if kind == "return" else (value if kind == "exit" else 1)
        self.proc.code = code

    def teardown(self):
        if self.thread is not None:
            self.thread.join(15)
        for cs in list(getattr(getattr(self, "exp", None), "camera_streams", ()) or ()):
            try:
                cs._atexit_cleanup()
            except Exception:
                pass
        dm = getattr(self, "device_mgr", None)
        if dm is not None:
            try:
                dm.close_devices()
            except Exception:
                pass


def _stub_lab_clients(monkeypatch, tmp_path, lab):
    """test_claim_split_compiles's stubs for every lab client but liveOD (the
    real client, in-process) -- each claim step recorded into lab.events."""
    from waxx.base import monitor as wmon
    from waxx.base.expt import Expt
    from waxx.control.cameras import camera_stream_client as csc
    from waxx.control.slm.slm import SLM
    from waxx.util.artiq import core as wcore
    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id
    import waxx.control.misc.oscilloscopes as osc
    from kexp.base.base import Base

    if getattr(lab, "_stubbed", False):
        return                                  # once per lab (the recorders must not stack)
    lab._stubbed = True
    events = lab.events
    state = tmp_path / "device_state.json"
    lab.state_file = state

    monkeypatch.setattr(wmon, "MonitorClient", lambda *a, **k: _RecordingMonitorClient(events))
    monkeypatch.setattr(kclients, "Monitor", lambda expt, device_state_json_path=None:
                        wmon.Monitor(expt, device_state_json_path=str(state)))
    monkeypatch.setattr(kclients, "APDStageClient", lambda *a, **k: SimpleNamespace(
        set_apd_stage=lambda s=None: events.append(("pdxc", s))))
    monkeypatch.setattr(kclients, "HMRClient", kclients.HMRDummy)
    monkeypatch.setattr(kclients, "BristolAverageReader",
                        lambda *a, **k: SimpleNamespace(get_average=lambda *a, **k: None))
    old = lab.old_liveod or lab.expt_old_liveod
    monkeypatch.setattr(kclients, "LiveODClient",
                        lambda *a, **k: lab.Client(lab, old=old, who="experiment"))
    monkeypatch.setattr(SLM, "reinit_if_due", lambda self, **kw: (
        events.append(("slm",)) or {"result": "e2e test", "by": kw.get("by")}))

    class _NoWavemeter(wavemeter_id.WavemeterController):
        def __init__(self, *a, **k):
            events.append(("wavemeter",))
            raise RuntimeError("e2e test: no wavemeter connection")

    monkeypatch.setattr(wavemeter_id, "WavemeterController", _NoWavemeter)
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

    real_compile = wcore.Core.compile

    def compile_(self, *a, **k):
        events.append(("compile",))
        return real_compile(self, *a, **k)
    monkeypatch.setattr(wcore.Core, "compile", compile_)

    def run_compiled(self, kernel_library, embedding_map, symbolizer, demangler):
        events.append(("run_compiled",))
        lab.compiled_runs.append(kernel_library)
    monkeypatch.setattr(wcore.Core, "_run_compiled", run_compiled)

    monkeypatch.setattr(osc, "SiglentSDS2000X_Base", _StubScope)


CLAIM_STEPS = ("pdxc", "slm", "wavemeter", "cam_connect", "INIT_RUN", "START_RUN", "announce",
               "stamp")


def names(events, keep=None):
    return [e[0] for e in events if keep is None or e[0] in keep]


def assert_claim_order(events):
    n = names(events, CLAIM_STEPS)
    first = {k: n.index(k) for k in set(n)}
    for a, b in zip(("pdxc", "slm", "wavemeter", "cam_connect"),
                    ("slm", "wavemeter", "cam_connect", "START_RUN")):
        if b in first:
            assert first[a] < first[b], n
    start = first.get("START_RUN", first.get("INIT_RUN"))
    last_cam = max(i for i, k in enumerate(n) if k == "cam_connect")
    # the stamp before the announcement (which makes the state untrusted)
    assert last_cam < start < first["stamp"] < first["announce"], n


# ------------------------------------------------------------------ fixtures

@pytest.fixture
def lab(app, tmp_path, monkeypatch, no_outbound_sockets):
    labs = []

    def make(**kw):
        lab_ = Lab(tmp_path, monkeypatch, **kw)
        labs.append(lab_)
        return lab_
    yield make
    for lab_ in labs:
        lab_.close()


def slot_running_and_head_warm(lab):
    """The slot job launched (cold) with its run's first shot in liveOD; the
    warm_e2e job submitted behind it and warm-launched. -> (slot id, warm id)."""
    a = lab.submit("slot")
    lab.tick()
    assert lab.job(a)["state"] == "running"
    lab.start_slot_run(a)
    b = lab.submit("warm_e2e")
    lab.tick()
    assert len(lab.spawner.calls) == 2, "the head job was not warm-launched"
    return a, b


def warm_job_ready(lab, monkeypatch, tmp_path):
    """... and its process prepared (RESERVE), compiled, "ready", waiting for
    GO. -> (slot id, warm id, process)."""
    a, b = slot_running_and_head_warm(lab)
    proc = SimProcess(lab, 1)
    proc.prepare(monkeypatch, tmp_path)
    proc.start_run()
    wait_for(lambda: (lab.q._jobs[b].warm or {}).get("state") == "ready"
             or not proc.thread.is_alive(), "the warm process's ready")
    assert proc.thread.is_alive(), f"the warm process ended before GO: {proc.result}"
    return a, b, proc


def end_slot_job(lab, code=0):
    """The slot job's run ends in liveOD, then its process exits."""
    lab.end_slot_run()
    lab.spawner.procs[0].code = code


def assert_nothing_claimed(lab, proc, files_before, talk_before):
    """No run id used, no file, no announce, no kernel, no claim."""
    ev = names(lab.events)
    assert lab.hdf5_files() == files_before
    assert lab.saver.server_talk.next_id == talk_before
    for step in ("claim", "START_RUN", "INIT_RUN", "announce", "stamp", "run_compiled", "pdxc",
                 "slm", "wavemeter", "cam_connect"):
        assert step not in ev, (step, ev)
    assert proc.exp.run_info.run_id == 0 and lab.compiled_runs == []


# ------------------------------------------------------------------ 1. happy path

def test_1_warm_start_happy_path(lab, monkeypatch, tmp_path):
    from waxx.util.artiq.core import GateNotPassed
    lab = lab()
    a, b = slot_running_and_head_warm(lab)

    # the warm launch: env and the BELOW_NORMAL flag
    call = lab.spawner.calls[1]
    assert call["below_normal"] is True and "below_normal" not in lab.spawner.calls[0]
    env = call["env"]
    assert env["WAXX_QUEUE_JOB"] == lab.qj(b) and env["WAXX_LAUNCHER"] == "kq"
    assert env["WAXX_OWNER"] == "agent" and len(env["WAXX_QUEUE_WARM"]) == 16
    assert "WAXX_QUEUE_WARM" not in lab.spawner.calls[0]["env"]
    assert lab.job(b)["state"] == "queued" and lab.job(b)["warm"]["state"] == "warming"

    # prepare: RESERVE only -- no run id, no file, no camera lock, liveOD's run
    # state unchanged; the device-state file (it always exists on the machine)
    # neither written nor read
    state_file = tmp_path / "device_state.json"
    state_file.write_text("{}")
    state_stat = (state_file.stat().st_mtime_ns, state_file.stat().st_size)
    files0, state0, begun0 = lab.hdf5_files(), lab.run_state(), list(lab.host.begun)
    proc = SimProcess(lab, 1)
    exp = proc.prepare(monkeypatch, tmp_path)
    assert "WAXX_QUEUE_WARM" not in os.environ                       # popped
    assert proc.qg.is_warm() and exp.core.queue_gate_armed
    assert names(lab.events) == ["RESERVE_RUN"], lab.events
    assert lab.replies["RESERVE_RUN"]["ok"] and exp._reservation
    assert lab.hdf5_files() == files0 and lab.run_state() == state0
    assert lab.host.begun == begun0
    assert exp.run_info.run_id == 0
    # (stat, never read: queue_gate's audit hook is process-wide here, and a read
    # by this test would land in the warm process's manifest)
    assert (state_file.stat().st_mtime_ns, state_file.stat().st_size) == state_stat
    poll = lab.poll()
    assert poll["reservation"]["pid"] == os.getpid()
    assert poll["reservation"]["queue_job"] == lab.qj(b)
    assert lab.job(b)["warm"]["py_pid"] == os.getpid()               # its hello reached the queue

    # run(): compile, then "ready" with a manifest, then it waits
    proc.start_run()
    wait_for(lambda: (lab.q._jobs[b].warm or {}).get("state") == "ready"
             or not proc.thread.is_alive(), "the warm process's ready")
    assert proc.thread.is_alive(), proc.result
    raw_manifest = lab.q._jobs[b].warm["manifest"]
    print(f"\n[e2e] manifest: {len(raw_manifest)} files, "
          f"{len(json.dumps(raw_manifest)) / 1024:.0f} KiB as JSON")
    manifest = {os.path.normcase(m[0]) for m in raw_manifest}
    assert os.path.normcase(os.path.join(os.environ["code"], "k-exp", "kexp", "base",
                                         "base.py")) in manifest
    assert os.path.normcase(str(lab.expts / f"{lab.helper}.py")) in manifest
    assert os.path.normcase(str(state_file)) not in manifest
    assert names(lab.events) == ["RESERVE_RUN", "compile"], lab.events
    with pytest.raises(GateNotPassed):
        exp.core.comm.open()                                         # fail-closed before GO

    # waiting: no GO while the slot job runs ...
    lab.tick(3)
    assert lab.job(b)["state"] == "queued" and lab.q._jobs[b].warm.get("go") is None
    # ... nor once its run has ended in liveOD while its PROCESS lives on
    lab.end_slot_run()
    lab.tick(3)
    assert lab.job(a)["state"] == "running"
    assert lab.job(b)["state"] == "queued" and lab.q._jobs[b].warm.get("go") is None
    time.sleep(3 * proc.qg.POLL_S)
    assert proc.thread.is_alive() and names(lab.events) == ["RESERVE_RUN", "compile"]

    # the slot process exits -> one tick -> GO (on disk first) -> claim -> START -> kernel
    files1, talk1 = lab.hdf5_files(), lab.saver.server_talk.next_id
    lab.spawner.procs[0].code = 0
    lab.tick()
    assert lab.job(a)["state"] == "saved", lab.job(a)
    assert lab.job(b)["state"] == "running" and lab.q._jobs[b].warm["go"] is not None
    result = proc.join()
    assert result[0] == "return", result
    assert len(lab.link.go_on_disk) >= 1 and all(g is not None for g in lab.link.go_on_disk)
    py_started = lab.q._jobs[b].warm["py_started"]
    assert lab.priorities == [(os.getpid(), py_started)]
    if sys.platform == "win32":                     # the creation time the queue checks pids by
        from waxx.util.device_state.detached import process_started
        assert py_started is not None and abs(py_started - process_started()) < 1.0
    assert len(proc.priority_raised) == 1

    ev = names(lab.events)
    assert ev.count("claim") == 1 and ev.count("START_RUN") == 1 and "INIT_RUN" not in ev
    assert ev.count("run_compiled") == 1 and len(lab.compiled_runs) == 1
    assert ev.index("compile") < ev.index("claim") < ev.index("START_RUN") \
        < ev.index("run_compiled")
    assert_claim_order(lab.events)
    assert ("pdxc", True) in lab.events                              # the APD path: stage in

    # START: exactly one new file, named by liveOD's START time
    start = lab.replies["START_RUN"]
    assert start["ok"] and start["reservation_known"] is True
    new = [f for f in lab.hdf5_files() if f not in files1]
    assert [os.path.normcase(f) for f in new] == [os.path.normcase(start["filepath"])]
    assert lab.saver.server_talk.next_id == talk1 + 1
    assert start["run_datetime_str"] != proc.warm_stamp
    stamp = time.mktime(time.strptime(start["run_datetime_str"], "%Y-%m-%d_%H-%M-%S"))
    assert abs(stamp - time.time()) < 120
    folder, name = os.path.split(start["filepath"])
    assert os.path.normcase(folder) == os.path.normcase(str(lab.data_dir / start["run_date_str"]))
    assert name.startswith(f"{start['run_id']:07d}_{start['run_datetime_str']}_")
    assert exp.run_info.run_id == start["run_id"] == lab.srv._current_run_id
    assert exp.run_info.run_datetime_str == start["run_datetime_str"]
    assert [k for _, k in lab.host.begun[len(begun0):]] == ["apd"]   # the one lock, at START
    assert lab.poll()["reservation"] is None                         # spent

    # the queue: the job running, its run id from liveOD
    lab.tick(2)
    jb = lab.job(b)
    assert jb["state"] == "running" and jb["run_id"] == start["run_id"]
    assert jb["warm"]["go"]["delivered"] is not None

    # its end (no shots ran -- the kernel was a recorder): END_RUN into the file
    # START made; the file records START's time and the source as imported
    import h5py
    exp.end(str(lab.expts / "warm_e2e.py"), notify=False)
    with h5py.File(start["filepath"], "r") as f:
        assert f["run_info/run_datetime_str"][()].decode() == start["run_datetime_str"]
        assert f.attrs["expt_file"] == (lab.expts / "warm_e2e.py").read_text()
        assert "source_changed_during_run" not in f.attrs
        assert bool(f.attrs["run_complete"])
    assert [os.path.normcase(f) for f in lab.hdf5_files() if f not in files1] == \
        [os.path.normcase(start["filepath"])]
    proc.exit()
    assert proc.proc.code == 0
    lab.tick(2)
    assert lab.job(b)["state"] in ("saved", "done"), lab.job(b)


def test_2b_a_person_hold_while_it_waits(lab, monkeypatch, tmp_path):
    lab = lab()
    a, b, proc = warm_job_ready(lab, monkeypatch, tmp_path)
    files0, talk0 = lab.hdf5_files(), lab.saver.server_talk.next_id
    assert lab.q.hold_request({"reason": "aligning", "by": "jp"})["status"] == "ok"
    lab.tick()
    assert lab.q._jobs[b].warm["state"] == "aborting"
    assert proc.join() == ("exit", 78)
    assert_nothing_claimed(lab, proc, files0, talk0)
    proc.exit()
    lab.tick(2)
    jb = lab.job(b)
    assert jb["state"] == "queued" and jb["warm"] is None
    assert len(lab.spawner.calls) == 2                               # held: no new warm launch
    assert lab.poll()["reservation"] is None
    assert lab.q.release_request({"by": "jp", "owner": "person"})["status"] == "ok"
    lab.tick()
    assert len(lab.spawner.calls) == 3                               # released: re-warmed
    assert lab.spawner.calls[2]["env"]["WAXX_QUEUE_JOB"] == lab.qj(b)
    assert lab.hdf5_files() == files0


# ------------------------------------------------------------------ 2. discard while waiting

def test_2_a_person_submits_ahead_while_it_waits(lab, monkeypatch, tmp_path):
    lab = lab()
    a, b, proc = warm_job_ready(lab, monkeypatch, tmp_path)
    files0, talk0, state0 = lab.hdf5_files(), lab.saver.server_talk.next_id, lab.run_state()
    assert lab.poll()["reservation"]["pid"] == os.getpid()

    c = lab.submit("person", owner="person")                        # ranked ahead of agents
    lab.tick()
    assert lab.q._jobs[b].warm["state"] == "aborting"
    assert "no longer next" in lab.q._jobs[b].warm["why"]
    assert proc.join() == ("exit", 78)                               # stood down at its next poll
    assert_nothing_claimed(lab, proc, files0, talk0)
    assert lab.run_state() == state0                                 # the slot run untouched

    # the process has not exited yet: no re-warm, the reservation is still held
    lab.tick(3)
    assert len(lab.spawner.calls) == 2
    assert lab.q._jobs[b].warm["state"] == "aborting"
    assert lab.poll()["reservation"]["pid"] == os.getpid()

    # it exits: its atexit releases the reservation; the queue drops the record
    proc.exit()
    assert proc.proc.code == 78
    assert lab.poll()["reservation"] is None
    assert ("experiment", "RELEASE_RESERVATION") in lab.requests
    lab.tick()
    jb = lab.job(b)
    assert jb["state"] == "queued" and jb["warm"] is None
    # only now a warm launch -- for the new head, the person's job
    assert len(lab.spawner.calls) == 3
    assert lab.spawner.calls[2]["env"]["WAXX_QUEUE_JOB"] == lab.qj(c)
    assert "run_queue_warm_discard" in lab.journal.kinds
    assert lab.hdf5_files() == files0 and lab.saver.server_talk.next_id == talk0


# ------------------------------------------------------------------ 3. manifest change

def test_3_a_file_in_its_manifest_changes_while_it_waits(lab, monkeypatch, tmp_path):
    from waxx.util.device_state import run_queue as rq
    lab = lab()
    a, b, proc = warm_job_ready(lab, monkeypatch, tmp_path)
    files0, talk0 = lab.hdf5_files(), lab.saver.server_talk.next_id
    token1 = lab.spawner.calls[1]["env"]["WAXX_QUEUE_WARM"]

    helper = lab.expts / f"{lab.helper}.py"
    helper.write_text("T_TOF = [1.e-3, 2.e-3, 3.e-3]\n")              # edited while it waits
    lab.clock.t += rq.WARM_MANIFEST_CHECK_S + 1
    lab.tick()
    w = lab.q._jobs[b].warm
    assert w["state"] == "aborting" and "a file it loaded changed" in w["why"]
    assert lab.helper in w["why"]
    assert proc.join() == ("exit", 78)
    assert_nothing_claimed(lab, proc, files0, talk0)
    lab.tick(2)
    assert len(lab.spawner.calls) == 2                               # not before it has exited

    proc.exit()
    lab.tick()
    assert len(lab.spawner.calls) == 3                               # re-warmed, same job
    env = lab.spawner.calls[2]["env"]
    assert env["WAXX_QUEUE_JOB"] == lab.qj(b) and env["WAXX_QUEUE_WARM"] != token1
    assert lab.job(b)["warm_attempts"] == 2 and lab.job(b)["state"] == "queued"
    assert lab.hdf5_files() == files0 and lab.saver.server_talk.next_id == talk0

    # the new warm process (a fresh process imports the helper afresh) takes the
    # machine with the edited code
    sys.modules.pop(lab.helper, None)
    proc2 = SimProcess(lab, 2)
    exp2 = proc2.prepare(monkeypatch, tmp_path)
    assert list(exp2.xvardims) == [3]
    proc2.start_run()
    wait_for(lambda: (lab.q._jobs[b].warm or {}).get("state") == "ready"
             or not proc2.thread.is_alive(), "the second warm process's ready")
    end_slot_job(lab)
    lab.tick()
    assert proc2.join()[0] == "return"
    start = lab.replies["START_RUN"]
    assert start["ok"] and exp2.run_info.run_id == start["run_id"]
    assert names(lab.events).count("claim") == 1 and names(lab.events).count("run_compiled") == 1
    assert lab.job(b)["state"] == "running"


# ------------------------------------------------------------------ 4. Reset between GO and START

def test_4_a_reset_between_go_and_start_refuses_the_start(lab, monkeypatch, tmp_path):
    from waxx.util.live_od.live_od_client import LiveODStartRefused
    lab = lab()
    a, b, proc = warm_job_ready(lab, monkeypatch, tmp_path)
    # a person presses Reset in liveOD right after the GO is handed out
    lab.link.on_go = lambda: lab.srv.request_reset("person")
    end_slot_job(lab)
    files1, talk1 = lab.hdf5_files(), lab.saver.server_talk.next_id
    lab.tick()
    assert lab.job(b)["state"] == "running"
    kind, err = proc.join()
    assert kind == "raise" and isinstance(err, LiveODStartRefused), (kind, err)
    start = lab.replies["START_RUN"]
    assert start["ok"] is False and start["refused_reason"] == "reset_since_go"
    assert lab.link.go_on_disk[0]["reset_count"] == 0
    # refused before any id: no file, no id, no announce, no kernel
    ev = names(lab.events)
    assert lab.hdf5_files() == files1 and lab.saver.server_talk.next_id == talk1
    assert "announce" not in ev and "stamp" not in ev and "run_compiled" not in ev
    assert "INIT_RUN" not in ev and proc.exp.run_info.run_id == 0
    # (claim_hardware ran before START, by design: stage, SLM, wavemeter, cameras)
    assert ev.index("cam_connect") < ev.index("START_RUN")
    assert lab.poll()["reset_requested"] is True                     # left for a person

    proc.exit()
    assert proc.proc.code == 1
    lab.tick(2)
    jb = lab.job(b)
    assert jb["state"] == "failed" and jb["run_id"] is None, jb
    assert lab.hdf5_files() == files1
    # the person's Reset puts the person hold on: no agent job starts (and so
    # none consumes that Abort) until a person releases it
    assert lab.q.hold.active, lab.q.info().get("person_hold")
    c = lab.submit("person")
    lab.tick(2)
    assert lab.job(c)["state"] == "queued" and len(lab.spawner.calls) == 2


# ------------------------------------------------------------------ 5. cold path unchanged

def test_5_a_cold_queue_launch_is_unchanged(lab, monkeypatch, tmp_path):
    lab = lab(warm_ahead=False)
    c = lab.submit("warm_e2e")
    lab.tick()
    assert len(lab.spawner.calls) == 1 and "WAXX_QUEUE_WARM" not in lab.spawner.calls[0]["env"]
    assert "below_normal" not in lab.spawner.calls[0]
    proc = SimProcess(lab, 0)
    exp = proc.prepare(monkeypatch, tmp_path)
    assert not proc.qg.is_warm() and exp.core.queue_gate_armed is False
    assert type(exp.core.comm).__name__ == "CommKernel"
    ev = names(lab.events)
    assert ev.count("claim") == 1 and "INIT_RUN" in ev and "compile" not in ev
    assert "RESERVE_RUN" not in ev and "START_RUN" not in ev
    assert_claim_order(lab.events)
    init = lab.replies["INIT_RUN"]
    assert init["ok"] and exp.run_info.run_id == init["run_id"] > 0
    # INIT_RUN names the file by the process's own stamp, as today
    assert os.path.basename(init["filepath"]).startswith(
        f"{init['run_id']:07d}_{proc.warm_stamp}_")
    proc.start_run()
    assert proc.join()[0] == "return"
    ev = names(lab.events)
    assert ev.count("claim") == 1 and ev.index("claim") < ev.index("compile") \
        < ev.index("run_compiled")
    assert ev.count("run_compiled") == 1
    assert lab.link.sent == []                                       # no queue_gate request at all
    assert not any(tag in NEW_TAGS for _, tag in lab.requests)
    lab.tick(2)
    jc = lab.job(c)
    assert jc["state"] == "running" and jc["run_id"] == init["run_id"] and jc["warm"] is None


# ------------------------------------------------------------------ 6. an old liveOD

def test_6a_the_queue_never_warms_against_a_liveod_without_reserve(lab, monkeypatch, tmp_path):
    lab = lab(old_liveod=True)
    a = lab.submit("slot")
    lab.tick()
    lab.start_slot_run(a)
    b = lab.submit("warm_e2e")
    lab.tick(3)
    assert lab.poll()["features"]["reserve"] is True                 # (the real server's) ...
    assert "reserve" not in lab.poller()["features"]                 # ... as the old one answers
    assert lab.poller()["n_shots"] == 1
    assert len(lab.spawner.calls) == 1 and lab.job(b)["warm"] is None
    end_slot_job(lab)
    lab.tick()
    assert len(lab.spawner.calls) == 2                               # launched cold, as today
    assert "WAXX_QUEUE_WARM" not in lab.spawner.calls[1]["env"]
    assert "below_normal" not in lab.spawner.calls[1]


def test_6b_a_warm_process_against_an_old_liveod_starts_with_a_restamped_init_run(
        lab, monkeypatch, tmp_path):
    """liveOD replaced by one from before phase 2 after the queue's warm launch:
    RESERVE is an unknown tag, so the claim starts with INIT_RUN, the run's
    time re-stamped first (the file is not named by the warm process's start)."""
    lab = lab(expt_old_liveod=True)
    a, b, proc = warm_job_ready(lab, monkeypatch, tmp_path)
    assert lab.replies["RESERVE_RUN"].get("ok") is False and proc.exp._reservation is None
    end_slot_job(lab)
    files1 = lab.hdf5_files()
    lab.tick()
    assert proc.join()[0] == "return"
    ev = names(lab.events)
    assert "START_RUN" not in ev and ev.count("INIT_RUN") == 1 and ev.count("claim") == 1
    assert [t for w, t in lab.requests if w == "experiment"] == ["RESERVE_RUN", "INIT_RUN"]
    init = lab.replies["INIT_RUN"]
    new = [f for f in lab.hdf5_files() if f not in files1]
    assert [os.path.normcase(f) for f in new] == [os.path.normcase(init["filepath"])]
    stamp_str = os.path.basename(init["filepath"])[8:27]
    assert stamp_str != proc.warm_stamp
    stamp = time.mktime(time.strptime(stamp_str, "%Y-%m-%d_%H-%M-%S"))
    assert abs(stamp - time.time()) < 120
    assert proc.exp.run_info.run_datetime_str == stamp_str
    assert names(lab.events).count("run_compiled") == 1
    lab.tick(2)
    assert lab.job(b)["state"] == "running" and lab.job(b)["run_id"] == init["run_id"]


# ------------------------------------------------------------------ 7. a person's direct run

def test_7_a_persons_direct_run_between_runs_is_waited_for(lab, monkeypatch, tmp_path):
    """After the slot job, a person runs an experiment directly (``ar_direct``,
    no queue): the reservation does not block it, and GO waits for its end."""
    lab = lab()
    a, b, proc = warm_job_ready(lab, monkeypatch, tmp_path)
    end_slot_job(lab)
    person = lab.dispatch({
        "tag": "INIT_RUN", "save_data": True, "capture_images": False, "camera_key": "",
        "params": {"N_img": 1}, "N_shots_with_repeats": 1, "expt_class": "direct",
        "expt_file": "direct", "run_date_str": time.strftime("%Y-%m-%d"),
        "run_datetime_str": time.strftime("%Y-%m-%d_%H-%M-%S"),
        "client_pid": 31337, "client_host": "person-pc", "launcher": ""}, who="person")
    assert person["ok"], person
    assert lab.poll()["reservation"]["pid"] == os.getpid()           # left alone
    lab.tick(3)
    assert lab.job(a)["state"] == "saved"
    assert lab.job(b)["state"] == "queued" and lab.q._jobs[b].warm.get("go") is None
    assert "START_RUN" not in names(lab.events)
    assert lab.dispatch({"tag": "END_RUN", "run_token": person["run_token"]},
                        who="person").get("ok")
    wait_for(lambda: not lab.poll()["run_in_progress"], "the person's run's save")
    lab.tick()
    assert proc.join()[0] == "return"
    start = lab.replies["START_RUN"]
    assert start["ok"] and start["run_id"] == person["run_id"] + 1   # ids in start order
    assert lab.job(b)["state"] == "running"


# ------------------------------------------------------------------ 8. the slot process dies

def test_8_the_slot_process_dies_without_end_run(lab, monkeypatch, tmp_path):
    """The slot job's process dies mid-run (no END_RUN): the queue tells liveOD
    (RUN_EXITED by run id, through the poller's client), the run is closed with
    what it has (its file kept), and the warm job's START goes."""
    lab = lab()
    a, b, proc = warm_job_ready(lab, monkeypatch, tmp_path)
    slot_file = lab.hdf5_files()
    assert len(slot_file) == 1
    lab.spawner.procs[0].code = 1                                    # died; liveOD still has its run
    lab.tick()
    assert ("queue", "RUN_EXITED") in lab.requests
    assert lab.job(a)["state"] in ("failed", "aborted"), lab.job(a)
    wait_for(lambda: (lab.tick() or True) and lab.job(b)["state"] == "running",
             "GO after the slot's run was closed", timeout=30)
    assert proc.join()[0] == "return"
    start = lab.replies["START_RUN"]
    assert start["ok"], start
    assert all(os.path.exists(f) for f in slot_file)                 # the dead run's file kept
    assert names(lab.events).count("claim") == 1

