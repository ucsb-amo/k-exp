"""Diagnostic images: the DiagnosticImage / DiagnosticCamera config, its
binding in DiagnosticImages, and the hook kernels compiled into a Base run.

No camera is ever opened: DiagnosticImages is built with diagnostics off, or
with kexp.control.cameras.diagnostic_images.camera_streams replaced (through
sys.modules) by stand-ins -- never the real camera_streams. The compile tests
build a Base experiment against the real device db and run ARTIQ's compiler
only (no core-device connection); they are skipped when %db% / %code% are not
set and take ~10 s each.
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

from kexp.config.camera_id import (DiagnosticCamera, DiagnosticImage, cameras,
                                   diagnostic_cameras, diagnostic_frame)
from kexp.control.cameras.diagnostic_images import DiagnosticImages

DI_MODULE = "kexp.control.cameras.diagnostic_images"


def _no_streams(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("test opened camera streams")
    monkeypatch.setattr(sys.modules[DI_MODULE], "camera_streams", refuse)


def _expt():
    return SimpleNamespace(core=None)


def _config(*entries):
    cfg = diagnostic_frame.__new__(diagnostic_frame)
    for name, entry in entries:
        entry.key = name
        setattr(cfg, name, entry)
    cfg.no_roi_downsample = 4
    return cfg


# ---- config ---------------------------------------------------------------

def test_the_config_carried_over_unchanged():
    """Frames, per-frame settings and camera settings as on main before the
    move to DiagnosticImage (k-exp bc551317); offsets as the t_diag_* params.
    Cameras added since are checked by tests of their own."""
    d = SimpleNamespace(entries=lambda: [e for e in diagnostic_cameras.entries()
                                         if e.key != "tweezer_pickoff"],
                        mot=diagnostic_cameras.mot)
    assert [(e.key, e.camera.key) for e in d.entries()] == [
        ("mot_2d", "basler_2dmot"), ("xy", "xy_basler"), ("z", "z_basler"),
        ("mot", "mot_basler"), ("x", "x_basler")]
    assert {e.key: e.frames for e in d.entries()} == {
        "mot_2d": ["img_2dmot"],
        "xy": ["img_mot_beams_xy", "img_gm_beams_xy"],
        "z": ["img_mot_beams_z", "img_gm_beams_z"],
        "mot": ["img_mot", "img_gm"],
        "x": ["img_tweezer_load_x", "img_tweezer_evap_x"]}
    assert {e.key: e.frame_settings for e in d.entries()} == {
        "mot_2d": {}, "xy": {"img_gm_beams_xy": {"gain": 18.}}, "z": {},
        "mot": {"img_gm": {"exposure_time": 3.e-3, "gain": 30.}},
        "x": {"img_tweezer_load_x": {"exposure_time": 50.e-6, "gain": 5.}}}
    assert {e.key: (e.exposure_time, e.gain, e.roi) for e in d.entries()} == {
        "mot_2d": (3.5e-3, 20., [1685, 741, 1959, 1022]),
        "xy": (19.e-6, 0., [382, 398, 943, 755]),
        "z": (19.e-6, 0., [660, 300, 1260, 900]),
        "mot": (300.e-6, 3., [1668, 1049, 2373, 1767]),
        "x": (300.e-6, 30., [1511, 141, 1729, 788])}
    timing = {img.key: (img.at, img.t) for e in d.entries() for img in e.images}
    assert timing == {
        "img_2dmot": ("mot_push_on", -60.e-3),           # t_diag_2dmot_before_push
        "img_mot_beams_xy": ("mot_beams_on", 5.e-3),      # t_diag_mot_beams_after_on
        "img_mot_beams_z": ("mot_beams_on", 5.e-3),
        "img_mot": ("mot_load_end", -150.e-3),           # t_diag_mot_before_end
        "img_gm": ("cmot_end", -25.e-3),                 # t_diag_gm_trigger_lead
        "img_gm_beams_xy": ("gm_beams_on", 0.25e-3),     # t_diag_gm_beams_after_start
        "img_gm_beams_z": ("gm_beams_on", 0.25e-3),
        "img_tweezer_load_x": ("tweezer_load", 1.e-3),   # t_diag_tweezer_after_load
        "img_tweezer_evap_x": ("tweezer_evap", 1.e-3)}   # t_diag_tweezer_after_evap
    assert d.mot.frame_index("img_gm") == 1 and d.mot.frame_index("img_2dmot") == -1


def test_tweezer_pickoff_entry():
    """The tweezer pickoff camera (2026-10-19): one frame at tweezer_load,
    on the 2D-MOT basler's trigger line, Line2."""
    e = diagnostic_cameras.tweezer_pickoff
    assert e.camera.key == "tweezer_pickoff_basler" and e.camera.serial_no == "40427782"
    assert e.camera.trigger_ttl == cameras.basler_2dmot.trigger_ttl == "basler_2dmot"
    assert e.camera.trigger_source == "Line2"
    assert (e.exposure_time, e.gain, e.roi) == (2.e-6, 0., None)
    assert [(i.key, i.at, i.t, i.show) for i in e.images] == [
        ("img_tweezer_pickoff", "tweezer_load", 1.e-3, "image")]
    assert e.frame_settings == {}

def test_image_spec_checks_and_repr():
    with pytest.raises(ValueError, match="identifier"):
        DiagnosticImage("img-bad", at="cmot_end")
    with pytest.raises(ValueError, match="show"):
        DiagnosticImage("img_a", at="cmot_end", show="table")
    with pytest.raises(ValueError, match="twice"):
        DiagnosticCamera(cameras.z_basler, images=[DiagnosticImage("img_a", at="cmot_end"),
                                                   DiagnosticImage("img_a", at="gm_beams_on")])
    img = DiagnosticImage("img_gm", at="cmot_end", t=-25.e-3, exposure_time=3.e-3, gain=30.,
                          label="GM fluorescence", show="image")
    assert img.label == "GM fluorescence"
    assert DiagnosticImage("img_mot_beams_z", at="mot_beams_on").label == "mot beams z"
    assert eval(repr(img)).__dict__ == img.__dict__


# ---- binding --------------------------------------------------------------

def test_every_image_is_bound_to_its_camera_with_its_index(monkeypatch):
    _no_streams(monkeypatch)
    diag = DiagnosticImages(_expt(), enabled=False)
    assert not diag.active
    assert set(diag.images) == {k for e in diagnostic_cameras.entries() for k in e.frames}
    for e in diagnostic_cameras.entries():
        cam = diag.cameras[e.key]
        assert cam is not e and cam.stream is diag.streams[e.key] and cam.diag is diag
        assert cam.stream.keys == tuple(e.frames)
        for j, spec in enumerate(e.images):
            img = getattr(diag, spec.key)
            assert img is diag.images[spec.key] and img is not spec
            assert (img.camera, img.j, img.at, img.t) == (cam, j, spec.at, spec.t)
    # the config singleton is left as it was
    assert all(img.j == -1 and img.camera is None
               for e in diagnostic_cameras.entries() for img in e.images)
    # one class per camera / image / run (ARTIQ types attributes per class)
    classes = [type(c) for c in diag.cameras.values()] + [type(i) for i in diag.images.values()]
    assert len(set(classes)) == len(classes)
    assert type(diag) is not DiagnosticImages and isinstance(diag, DiagnosticImages)


def test_each_hook_triggers_the_images_at_it(monkeypatch):
    _no_streams(monkeypatch)
    diag = DiagnosticImages(_expt(), enabled=False)
    hooks = DiagnosticImages.hooks()
    assert hooks == ["mot_push_on", "mot_beams_on", "mot_load_end", "cmot_end", "gm_beams_on",
                     "lightsheet_load", "lightsheet_evap", "tweezer_load", "tweezer_evap"]
    for name in hooks:
        src = getattr(type(diag), f"_fire_{name}").artiq_embedded.function
        called = [line.strip() for line in src.splitlines()[1:]]
        want = [f"self.{k}.trigger(t_stage)" for k, i in diag.images.items() if i.at == name]
        assert called == (want or ["pass"]), name
        assert getattr(type(diag), name) is getattr(DiagnosticImages, name)
    assert type(diag)._fire_mot_beams_on.artiq_embedded.function.count("trigger") == 2
    assert type(diag)._fire_lightsheet_load.artiq_embedded.function.endswith("pass")
    # a second run's object has hooks of its own
    other = DiagnosticImages(_expt(), enabled=False)
    assert type(other) is not type(diag)


def test_a_config_the_hooks_cannot_fire_is_refused_before_any_camera(monkeypatch):
    _no_streams(monkeypatch)

    def cam(*images):
        return DiagnosticCamera(cameras.z_basler, images=images)

    with pytest.raises(ValueError, match="no such hook"):
        DiagnosticImages(_expt(), enabled=False,
                         config=_config(("z", cam(DiagnosticImage("img_a", at="gm_start")))))
    with pytest.raises(ValueError, match="also a frame of 'z'"):
        DiagnosticImages(_expt(), enabled=False, config=_config(
            ("z", cam(DiagnosticImage("img_a", at="cmot_end"))),
            ("xy", DiagnosticCamera(cameras.xy_basler,
                                    images=[DiagnosticImage("img_a", at="cmot_end")]))))
    for taken in ("images", "active", "cmot_end", "record"):
        with pytest.raises(ValueError, match="taken"):
            DiagnosticImages(_expt(), enabled=False,
                             config=_config(("z", cam(DiagnosticImage(taken, at="cmot_end")))))
    # a camera with no images yet is skipped, not set up
    diag = DiagnosticImages(_expt(), enabled=False, config=_config(("z", cam())))
    assert diag.cameras == {} and diag.images == {}


def test_a_hook_must_fire_its_own_images(monkeypatch):
    from artiq.experiment import kernel
    _no_streams(monkeypatch)

    class Miswired(DiagnosticImages):
        @kernel
        def extra_hook(self, t_stage=0.):
            """Copied from cmot_end and not renamed."""
            self._fire_cmot_end(t_stage)

    with pytest.raises(TypeError, match="must call self._fire_extra_hook"):
        Miswired(_expt(), enabled=False)


def test_the_record(monkeypatch):
    _no_streams(monkeypatch)
    diag = DiagnosticImages(_expt(), enabled=False)
    diag.img_mot.t = -0.1           # an experiment's own offset, set in prepare
    rec = json.loads(json.dumps(diag.record()))
    assert rec["enabled"] is False
    assert rec["images"]["img_mot"] == {"camera": "mot", "camera_id": "mot_basler", "frame": 0,
                                        "at": "mot_load_end", "t": -0.1}
    assert rec["images"]["img_gm"] == {"camera": "mot", "camera_id": "mot_basler", "frame": 1,
                                       "at": "cmot_end", "t": -25.e-3,
                                       "exposure_time": 3.e-3, "gain": 30.}
    assert diagnostic_cameras.mot.images[0].t == -150.e-3


# ---- compile ---------------------------------------------------------------

needs_db = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                              reason="needs the lab env vars %db% and %code%")

EXPT = '''
from artiq.experiment import *
from kexp import Base
import numpy as np

class DiagnosticHooksCompile(EnvExperiment, Base):
    MIXED_STREAMS = False

    def prepare(self):
        Base.__init__(self, setup_camera=False, suppress_live_od=True, save_data=False)
        if self.MIXED_STREAMS:
            # as an enabled run (camera_streams is the test's stand-in)
            from kexp.control.cameras.diagnostic_images import DiagnosticImages
            self.diagnostic_images = True
            self.diag = DiagnosticImages(self, enabled=True)
        self.xvar('t_tof', np.linspace(1.e-3, 2.e-3, 2))
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.mot(self.p.t_mot_load)
        self.cmot_d1(self.p.t_d1cmot)
        self.gm(self.p.t_gm)
        self.diag.lightsheet_load()
        self.diag.lightsheet_evap()
        self.diag.tweezer_load()
        self.diag.tweezer_evap()
        self.diag.img_mot.trigger()
        self.diag.img_tweezer_evap_x.trigger(5.e-3)
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


def _build(monkeypatch, tmp_path, mixed=False):
    from waxx.base import monitor as wmon
    from waxx.control.slm.slm import SLM
    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id

    if mixed:
        monkeypatch.setattr(sys.modules[DI_MODULE], "camera_streams", _mixed_streams)
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

    path = tmp_path / "diagnostic_hooks_compile.py"
    path.write_text(EXPT)
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(str(path), prefix="compile_test_")
    cls = get_experiment(module)
    cls.MIXED_STREAMS = mixed
    exp = cls((device_mgr, _NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return cls, exp, device_mgr


def _mixed_streams(expt, specs):
    """camera_streams' stand-in: the first camera a real
    TriggeredCameraStreamClient's kernel on its real TTL (host side never
    set up), the second a placeholder, the rest inactive."""
    from waxx.control.cameras import camera_stream_client as csc
    from kexp.config.camera_id import camera_trigger_ttl
    out = []
    for i, spec in enumerate(specs):
        if i == 0:
            s = csc.TriggeredCameraStreamClient.__new__(csc.TriggeredCameraStreamClient)
            s.core = expt.core
            s.ttl = camera_trigger_ttl(expt.ttl, spec["camera"])
            s.exposure_delay = 0.
            s.t_trigger = 2.e-6
            s.keys = tuple(spec["key"])
            out.append(s)
        elif i == 1:
            out.append(csc.DummyCameraStreamClient(expt, spec["key"], reason="test",
                                                   triggered=True))
        else:
            out.append(csc.InactiveCameraStream(expt, spec["key"], reason="test"))
    return out


def _compile(cls, exp):
    # Never call run(): it would compile AND run on the core device.
    exp.core.compile(cls.run, [exp], {}, attribute_writeback=False, print_as_rpc=False)


@needs_db
def test_hooks_compile_with_diagnostics_off(monkeypatch, tmp_path):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path)
    try:
        assert not exp.diag.enabled
        assert json.loads(exp._extra_file_texts["diagnostic_images"])["enabled"] is False
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


@needs_db
def test_hooks_compile_with_mixed_streams(monkeypatch, tmp_path):
    from waxx.control.cameras import camera_stream_client as csc
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, mixed=True)
    try:
        assert exp.diag.active
        rec = json.loads(exp._extra_file_texts["diagnostic_images"])
        assert rec["enabled"] is True and set(rec["images"]) == set(exp.diag.images)
        kinds = [type(s) for s in exp.diag.streams.values()]
        assert kinds[0] is csc.TriggeredCameraStreamClient
        assert kinds[1] is csc.DummyCameraStreamClient
        assert set(kinds[2:]) == {csc.InactiveCameraStream}
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


@needs_db
def test_hook_bodies_are_really_compiled(monkeypatch, tmp_path):
    """Negative control: a hook body that cannot compile fails the run's
    compile, so the compiles above do type-check the generated hooks."""
    from artiq.coredevice.core import CompileError
    from artiq.language.core import kernel_from_string
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, mixed=True)
    try:
        setattr(type(exp.diag), "_fire_tweezer_evap", kernel_from_string(
            ["self", "t_stage"], "self.no_such_image_xyz.trigger(t_stage)"))
        with pytest.raises(CompileError, match="no_such_image_xyz"):
            _compile(cls, exp)
    finally:
        device_mgr.close_devices()
