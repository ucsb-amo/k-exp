"""Offline tests for kexp.control.cameras.camera_stream.camera_streams.

No network, no UDP, no servers: the triggered client is the real waxx class,
built through its _stream / _server_defaults test hooks on an in-memory
stream; camera_trigger_ttl is replaced by named stand-ins. The cameras are
the real diagnostic_cameras entries (mot and x share a trigger line).
"""
import importlib
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
SETUP_S = 0.4          # each fake camera's setup time


class Frame:
    def __init__(self, seq, rev, shape=(10, 12)):
        self.image = np.zeros(shape, dtype=np.uint8)
        self.seq = seq
        self.settings_rev = rev


class FakeTrigStream:
    """beacon.camera.stream.CameraStream as a triggered client uses it."""

    def __init__(self):
        self.entry = SimpleNamespace(host="127.0.0.1")
        self.server_id = "camera_server:fake"
        self._settings = {"exposure_time": 300e-6, "gain": 12.0,
                          "trigger_mode": "Off", "trigger_source": "Line1"}
        self.rev = 1
        self._seq = 0
        self.live = False
        self.closed = False

    def snap(self, timeout=5.0, policy="restart", require_rev=None):
        self._seq += 1
        return Frame(self._seq, self.rev)

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


@pytest.fixture
def rig(monkeypatch):
    """Fake streams per serial; ``fail`` serials raise in setup; setup
    threads and timing recorded."""
    rig = SimpleNamespace(streams={}, fail=set(), threads=set(), ttls={})
    real = csc.TriggeredCameraStreamClient

    def make(expt, serial, key, **kw):
        rig.threads.add(threading.current_thread().name)
        time.sleep(SETUP_S)
        if serial in rig.fail:
            raise RuntimeError("camera down (test)")
        s = FakeTrigStream()
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
    """As diagnostic_frame.bind makes them."""
    return [dict(camera=e.camera, key=list(e.frames), mode="triggered", on_error=on_error,
                 exposure_time=e.images[0].exposure_time, gain=e.images[0].gain,
                 crop_to_saved_roi=False, frame_rois=e.frame_rois,
                 frame_settings=e.frame_settings or None)
            for e in diagnostic_cameras.entries()]


def _keep(fe):
    _registered.extend(s for s in fe.camera_streams
                       if isinstance(s, csc.TriggeredCameraStreamClient))


def test_cameras_set_up_in_parallel_and_registered_in_spec_order(rig):
    fe = FakeExpt()
    specs = _specs()
    t0 = time.monotonic()
    out = cs_mod.camera_streams(fe, specs)
    took = time.monotonic() - t0
    _keep(fe)
    assert len(rig.threads) == len(specs) > 1          # one setup thread per camera
    assert took < SETUP_S * len(specs) / 2              # not one after another
    assert all(isinstance(s, csc.TriggeredCameraStreamClient) for s in out)
    assert [s.keys for s in out] == [tuple(sp["key"]) for sp in specs]
    assert fe.camera_streams == out                    # registered in spec order
    for sp in specs:
        for k in sp["key"]:
            assert hasattr(fe.data, k) and hasattr(fe.data, k + "_meta")


def test_shared_trigger_line_streams_become_siblings(rig):
    fe = FakeExpt()
    entries = diagnostic_cameras.entries()
    out = cs_mod.camera_streams(fe, _specs())
    _keep(fe)
    by_key = {e.key: s for e, s in zip(entries, out)}
    assert by_key["mot_basler"]._siblings == [by_key["x_basler"]]
    assert by_key["x_basler"]._siblings == [by_key["mot_basler"]]
    assert by_key["xy_basler"]._siblings == []


def test_failed_camera_gets_a_placeholder_in_its_place(rig, capsys):
    fe = FakeExpt()
    entries = diagnostic_cameras.entries()
    bad = entries[1].camera
    rig.fail.add(str(bad.serial_no))
    out = cs_mod.camera_streams(fe, _specs(on_error="dummy"))
    _keep(fe)
    assert isinstance(out[1], csc.DummyCameraStreamClient)
    assert "camera down (test)" in out[1].reason
    assert all(isinstance(s, csc.TriggeredCameraStreamClient)
               for i, s in enumerate(out) if i != 1)
    assert fe.camera_streams == out
    assert "could not be set up" in capsys.readouterr().out


def test_raise_registers_earlier_and_puts_later_cameras_back(rig):
    fe = FakeExpt()
    entries = diagnostic_cameras.entries()
    rig.fail.add(str(entries[2].camera.serial_no))
    with pytest.raises(RuntimeError, match="camera down"):
        cs_mod.camera_streams(fe, _specs(on_error="raise"))
    _keep(fe)
    assert [s.keys for s in fe.camera_streams] == [tuple(e.frames) for e in entries[:2]]
    for e in entries[3:]:
        s = rig.streams[str(e.camera.serial_no)]
        assert s.closed and not s.live
        assert s._settings["trigger_mode"] == "Off"
    for e in entries[3:]:
        for k in e.frames:
            assert not hasattr(fe.data, k)


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
