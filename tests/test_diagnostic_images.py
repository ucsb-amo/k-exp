"""Diagnostic images: kexp's diagnostic_frame (camera_id), its binding to a
run (kexp.control.cameras.diagnostic_images) and the image trigger kernels
compiled into a Base run.

No camera is ever opened: frames are bound with diagnostics off, or with
stand-in stream factories -- the module's camera_streams is replaced through
sys.modules and never called for real. The compile tests build a Base
experiment against the real device db and run ARTIQ's compiler only (no
core-device connection); they are skipped when %db% / %code% are not set and
take ~10 s each.
"""
import importlib
import json
import os
import sys
from types import SimpleNamespace

import pytest

from waxx.control.cameras import camera_stream_client as csc
from waxx.control.cameras.diagnostic_frame import DiagnosticImage
from waxx.control.cameras.exposure_delay import ExposureDelayCell
from waxx.control.cameras.diagnostic_frame import diagnostic_frame as diagnostic_frame_waxx

from kexp.config.camera_id import cameras, diagnostic_cameras, diagnostic_frame

DI_MODULE = "kexp.control.cameras.diagnostic_images"


def _no_streams(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("test opened camera streams")
    monkeypatch.setattr(importlib.import_module(DI_MODULE), "camera_streams", refuse)


def _expt():
    return SimpleNamespace(core=SimpleNamespace(), params=SimpleNamespace(t_mot_load=1.0))


def _ttl(camera):
    return f"ttl:{camera.trigger_ttl}"


def _bound(enabled=False, make_streams=None, expt=None):
    return diagnostic_frame().bind(expt or _expt(), enabled, make_streams=make_streams,
                                   trigger_ttl=_ttl)


# ---- config ---------------------------------------------------------------

def test_the_config_carried_over_unchanged():
    """Each image at the exposure / gain / ROI it ran at when they were set per
    camera (k-exp 67e72978: the camera's, or the image's own exposure / gain);
    offsets as the t_diag_* params; the tweezer pickoff and the x basler's ROI
    (#87302) as on 2026-10-19."""
    d = diagnostic_cameras
    assert [e.key for e in d.entries()] == [
        "basler_2dmot", "xy_basler", "z_basler", "mot_basler", "x_basler",
        "tweezer_pickoff_basler"]
    assert all(e.camera is getattr(cameras, e.key) for e in d.entries())
    assert {e.key: e.frames for e in d.entries()} == {
        "basler_2dmot": ["img_2dmot"],
        "xy_basler": ["img_mot_beams_xy", "img_gm_beams_xy"],
        "z_basler": ["img_mot_beams_z", "img_gm_beams_z"],
        "mot_basler": ["img_mot", "img_gm"],
        "x_basler": ["img_tweezer_load_x", "img_tweezer_evap_x"],
        "tweezer_pickoff_basler": ["img_tweezer_pickoff"]}
    xy, z, mot, x = ([382, 398, 943, 755], [660, 300, 1260, 900], [1668, 1049, 2373, 1767],
                     [636, 366, 872, 662])
    assert {k: (img.exposure_time, img.gain, img.roi) for k, img in d.images().items()} == {
        "img_2dmot": (3.5e-3, 20., [1685, 741, 1959, 1022]),
        "img_mot_beams_xy": (19.e-6, 0., xy),
        "img_gm_beams_xy": (19.e-6, 18., xy),
        "img_mot_beams_z": (19.e-6, 0., z),
        "img_gm_beams_z": (19.e-6, 0., z),
        "img_mot": (300.e-6, 3., mot),
        "img_gm": (3.e-3, 30., mot),
        "img_tweezer_load_x": (50.e-6, 5., x),
        "img_tweezer_evap_x": (300.e-6, 30., x),
        "img_tweezer_pickoff": (2.e-6, 0., [1799, 909, 2787, 1804])}
    assert all(img.given == ("exposure_time", "gain", "roi") for img in d.images().values())
    # what the streams set between frames: the frames at other settings than their camera's first
    assert {e.key: e.frame_settings for e in d.entries()} == {
        "basler_2dmot": {}, "xy_basler": {"img_gm_beams_xy": {"exposure_time": 19.e-6, "gain": 18.}},
        "z_basler": {}, "mot_basler": {"img_gm": {"exposure_time": 3.e-3, "gain": 30.}},
        "x_basler": {"img_tweezer_evap_x": {"exposure_time": 300.e-6, "gain": 30.}},
        "tweezer_pickoff_basler": {}}
    assert {k: (img.t_offset, img.t_stage) for k, img in d.images().items()} == {
        "img_2dmot": (-60.e-3, None),             # t_diag_2dmot_before_push
        "img_mot_beams_xy": (5.e-3, None),        # t_diag_mot_beams_after_on
        "img_gm_beams_xy": (0.25e-3, None),       # t_diag_gm_beams_after_start
        "img_mot_beams_z": (5.e-3, None),
        "img_gm_beams_z": (0.25e-3, None),
        "img_mot": (-150.e-3, "t_mot_load"),      # t_diag_mot_before_end, main's load check
        "img_gm": (-25.e-3, None),                # t_diag_gm_trigger_lead
        "img_tweezer_load_x": (1.e-3, None),      # t_diag_tweezer_after_load
        "img_tweezer_evap_x": (1.e-3, None),      # t_diag_tweezer_after_evap
        "img_tweezer_pickoff": (1.e-3, None)}     # user, 2026-10-19
    assert {k: img.show for k, img in d.images().items()} == {
        "img_2dmot": "image", "img_mot_beams_xy": "counts", "img_gm_beams_xy": "counts",
        "img_mot_beams_z": "counts", "img_gm_beams_z": "counts", "img_mot": "image",
        "img_gm": "image", "img_tweezer_load_x": None, "img_tweezer_evap_x": None,
        "img_tweezer_pickoff": "image"}
    mot = d.entries()[3]
    assert mot.frame_index("img_gm") == 1 and mot.frame_index("img_2dmot") == -1
    assert mot.frame_rois == {"img_mot": [1668, 1049, 2373, 1767], "img_gm": [1668, 1049, 2373, 1767]}


def test_tweezer_pickoff_entry():
    """The tweezer pickoff camera (2026-10-19): on the 2D-MOT basler's trigger
    line, Line2, so the two streams are siblings."""
    cam = diagnostic_cameras.img_tweezer_pickoff.camera
    assert cam.key == "tweezer_pickoff_basler" and cam.serial_no == "40427782"
    assert cam.trigger_ttl == cameras.basler_2dmot.trigger_ttl == "basler_2dmot"
    assert cam.trigger_source == "Line2"


class _Frame(diagnostic_frame_waxx):
    def __init__(self, body, setup=None):
        self.setup()
        if setup:
            setup(self)
        body(self)
        self.cleanup()


def test_names_labels_and_refusals():
    d = diagnostic_cameras
    assert d.img_mot.key == "img_mot" and d.img_mot.camera is cameras.mot_basler
    mot = d.entries()[3]
    assert mot.images == [d.img_mot, d.img_gm]
    assert mot.label == "mot_basler" and d.img_mot_beams_z.label == "MOT beams"

    def ok(f):
        f.img_a_b = f.image(cameras.z_basler, t_offset=1.e-3)
    f = _Frame(ok)
    (cam,) = f.entries()
    assert f.img_a_b.label == "a b" and cam.label == "z_basler" and cam.frames == ["img_a_b"]

    def twice(f):
        f.img_a = f.image(cameras.z_basler)
        f.img_b = f.img_a
    with pytest.raises(ValueError, match="already .img_a"):
        _Frame(twice)

    def taken(f):
        f.images = f.image(cameras.z_basler)
    with pytest.raises(ValueError, match="taken"):
        _Frame(taken)

    def unassigned(f):
        f.image(cameras.z_basler)
    with pytest.raises(ValueError, match="not assigned"):
        _Frame(unassigned)

    def old_camera_line(f):
        f.z = f.camera(cameras.z_basler, exposure_time=19.e-6)
    with pytest.raises(TypeError, match="no longer assigned"):
        _Frame(old_camera_line)

    with pytest.raises(ValueError, match="show"):
        DiagnosticImage(cameras.z_basler, show="table")
    with pytest.raises(TypeError, match="camera-frame entry"):
        DiagnosticImage("40416468")
    for bad in ([0, 0, 10], [5, 0, 5, 10], [-1, 0, 4, 4]):
        with pytest.raises(ValueError, match="roi"):
            DiagnosticImage(cameras.z_basler, roi=bad)


def test_defaults_from_the_camera_entry():
    """What an image does not give: the entry's absorption exposure / gain (z
    basler: 19 us, 24 dB) and the full frame; the frame's default_imaging_type
    picks another set. The shared entry is never changed."""
    before = (cameras.z_basler.exposure_time, cameras.z_basler.gain)

    def body(f):
        f.img_a = f.image(cameras.z_basler)
        f.img_b = f.image(cameras.z_basler, gain=3., roi=[1, 2, 30, 40])
    f = _Frame(body)
    assert (f.img_a.exposure_time, f.img_a.gain, f.img_a.roi, f.img_a.given) == (19.e-6, 24., None, ())
    assert (f.img_b.exposure_time, f.img_b.gain, f.img_b.roi) == (19.e-6, 3., [1, 2, 30, 40])
    assert f.img_b.given == ("gain", "roi")
    assert f.entries()[0].frame_settings == {"img_b": {"exposure_time": 19.e-6, "gain": 3.}}
    assert f.entries()[0].frame_rois == {"img_a": None, "img_b": [1, 2, 30, 40]}

    from waxx.control.cameras.camera_param_classes import img_types

    def fluorescence(f):
        f.default_imaging_type = img_types.FLUORESCENCE
    f = _Frame(lambda f: setattr(f, "img_a", f.image(cameras.z_basler)), setup=fluorescence)
    assert (f.img_a.exposure_time, f.img_a.gain) == (1.e-3, 0.)
    assert (cameras.z_basler.exposure_time, cameras.z_basler.gain) == before


# ---- binding --------------------------------------------------------------

def test_bind_with_diagnostics_off(monkeypatch):
    _no_streams(monkeypatch)
    diag = _bound()
    assert diag is not diagnostic_cameras and not diag.enabled and not diag.active
    for cam in diag.entries():
        assert isinstance(cam.stream, csc.InactiveCameraStream)
        assert cam.stream.keys == tuple(cam.frames)
        for j, img in enumerate(cam.images):
            assert (img.frame, img.j, img.live, img.ttl) == (diag, j, False, _ttl(cam.camera))
    # the config singleton is left as it was
    assert all(img.j == -1 and img.frame is None for img in diagnostic_cameras.images().values())
    # the 2D-MOT and pickoff baslers share a line, as do the MOT and x baslers
    assert diag.img_2dmot.ttl == diag.img_tweezer_pickoff.ttl
    assert diag.img_mot.ttl == diag.img_tweezer_load_x.ttl


def test_bind_with_streams_and_the_edge_reaching_its_stream(capsys):
    calls = []
    seen = []

    def make_streams(expt, specs):
        seen.extend(specs)
        out = []
        for i, spec in enumerate(specs):
            if i % 2 == 0:
                s = csc.TriggeredCameraStreamClient.__new__(csc.TriggeredCameraStreamClient)
                s.ttl, s.t_trigger = f"line{i}", 3.e-6
                s.exposure_delay_cell = ExposureDelayCell(1.e-4)
                s.announce_trigger_mu = lambda slack, j, i=i: calls.append((i, slack, j))
            else:
                s = csc.InactiveCameraStream(expt, spec["key"], reason="test")
            out.append(s)
        return out

    diag = _bound(enabled=True, make_streams=make_streams)
    assert diag.active
    # cameras in order: mot_2d 0, xy 1, z 2, mot 3, x 4, tweezer_pickoff 5 -- even ones live
    assert {k: img.live for k, img in diag.images().items()} == {
        "img_2dmot": True, "img_mot_beams_xy": False, "img_gm_beams_xy": False,
        "img_mot_beams_z": True, "img_gm_beams_z": True, "img_mot": False, "img_gm": False,
        "img_tweezer_load_x": True, "img_tweezer_evap_x": True, "img_tweezer_pickoff": False}
    x = diag.img_tweezer_evap_x
    assert (x.ttl, x.exposure_delay_cell.value, x.t_trigger, x.j) == ("line4", 1.e-4, 3.e-6, 1)
    # the stream's cell itself (the kernel writes the claim's delay into it)
    assert x.exposure_delay_cell is diag.img_tweezer_load_x.exposure_delay_cell
    assert diag.img_mot.ttl == "ttl:mot_basler_trigger"     # a placeholder's: its own line
    x.announce_edge(1234)
    diag.img_mot.announce_edge(5)                           # not live: nothing, nothing raised
    assert calls == [(4, 1234, 1)]
    out = capsys.readouterr().out
    assert ("connected: basler_2dmot, z_basler, x_basler | NOT connected: xy_basler, mot_basler, "
            "tweezer_pickoff_basler") in out
    # the MOT basler's stream: at its first frame's settings, each frame cropped to its own ROI,
    # no saved viewer ROI read
    spec = seen[3]
    assert spec["camera"] is cameras.mot_basler and spec["key"] == ["img_mot", "img_gm"]
    assert (spec["exposure_time"], spec["gain"], spec["crop_to_saved_roi"]) == (300.e-6, 3., False)
    assert spec["frame_settings"] == {"img_gm": {"exposure_time": 3.e-3, "gain": 30.}}
    assert spec["frame_rois"] == {"img_mot": [1668, 1049, 2373, 1767],
                                  "img_gm": [1668, 1049, 2373, 1767]}
    assert seen[0]["frame_settings"] is None


def test_t_stage_from_the_run_params_and_scan(capsys):
    diag = _bound(enabled=True, make_streams=lambda e, s: [
        csc.InactiveCameraStream(e, sp["key"]) for sp in s])
    assert diag.img_mot.in_stage and diag.img_mot.t_stage_s == 1.0
    diag.resolve_stages(SimpleNamespace(t_mot_load=0.1))
    assert not diag.img_mot.in_stage
    assert "img_mot: not taken this run" in capsys.readouterr().out
    xv = [SimpleNamespace(key="t_mot_load", values=[0.5, 0.149, 2.])]
    diag.resolve_stages(SimpleNamespace(t_mot_load=1.), xv)
    assert not diag.img_mot.in_stage and diag.img_mot.t_stage_s == 0.149
    diag.img_gm.t_stage = 0.01
    diag.resolve_stages(SimpleNamespace(t_mot_load=1.))
    assert not diag.img_gm.in_stage and diag.img_mot.in_stage
    diag.img_gm.t_stage = "t_no_such_param"
    with pytest.raises(ValueError, match="not a parameter"):
        diag.resolve_stages(SimpleNamespace(t_mot_load=1.))


def test_the_record():
    diag = _bound()
    diag.img_mot.t_offset = -0.1           # an experiment's own offset, set in prepare
    diag.resolve_stages(SimpleNamespace(t_mot_load=0.5))
    rec = json.loads(json.dumps(diag.record()))
    assert rec["enabled"] is False and rec["default_imaging_type"] == "ABSORPTION"
    roi = [1668, 1049, 2373, 1767]
    assert rec["images"]["img_mot"] == {"camera": "mot_basler", "camera_id": "mot_basler",
                                        "frame": 0, "t_offset": -0.1, "t_stage": "t_mot_load",
                                        "t_stage_s": 0.5, "taken": False, "exposure_time": 300.e-6,
                                        "gain": 3., "roi": roi, "from_camera_entry": [],
                                        "max_exposure_time": None,
                                        # diagnostics off: no delay is used
                                        "exposure_delay": None, "exposure_delay_source": None}
    assert rec["images"]["img_gm"] == {"camera": "mot_basler", "camera_id": "mot_basler",
                                       "frame": 1, "t_offset": -25.e-3, "t_stage": None,
                                       "t_stage_s": None, "taken": False, "exposure_time": 3.e-3,
                                       "gain": 30., "roi": roi, "from_camera_entry": [],
                                       "max_exposure_time": None,
                                       "exposure_delay": None, "exposure_delay_source": None}
    assert diagnostic_cameras.img_mot.t_offset == -150.e-3


# ---- compile ---------------------------------------------------------------

needs_db = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                              reason="needs the lab env vars %db% and %code%")

_TRIGGERS = "\n".join(f"        self.diag.{k}.trigger()" for k in diagnostic_cameras.images())

EXPT = '''
from artiq.experiment import *
from kexp import Base
import numpy as np

class DiagnosticImagesCompile(EnvExperiment, Base):
    MIXED_STREAMS = False

    def prepare(self):
        Base.__init__(self, setup_camera=False, suppress_live_od=True, save_data=False)
        if self.MIXED_STREAMS:
            # as an enabled run (camera_streams is the test's stand-in)
            from kexp.control.cameras.diagnostic_images import diagnostic_images
            self.diagnostic_images = True
            self.diag = diagnostic_images(self, enabled=True)
        self.xvar('t_tof', np.linspace(1.e-3, 2.e-3, 2))
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.mot(self.p.t_mot_load)
        self.cmot_d1(self.p.t_d1cmot)
        self.gm(self.p.t_gm)
''' + _TRIGGERS + '''
        delay(self.p.t_tof)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''


class _StubServerClient:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


class _NoDatasets:
    def __getattr__(self, name):
        raise RuntimeError(f"compile test: dataset access ({name})")


def _mixed_streams(expt, specs):
    """camera_streams' stand-in: the first camera a real
    TriggeredCameraStreamClient (host side never set up) on its real TTL, the
    second a placeholder, the rest inactive."""
    from kexp.config.camera_id import camera_trigger_ttl
    out = []
    for i, spec in enumerate(specs):
        if i == 0:
            s = csc.TriggeredCameraStreamClient.__new__(csc.TriggeredCameraStreamClient)
            s.core = expt.core
            s.ttl = camera_trigger_ttl(expt.ttl, spec["camera"])
            s.exposure_delay_cell = ExposureDelayCell(0.)
            s.t_trigger = 2.e-6
            s.keys = tuple(spec["key"])
            out.append(s)
        elif i == 1:
            out.append(csc.DummyCameraStreamClient(expt, spec["key"], reason="test",
                                                   triggered=True))
        else:
            out.append(csc.InactiveCameraStream(expt, spec["key"], reason="test"))
    return out


def _build(monkeypatch, tmp_path, mixed=False):
    from waxx.base import monitor as wmon
    from waxx.control.slm.slm import SLM
    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id

    if mixed:
        monkeypatch.setattr(importlib.import_module(DI_MODULE), "camera_streams", _mixed_streams)
    else:
        _no_streams(monkeypatch)
    state = str(tmp_path / "device_state.json")
    monkeypatch.setattr(wmon, "MonitorClient", _StubServerClient)
    monkeypatch.setattr(kclients, "Monitor", lambda expt, device_state_json_path=None:
                        wmon.Monitor(expt, device_state_json_path=state))
    monkeypatch.setattr(kclients, "APDStageClient",
                        lambda *a, **k: SimpleNamespace(set_apd_stage=lambda *a, **k: None))
    monkeypatch.setattr(kclients, "HMRClient", kclients.HMRDummy)
    monkeypatch.setattr(kclients, "BristolAverageReader",
                        lambda *a, **k: SimpleNamespace(get_average=lambda *a, **k: None))
    monkeypatch.setattr(SLM, "reinit_if_due",
                        lambda self, **kw: {"result": "compile test", "by": kw.get("by")})

    class _NoWavemeter(wavemeter_id.WavemeterController):
        def __init__(self, *a, **k):
            raise RuntimeError("compile test: no wavemeter connection")

    monkeypatch.setattr(wavemeter_id, "WavemeterController", _NoWavemeter)

    from artiq.master.databases import DeviceDB
    from artiq.master.worker_db import DeviceManager
    from artiq.language.environment import ProcessArgumentManager
    from artiq.tools import file_import, get_experiment

    path = tmp_path / "diagnostic_images_compile.py"
    path.write_text(EXPT)
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(str(path), prefix="compile_test_")
    cls = get_experiment(module)
    cls.MIXED_STREAMS = mixed
    exp = cls((device_mgr, _NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return cls, exp, device_mgr


def _compile(cls, exp):
    # Never call run(): it would compile AND run on the core device.
    exp.core.compile(cls.run, [exp], {}, attribute_writeback=False, print_as_rpc=False)


@needs_db
def test_images_compile_with_diagnostics_off(monkeypatch, tmp_path):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path)
    try:
        assert not exp.diag.enabled and isinstance(exp.diag, diagnostic_frame)
        assert json.loads(exp._extra_file_texts["diagnostic_images"])["enabled"] is False
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


@needs_db
def test_images_compile_with_mixed_streams(monkeypatch, tmp_path):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, mixed=True)
    try:
        assert exp.diag.active
        kinds = [type(s) for s in exp.diag.streams().values()]
        assert kinds[0] is csc.TriggeredCameraStreamClient
        assert kinds[1] is csc.DummyCameraStreamClient
        assert set(kinds[2:]) == {csc.InactiveCameraStream}
        assert exp.diag.img_2dmot.live and not exp.diag.img_mot.live
        rec = json.loads(exp._extra_file_texts["diagnostic_images"])
        assert rec["enabled"] is True and set(rec["images"]) == set(exp.diag.images())
        assert rec["images"]["img_mot"]["taken"] is False          # placeholder camera
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


@needs_db
def test_image_triggers_are_really_compiled(monkeypatch, tmp_path):
    """Negative control: one image on a TTL of another type fails the run's
    compile, so the compiles above do type-check the image kernels (and every
    image must stay one type)."""
    from artiq.coredevice.core import CompileError
    from waxx.control.artiq.TTL import DummyTTL
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, mixed=True)
    try:
        exp.diag.img_gm.ttl = DummyTTL()
        with pytest.raises(CompileError, match="ttl"):
            _compile(cls, exp)
    finally:
        device_mgr.close_devices()
