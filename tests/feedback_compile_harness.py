"""Compile harness for FeedbackExpt-derived experiments (imported by the
*_compiles tests; not collected itself).

``_build`` writes an experiment source (``EXPT`` by default) to pytest's temp
dir, prepares it against the real device db with every network client stubbed
(monitor, stage, magnetometer, Bristol, SLM reinit, the Siglent scope, liveOD
suppressed), and ``_compile`` type-checks its run() with ARTIQ's compiler. No
core-device connection is made (the same thing artiq_compile does); nothing is
written outside pytest's temp dir. Each compile takes ~10 s. Tests using it
skip when %db% / %code% are not set.
"""
import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

EXPT = '''
from artiq.experiment import *
from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
import numpy as np

class FeedbackCompile(EnvExperiment, FeedbackExpt):
    def prepare(self):
        FeedbackExpt.__init__(self, save_data=False, suppress_live_od=True)
        self.p.N_pulses = 3
        self.p.N_repeats = 1
        self.xvar('feedback_fractional_initial_offset', np.array([0., 0.5, 1.]))
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


def _build(monkeypatch, tmp_path, mot_preload=False, expt=None):
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

    path = tmp_path / f"feedback_compile_{int(mot_preload)}.py"
    text = EXPT if expt is None else expt
    if mot_preload:
        text = text.replace("suppress_live_od=True)", "suppress_live_od=True, mot_preload=True)")
    path.write_text(text)
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(str(path), prefix="compile_test_")
    cls = get_experiment(module)
    exp = cls((device_mgr, _NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return cls, exp, device_mgr


def _compile(cls, exp):
    # Never call run(): it would compile AND run on the core device.
    exp.core.compile(cls.run, [exp], {}, attribute_writeback=False, print_as_rpc=False)
