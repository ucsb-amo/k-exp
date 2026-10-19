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
import json
import os
import sys
from types import SimpleNamespace

import pytest

from waxx.control.cameras import camera_stream_client as csc
from waxx.control.cameras.diagnostic_frame import DiagnosticCamera, DiagnosticImage
from waxx.control.cameras.diagnostic_frame import diagnostic_frame as diagnostic_frame_waxx

from kexp.config.camera_id import cameras, diagnostic_cameras, diagnostic_frame

DI_MODULE = "kexp.control.cameras.diagnostic_images"


def _no_streams(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("test opened camera streams")
    monkeypatch.setattr(sys.modules[DI_MODULE], "camera_streams", refuse)


def _expt():
    return SimpleNamespace(core=SimpleNamespace(), params=SimpleNamespace(t_mot_load=1.0))


def _ttl(camera):
    return f"ttl:{camera.trigger_ttl}"


def _bound(enabled=False, make_streams=None, expt=None):
    return diagnostic_frame().bind(expt or _expt(), enabled, make_streams=make_streams,
                                   trigger_ttl=_ttl)


# ---- config ---------------------------------------------------------------

def test_the_config_carried_over_unchanged():
    """Frames, per-frame settings and camera settings as on main before the
    move (k-exp bc551317); offsets as the t_diag_* params; the tweezer pickoff
    as found in the live tree on 2026-10-19."""
    d = diagnostic_cameras
    assert [(e.key, e.camera.key) for e in d.entries()] == [
        ("mot_2d", "basler_2dmot"), ("xy", "xy_basler"), ("z", "z_basler"),
        ("mot", "mot_basler"), ("x", "x_basler"), ("tweezer_pickoff", "tweezer_pickoff_basler")]
    assert {e.key: e.frames for e in d.entries()} == {
        "mot_2d": ["img_2dmot"],
        "xy": ["img_mot_beams_xy", "img_gm_beams_xy"],
        "z": ["img_mot_beams_z", "img_gm_beams_z"],
        "mot": ["img_mot", "img_gm"],
        "x": ["img_tweezer_load_x", "img_tweezer_evap_x"],
        "tweezer_pickoff": ["img_tweezer_pickoff"]}
    assert {e.key: e.frame_settings for e in d.entries()} == {
        "mot_2d": {}, "xy": {"img_gm_beams_xy": {"gain": 18.}}, "z": {},
        "mot": {"img_gm": {"exposure_time": 3.e-3, "gain": 30.}},
        "x": {"img_tweezer_load_x": {"exposure_time": 50.e-6, "gain": 5.}},
        "tweezer_pickoff": {}}
    assert {e.key: (e.exposure_time, e.gain, e.roi) for e in d.entries()} == {
        "mot_2d": (3.5e-3, 20., [1685, 741, 1959, 1022]),
        "xy": (19.e-6, 0., [382, 398, 943, 755]),
        "z": (19.e-6, 0., [660, 300, 1260, 900]),
        "mot": (300.e-6, 3., [1668, 1049, 2373, 1767]),
        "x": (300.e-6, 30., [1511, 141, 1729, 788]),
        "tweezer_pickoff": (2.e-6, 0., [1799, 909, 2787, 1804])}
    assert {k: (img.t, img.t_stage) for k, img in d.images().items()} == {
        "img_2dmot": (-60.e-3, None),             # t_diag_2dmot_before_push
        "img_mot_beams_xy": (5.e-3, None),        # t_diag_mot_beams_after_on
        "img_gm_beams_xy": (0.25e-3, None),       # t_diag_gm_beams_after_start
        "img_mot_beams_z": (5.e-3, None),
        "img_gm_beams_z": (0.25e-3, None),
        "img_mot": (-150.e-3, "t_mot_load"),      # t_diag_mot_before_end, main's load check
        "img_gm": (-25.e-3, None),                # t_diag_gm_trigger_lead
        "img_tweezer_load_x": (1.e-3, None),      # t_diag_tweezer_after_load
        "img_tweezer_evap_x": (1.e-3, None),      # t_diag_tweezer_after_evap
        "img_tweezer_pickoff": (2.e-6, None)}     # as found 2026-10-19
    assert {k: img.show for k, img in d.images().items()} == {
        "img_2dmot": "image", "img_mot_beams_xy": "counts", "img_gm_beams_xy": "counts",
        "img_mot_beams_z": "counts", "img_gm_beams_z": "counts", "img_mot": "image",
        "img_gm": "image", "img_tweezer_load_x": None, "img_tweezer_evap_x": None,
        "img_tweezer_pickoff": "image"}
    assert d.mot.frame_index("img_gm") == 1 and d.mot.frame_index("img_2dmot") == -1


def test_tweezer_pickoff_entry():
    """The tweezer pickoff camera (2026-10-19): on the 2D-MOT basler's trigger
    line, Line2, so the two streams are siblings."""
    e = diagnostic_cameras.tweezer_pickoff
    assert e.camera.key == "tweezer_pickoff_basler" and e.camera.serial_no == "40427782"
    assert e.camera.trigger_ttl == cameras.basler_2dmot.trigger_ttl == "basler_2dmot"
    assert e.camera.trigger_source == "Line2"


def test_names_labels_and_refusals():
    d = diagnostic_cameras
    assert d.img_mot.key == "img_mot" and d.img_mot.camera is d.mot
    assert d.mot.images == [d.img_mot, d.img_gm]
    assert d.mot.label == "MOT basler" and d.img_mot_beams_z.label == "MOT beams"

    class Frame(diagnostic_frame_waxx):
        def __init__(self, body):
            self.setup()
            body(self)
            self.cleanup()

    def ok(f):
        f.cam = f.camera(cameras.z_basler)
        f.img_a_b = f.image(f.cam, t=1.e-3)
    f = Frame(ok)
    assert f.img_a_b.label == "a b" and f.cam.label == "z basler" and f.cam.frames == ["img_a_b"]

    def twice(f):
        f.cam = f.camera(cameras.z_basler)
        f.img_a = f.image(f.cam)
        f.img_b = f.img_a
    with pytest.raises(ValueError, match="already .img_a"):
        Frame(twice)

    def taken(f):
        f.cam = f.camera(cameras.z_basler)
        f.images = f.image(f.cam)
    with pytest.raises(ValueError, match="taken"):
        Frame(taken)

    def unassigned(f):
        f.cam = f.camera(cameras.z_basler)
        f.image(f.cam)
    with pytest.raises(ValueError, match="not assigned"):
        Frame(unassigned)

    def foreign(f):
        f.img_a = f.image(DiagnosticCamera(cameras.z_basler))
    with pytest.raises(ValueError, match="not an attribute"):
        Frame(foreign)

    with pytest.raises(ValueError, match="show"):
        DiagnosticImage(DiagnosticCamera(cameras.z_basler), show="table")
    with pytest.raises(TypeError, match="DiagnosticCamera"):
        DiagnosticImage(cameras.z_basler)


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

    def make_streams(expt, specs):
        out = []
        for i, spec in enumerate(specs):
            if i % 2 == 0:
                s = csc.TriggeredCameraStreamClient.__new__(csc.TriggeredCameraStreamClient)
                s.ttl, s.exposure_delay, s.t_trigger = f"line{i}", 1.e-4, 3.e-6
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
    assert (x.ttl, x.exposure_delay, x.t_trigger, x.j) == ("line4", 1.e-4, 3.e-6, 1)
    assert diag.img_mot.ttl == "ttl:mot_basler_trigger"     # a placeholder's: its own line
    x.announce_edge(1234)
    diag.img_mot.announce_edge(5)                           # not live: nothing, nothing raised
    assert calls == [(4, 1234, 1)]
    out = capsys.readouterr().out
    assert "connected: mot_2d, z, x | NOT connected: xy, mot, tweezer_pickoff" in out


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
    diag.img_mot.t = -0.1           # an experiment's own offset, set in prepare
    diag.resolve_stages(SimpleNamespace(t_mot_load=0.5))
    rec = json.loads(json.dumps(diag.record()))
    assert rec["enabled"] is False
    assert rec["images"]["img_mot"] == {"camera": "mot", "camera_id": "mot_basler", "frame": 0,
                                        "t": -0.1, "t_stage": "t_mot_load", "t_stage_s": 0.5,
                                        "taken": False}
    assert rec["images"]["img_gm"] == {"camera": "mot", "camera_id": "mot_basler", "frame": 1,
                                       "t": -25.e-3, "t_stage": None, "t_stage_s": None,
                                       "taken": False, "exposure_time": 3.e-3, "gain": 30.}
    assert diagnostic_cameras.img_mot.t == -150.e-3


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
