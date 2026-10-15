"""Offline tests for kexp.control.cameras.camera_stream: camera_streams builds
the streams with no network (queue phase 2: what the kernel sees is fixed
before the compile), connect_camera_streams connects them in the run's claim,
in parallel.

No network, no UDP, no servers: the triggered client is the real waxx class,
built through its _stream / _server_defaults test hooks on an in-memory
stream; camera_trigger_ttl is replaced by named stand-ins. The cameras are
the real diagnostic_cameras entries (mot and x share a trigger line).
"""
import importlib
import json
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from waxx.config.data_vault import DataVault
from waxx.control.cameras import camera_stream_client as csc

from kexp.config.camera_id import diagnostic_cameras
# the module (kexp.control.cameras re-exports a function of the same name)
cs_mod = importlib.import_module("kexp.control.cameras.camera_stream")

DEFAULTS = {"exposure_time": 19e-6, "gain": 0.0, "trigger_mode": "Off",
            "roi": [2, 3, 7, 9]}
SETUP_S = 0.4          # each fake camera's connect time
CROPPED = (6, 5)       # a (10, 12) frame cropped to DEFAULTS' roi


class Frame:
    def __init__(self, seq, rev, shape=(10, 12)):
        self.image = np.zeros(shape, dtype=np.uint8)
        self.seq = seq
        self.settings_rev = rev


class FakeTrigStream:
    """beacon.camera.stream.CameraStream as a triggered client uses it. The
    first call (the connect) takes SETUP_S and fails for a serial in
    ``rig.fail``; every call is counted."""

    def __init__(self, rig, serial):
        self.rig = rig
        self.serial = serial
        self.calls = 0
        self.entry = SimpleNamespace(host="127.0.0.1")
        self.server_id = "camera_server:fake"
        self._settings = {"exposure_time": 300e-6, "gain": 12.0,
                          "trigger_mode": "Off", "trigger_source": "Line1"}
        self.rev = 1
        self._seq = 0
        self.live = False
        self.closed = False

    def _call(self):
        self.calls += 1
        if self.calls == 1:
            self.rig.threads.add(threading.current_thread().name)
            time.sleep(SETUP_S)
            if self.serial in self.rig.fail:
                raise RuntimeError("camera down (test)")

    def snap(self, timeout=5.0, policy="restart", require_rev=None):
        self._call()
        self._seq += 1
        return Frame(self._seq, self.rev)

    def get_settings(self):
        self._call()
        return dict(self._settings), self.rev

    def set(self, **values):
        self._call()
        self.rev += 1
        self._settings.update(values)
        rb = {k: {"value": v, "origin": "applied", "requested": v} for k, v in values.items()}
        return {"readback": rb, "settings_rev": self.rev, "errors": {}}

    def start_live(self):
        self._call()
        self.live = True

    def stop_live(self):
        self.live = False

    def status(self, refresh=True):
        return SimpleNamespace(state="streaming" if self.live else "idle",
                               instance="inst", raw={"seq": self._seq})

    def latest(self, after_seq=None, timeout=2.0, sources=("live",), include_run=False):
        time.sleep(min(timeout, 0.05))
        return None

    def close(self):
        self.closed = True


class FakeExpt:
    def __init__(self):
        self.core = SimpleNamespace(mu_to_seconds=lambda mu: float(mu) * 1e-9)
        self.data = DataVault(expt=self)
        self.xvardims = [2]
        self.scan_xvars = [SimpleNamespace(counter=0)]
        self.camera_streams = []
        self._extra_file_texts = {}
        self.setup_camera = False
        self.camera_params = None
        self.ttl = object()
        self.live_od_client = None
        self._run_started = False


@pytest.fixture
def rig(monkeypatch):
    """Fake streams per serial; ``fail`` serials raise at connect; connect
    threads recorded."""
    rig = SimpleNamespace(streams={}, fail=set(), threads=set(), ttls={})
    real = csc.TriggeredCameraStreamClient

    def make(expt, serial, key, **kw):
        assert kw.get("connect") is False          # camera_streams never connects
        s = FakeTrigStream(rig, serial)
        rig.streams[serial] = s
        return real(expt, serial, key, _stream=s, _server_defaults=DEFAULTS, **kw)

    monkeypatch.setattr(cs_mod, "TriggeredCameraStreamClient", make)
    monkeypatch.setattr(cs_mod, "camera_trigger_ttl",
                        lambda frame, entry: rig.ttls.setdefault(
                            str(entry.trigger_ttl), SimpleNamespace(key=str(entry.trigger_ttl))))
    yield rig
    for s in list(_registered):
        s._atexit_cleanup()
    _registered.clear()


_registered = []


def _specs(on_error="dummy"):
    return [dict(camera=e.camera, key=list(e.frames), mode="triggered", on_error=on_error,
                 exposure_time=e.exposure_time, gain=e.gain, roi=e.roi,
                 frame_settings=e.frame_settings or None)
            for e in diagnostic_cameras.entries()]


def _keep(fe):
    _registered.extend(s for s in fe.camera_streams
                       if isinstance(s, csc.TriggeredCameraStreamClient))


def _container(fe, key):
    return fe.data.__dict__[key]


def test_streams_are_built_without_any_network(rig):
    fe = FakeExpt()
    specs = _specs()
    out = cs_mod.camera_streams(fe, specs)
    _keep(fe)
    assert all(isinstance(s, csc.TriggeredCameraStreamClient) for s in out)
    assert all(s.calls == 0 for s in rig.streams.values())     # nothing touched
    assert rig.threads == set()
    assert not any(s.live for s in out) and all(s._worker is None for s in out)
    assert [s.keys for s in out] == [tuple(sp["key"]) for sp in specs]
    assert fe.camera_streams == out                    # registered in spec order
    for sp in specs:
        for k in sp["key"]:
            dc = _container(fe, k)
            assert dc._per_shot_data_shape == csc.PROVISIONAL_FRAME_SHAPE
            assert hasattr(fe.data, k + "_meta")


def test_connect_in_parallel_activates_and_sets_the_real_shapes(rig):
    fe = FakeExpt()
    specs = _specs()
    out = cs_mod.camera_streams(fe, specs)
    _keep(fe)
    fe.data.init()                  # finish_prepare ran: the claim comes after it
    t0 = time.monotonic()
    res = cs_mod.connect_camera_streams(fe)
    took = time.monotonic() - t0
    assert len(rig.threads) == len(specs) > 1          # one connect thread per camera
    assert took < SETUP_S * len(specs) / 2              # not one after another
    assert [e for _, e in res] == [None] * len(specs)
    assert all(s.live for s in out) and fe.camera_streams == out
    for sp, s in zip(specs, out):
        # the probe frame's shape (cropped to the entry's or the saved roi)
        assert s._frame_shape != csc.PROVISIONAL_FRAME_SHAPE
        if not sp["roi"]:
            assert s._frame_shape == CROPPED
        for k in sp["key"]:
            dc = _container(fe, k)
            assert dc._per_shot_data_shape == s._frame_shape and dc.stream_only
            assert dc._run_data.shape == (2,) + s._frame_shape    # resized after init()
    # a second connect does nothing
    n = {k: s.calls for k, s in rig.streams.items()}
    cs_mod.connect_camera_streams(fe)
    assert {k: s.calls for k, s in rig.streams.items()} == n


def test_shared_trigger_line_streams_become_siblings_before_connect(rig):
    fe = FakeExpt()
    entries = diagnostic_cameras.entries()
    out = cs_mod.camera_streams(fe, _specs())
    _keep(fe)
    by_key = {e.key: s for e, s in zip(entries, out)}
    assert by_key["mot"]._siblings == [by_key["x"]]
    assert by_key["x"]._siblings == [by_key["mot"]]
    assert by_key["xy"]._siblings == []


def test_failed_connect_makes_a_dead_stream_not_a_placeholder_swap(rig, capsys):
    fe = FakeExpt()
    entries = diagnostic_cameras.entries()
    i_bad = [e.key for e in entries].index("mot")
    bad = entries[i_bad]
    rig.fail.add(str(bad.camera.serial_no))
    out = cs_mod.camera_streams(fe, _specs(on_error="dummy"))
    _keep(fe)
    fe.data.init()
    cs_mod.connect_camera_streams(fe)
    dead = out[i_bad]
    # same object, same class (the kernel was compiled against it)
    assert fe.camera_streams[i_bad] is dead
    assert isinstance(dead, csc.TriggeredCameraStreamClient) and not dead.live
    assert "camera down (test)" in dead._dead_reason
    assert all(s.live for i, s in enumerate(out) if i != i_bad)
    assert "could not be set up" in capsys.readouterr().out
    # its containers are the placeholder's: one byte per shot, NaN records
    for k in bad.frames:
        dc = _container(fe, k)
        assert dc._per_shot_data_shape == (1,) and dc._run_data.dtype == np.uint8
        assert not dc.stream_only
        assert np.isnan(np.asarray(_container(fe, k + "_meta")._run_data)).all()
    # its kernel calls are counted, its live sibling still hears the edge
    sib = out[[e.key for e in entries].index("x")]
    n_sib = sib.counts.get("sibling_edges", 0)
    dead.announce_trigger_mu(0, 0)
    assert dead.counts["edges_not_served"] == 1
    assert sib.counts.get("sibling_edges", 0) == n_sib + 1
    assert dead._queue.empty()
    dead.finish()
    rec = json.loads(fe._extra_file_texts[f"camera_stream_{bad.frames[0]}"])
    assert rec["dummy"] and rec["dead"] and rec["edges_not_served"] == 1
    assert "camera down (test)" in rec["reason"]


def test_raise_on_connect_failure_puts_later_cameras_back(rig):
    fe = FakeExpt()
    entries = diagnostic_cameras.entries()
    rig.fail.add(str(entries[2].camera.serial_no))
    out = cs_mod.camera_streams(fe, _specs(on_error="raise"))
    _keep(fe)
    fe.data.init()
    with pytest.raises(RuntimeError, match="camera down"):
        cs_mod.connect_camera_streams(fe)
    assert all(s.live for s in out[:2])
    for i, e in enumerate(entries[2:], start=2):
        assert not out[i].live
        s = rig.streams[str(e.camera.serial_no)]
        if i > 2:
            assert s.closed and not s.live
            assert s._settings["trigger_mode"] == "Off"


def test_containers_cannot_be_resized_once_the_run_started(rig):
    fe = FakeExpt()
    out = cs_mod.camera_streams(fe, _specs())
    _keep(fe)
    fe.data.init()
    fe._run_started = True
    dc = _container(fe, out[0].keys[0])
    with pytest.raises(RuntimeError, match="has started"):
        fe.data.resize_host_container(dc, (3, 3), np.uint16)


def test_run_camera_gets_a_placeholder_without_setup(rig):
    fe = FakeExpt()
    entries = diagnostic_cameras.entries()
    fe.setup_camera = True
    fe.camera_params = entries[0].camera
    out = cs_mod.camera_streams(fe, _specs())
    _keep(fe)
    assert isinstance(out[0], csc.DummyCameraStreamClient)
    assert str(entries[0].camera.serial_no) not in rig.streams


def test_same_camera_twice_in_one_call_is_refused(rig):
    fe = FakeExpt()
    spec = _specs()[0]
    other = dict(spec, key=["img_other"])
    with pytest.raises(ValueError, match="asked for twice"):
        cs_mod.camera_streams(fe, [spec, other])
    assert rig.streams == {} and fe.camera_streams == []
