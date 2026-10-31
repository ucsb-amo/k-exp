"""The feedback experiments compile with the state-dependent read model ON (2026-10-11).

The standard path (FeedbackExpt: generate_posterior in the loop) and the fast path
(FeedbackExptFast: propagate_hypotheses / weigh_hypotheses) each compile their run() with
read_twist_per_sz, back_action_coherence_slope and read_alpha_lightshift set, and the
standard path once with them off (every read-model param set explicitly in the source,
never taken from the shipped defaults, which are M1-p2 since 2026-10-11). Compile only,
against the real device db: no core-device connection (as artiq_compile), every network client stubbed (the sub-scan compile test's
stubs). Skipped without %db% / %code%. ~10 s per compile."""
import os

import pytest

from test_feedback_subscan_compiles import _NoDatasets, _StubScope, _StubServerClient  # noqa: F401
import test_feedback_subscan_compiles as subscan

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

EXPT = '''
from artiq.experiment import *
from MODULE import BASECLASS
import numpy as np

class ReadcohCompile(EnvExperiment, BASECLASS):
    def prepare(self):
        BASECLASS.__init__(self, save_data=False, suppress_live_od=True)
        self.p.cal_enabled = CAL_ENABLED
        self.p.cal_every_n_shots = 2
        self.p.N_pulses = 3
        self.p.N_repeats = 1
        self.p.read_twist_per_sz = TWIST
        self.p.back_action_coherence_slope = SLOPE
        self.p.read_alpha_lightshift = ALS
        self.p.back_action_coherence = COH
        self.xvar('feedback_fractional_initial_offset', np.array([0., 0.5, 1.]))
        self.finish_prepare(shuffle=False)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''

PATHS = {
    "standard": ("kexp.experiments.HF_experiments.feedback.base_expt_feedback", "FeedbackExpt"),
    "fast": ("kexp.experiments.HF_experiments.feedback.alias_grid.base_expt_feedback_fast",
             "FeedbackExptFast"),
}


def _build(monkeypatch, tmp_path, path, twist, slope, als, coh, cal_enabled=0):
    module, base = PATHS[path]
    src = (EXPT.replace("MODULE", module).replace("BASECLASS", base)
           .replace("TWIST", repr(twist)).replace("SLOPE", repr(slope)).replace("ALS", als)
           .replace("COH", repr(coh)))
    orig = subscan.EXPT
    monkeypatch.setattr(subscan, "EXPT", src)      # subscan._build fills CAL_ENABLED
    try:
        return subscan._build(monkeypatch, tmp_path, cal_enabled=cal_enabled)
    finally:
        monkeypatch.setattr(subscan, "EXPT", orig)


@pytest.mark.parametrize("path,cal_enabled", [("standard", 0), ("fast", 0), ("standard", 1)])
def test_compiles_with_the_read_model_on(monkeypatch, tmp_path, path, cal_enabled):
    """(cal_enabled 1: the in-run readout calibration's sub-scan in the same kernel)"""
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, path, 0.869, 0.193, "1.432", 0.739,
                                  cal_enabled=cal_enabled)
    try:
        assert exp.read_twist_on and exp.read_coherence_slope_on and exp.read_alpha_lightshift_on
        assert exp.read_twist == 0.869 and exp.read_alpha_lightshift == 1.432
        subscan._compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_compiles_with_the_read_model_off(monkeypatch, tmp_path):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, "standard", 0.0, 0.0, 'float("nan")', 0.7215)
    try:
        assert not (exp.read_twist_on or exp.read_coherence_slope_on or exp.read_alpha_lightshift_on)
        subscan._compile(cls, exp)
    finally:
        device_mgr.close_devices()
