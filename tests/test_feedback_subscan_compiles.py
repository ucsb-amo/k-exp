"""A feedback experiment with the interleaved readout calibration compiles.

The sub-scan's kernel path -- the scan loop's slot (waxx Scanner), the
kexp Base hooks, FeedbackExpt.calibration_kernel / calibration_read and the
sub-scan vault's put_shot_data -- is only type-checked by ARTIQ's compiler.
This compiles a minimal FeedbackExpt-derived experiment's run() against the
real device db, with cal_enabled 1 and 0. No core-device connection is made
(the same thing artiq_compile does); every network client is a stub (monitor,
stage, magnetometer, Bristol, SLM reinit, the Siglent scope, liveOD
suppressed), nothing is written outside pytest's temp dir.

Also: a static check that calibration_kernel triggers no camera and no scope
(frames are counted per shot). Each compile takes ~10 s. Skipped when %db% /
%code% are not set.
"""
import inspect
import os
import re
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

EXPT = '''
from artiq.experiment import *
from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
import numpy as np

class SubScanCompile(EnvExperiment, FeedbackExpt):
    def prepare(self):
        FeedbackExpt.__init__(self, save_data=False, suppress_live_od=True)
        self.p.cal_enabled = CAL_ENABLED
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


class _StubServerClient:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


class _NoDatasets:
    def __getattr__(self, name):
        raise RuntimeError(f"compile test: dataset access ({name})")


class _StubScope:
    """Stands in for the Siglent driver: construction connects to the scope."""
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


def _build(monkeypatch, tmp_path, cal_enabled=1):
    from waxx.base import monitor as wmon
    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id
    import waxx.control.misc.oscilloscopes as osc

    state = str(tmp_path / "device_state.json")
    monkeypatch.setattr(wmon, "MonitorClient", _StubServerClient)
    monkeypatch.setattr(kclients, "Monitor", lambda expt, device_state_json_path=None:
                        wmon.Monitor(expt, device_state_json_path=state))
    monkeypatch.setattr(kclients, "APDStageClient",
                        lambda *a, **k: SimpleNamespace(set_apd_stage=lambda *a, **k: None))
    monkeypatch.setattr(kclients, "HMRClient", kclients.HMRDummy)
    monkeypatch.setattr(kclients, "BristolAverageReader",
                        lambda *a, **k: SimpleNamespace(get_average=lambda *a, **k: None))
    from waxx.control.slm.slm import SLM
    monkeypatch.setattr(SLM, "reinit_if_due",
                        lambda self, **kw: {"result": "compile test", "by": kw.get("by")})
    monkeypatch.setattr(osc, "SiglentSDS2000X_Base", _StubScope)

    class _NoWavemeter(wavemeter_id.WavemeterController):
        def __init__(self, *a, **k):
            raise RuntimeError("compile test: no wavemeter connection")

    monkeypatch.setattr(wavemeter_id, "WavemeterController", _NoWavemeter)

    from artiq.master.databases import DeviceDB
    from artiq.master.worker_db import DeviceManager
    from artiq.language.environment import ProcessArgumentManager
    from artiq.tools import file_import, get_experiment

    path = tmp_path / f"subscan_compile_{cal_enabled}.py"
    path.write_text(EXPT.replace("CAL_ENABLED", str(cal_enabled)))
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(str(path), prefix="compile_test_")
    cls = get_experiment(module)
    exp = cls((device_mgr, _NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return cls, exp, device_mgr


def _compile(cls, exp):
    # Never call run(): it would compile AND run on the core device.
    exp.core.compile(cls.run, [exp], {}, attribute_writeback=False, print_as_rpc=False)


def test_the_sub_scan_is_declared_and_the_run_compiles(monkeypatch, tmp_path):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, cal_enabled=1)
    try:
        sub = exp._subscan
        assert sub is not None and exp.cal is sub
        assert sub.xvarnames == ["t_raman_pulse"] and sub.point_keys == ["t_raman_pulse", "cal_readout_mode"]
        assert sub.n_points_per_event == 2 and sub.n_cycle == 2 and sub.event_starts == [0, 2]
        assert "cal_apd" in exp.data.keys and "cal_status" in exp.data.keys
        # without liveOD the sub-scan is disabled loudly, the run proceeds; the kernel still compiles
        assert not exp._subscan_enabled and "cal_scan_disabled" in exp._extra_file_texts
        assert exp.readout_cal is not None and exp.readout_cal.start["values"]["v_apd_all_up"] == exp.p.v_apd_all_up
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_without_the_sub_scan_the_run_compiles_and_declares_nothing(monkeypatch, tmp_path):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, cal_enabled=0)
    try:
        # the object exists for the compiler; it is off, takes nothing and leaves no record
        assert exp._subscan is exp.cal and not exp.cal.enabled and exp.cal.quiet
        assert exp.readout_cal is None and not exp._subscan_enabled
        assert not any(k.startswith("cal_") for k in exp.data.keys)
        assert "cal_scan_disabled" not in exp._extra_file_texts
        assert exp.cal.data.apd.shot_data.shape == (int(exp.p.cal_n_reads),)
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_the_guards_refuse_the_apply_path_and_the_preshot_gain(monkeypatch, tmp_path):
    from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
    e = SimpleNamespace(p=SimpleNamespace(cal_apply=1))
    with pytest.raises(NotImplementedError):
        FeedbackExpt._declare_readout_calibration(e)
    e = SimpleNamespace(p=SimpleNamespace(cal_apply=0, preshot_endpoint_gain=0.5))
    with pytest.raises(ValueError, match="mutually exclusive"):
        FeedbackExpt._declare_readout_calibration(e)


def test_calibration_kernel_triggers_no_camera_and_no_scope():
    from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
    src = inspect.getsource(FeedbackExpt.calibration_kernel) + inspect.getsource(FeedbackExpt.calibration_read)
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith(("#", '"""')) )
    for token in ("abs_image", "trigger_camera", "pd_scope_trig", "self.diag.", "camera_trigger", "self.data."):
        assert not re.search(re.escape(token) + r"\w*\(", body.split('"""')[-1]), token
