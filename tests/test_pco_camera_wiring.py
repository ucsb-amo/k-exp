"""The pco.edge as an auxiliary camera in kexp: its camera-table entry, what
camera_stream hands the waxx stream clients for it, and its Server Dashboard
entry.  Offline: the stream classes are replaced by recorders, nothing is
connected."""
from types import SimpleNamespace

import pytest

from kexp.config.camera_id import cameras
import importlib
cs_mod = importlib.import_module("kexp.control.cameras.camera_stream")   # the package exports the function under this name
from waxx.control.cameras.camera_param_classes import PCOParams


class Recorder:
    def __init__(self, expt, serial, key, **kw):
        self.expt, self.serial, self.key, self.kw = expt, serial, key, kw
        self.label = f"camera_stream:{key}"
        self.ttl = kw.get("ttl")

    def register(self):
        self.expt.camera_streams.append(self)

    def abandon(self):
        pass


@pytest.fixture
def expt(monkeypatch):
    monkeypatch.setattr(cs_mod, "CameraStreamClient", Recorder)
    monkeypatch.setattr(cs_mod, "TriggeredCameraStreamClient", Recorder)
    return SimpleNamespace(camera_params=cameras.andor, setup_camera=True, camera_streams=[],
                           live_od_client=None, ttl=SimpleNamespace(pco_trigger="TTL"))


def test_the_camera_table_entry():
    p = cameras.pco_edge
    assert isinstance(p, PCOParams) and p.key == "pco_edge" and p.camera_type == "pco"
    assert p.pixel_format == "Mono16"
    # inside the Camera Link width cap (beacon CAMERA_LINK_MAX_OUTPUT_WIDTH = 640)
    assert p.resolution[1] <= 640
    assert p.trigger_ttl == ""                      # no trigger line wired (2026-11-15)


def test_free_run_stream_takes_everything_from_the_entry(expt):
    s = cs_mod.camera_stream(expt, cameras.pco_edge, "img_pco")
    p = cameras.pco_edge
    assert s.serial == p.serial_no
    assert s.kw["pixel_format"] == "Mono16" and s.kw["read_saved_defaults"] is False
    assert s.kw["settings"] == {"sensor_roi": p.sensor_roi, "readout_rate": p.readout_rate}
    assert s.kw["exposure_time"] == p.exposure_time and s.kw["gain"] == 0.0


def test_the_call_overrides_the_entry(expt):
    s = cs_mod.camera_stream(expt, cameras.pco_edge, "img_pco", exposure_time=5e-3,
                             settings={"sensor_roi": (960, 1600, 0, 2160, 1, 1)},
                             roi=[0, 0, 100, 100])
    assert s.kw["exposure_time"] == 5e-3 and s.kw["roi"] == [0, 0, 100, 100]
    assert s.kw["settings"] == {"sensor_roi": (960, 1600, 0, 2160, 1, 1),
                                "readout_rate": "slow"}


def test_triggered_needs_a_trigger_line(expt):
    with pytest.raises(ValueError, match="No camera TTL mapping"):
        cs_mod.camera_stream(expt, cameras.pco_edge, "img_pco", mode="triggered")


def test_triggered_stream_on_a_pco_with_a_trigger_line(expt):
    p = PCOParams(serial_number="61000123", trigger_ttl="pco_trigger", key="pco_test")
    s = cs_mod.camera_stream(expt, p, ["img_a", "img_b"], mode="triggered")
    assert s.kw["ttl"] == "TTL" and s.kw["trigger_source"] == "ExposureTrigger"
    assert s.kw["exposure_delay_from_camera"] is False and s.kw["exposure_delay"] == 0.0
    assert s.kw["settings"]["sensor_roi"] == p.sensor_roi


def test_basler_streams_are_given_nothing_new(expt):
    s = cs_mod.camera_stream(expt, cameras.mot_basler, "img_mot")
    assert "settings" not in s.kw and "read_saved_defaults" not in s.kw
    assert s.kw["exposure_time"] is None and s.kw["gain"] is None


def test_the_server_dashboard_entry():
    from kexp.util.dashboard.dashboard_hosts import HOST_AUTOSTART_SERVERS
    from kexp.util.dashboard.server_registry import SERVER_SPECS
    (spec,) = [s for s in SERVER_SPECS if s.id == "pco"]
    assert spec.server_cmd[-2:] == ["-m", "beacon.pco.server_headless"]
    assert spec.hidden_panel and spec.body_factory is None
    assert all("pco" not in ids for ids in HOST_AUTOSTART_SERVERS.values())
