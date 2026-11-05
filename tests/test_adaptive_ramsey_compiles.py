"""The adaptive Ramsey test experiment compiles (2026-10-30).

AdaptiveRamseyExpt's run() -- scan_kernel, feedback_loop with ramsey_plan_next (the max-variance
gap + phase policy), ramsey_read, the timing probe in initialize_feedback -- through ARTIQ's
compiler against the real device db, no core-device connection (as artiq_compile), every network
client stubbed (feedback_compile_harness's stubs). Once with the default policy and once with
PHASE_RANDOM (the phase-sign check run). Skipped without %db% / %code%. ~10 s per compile.
"""
import os

import pytest

import feedback_compile_harness as harness

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

VERSIONS = {
    "v1": ("kexp.experiments.HF_experiments.feedback.adaptive_ramsey.adaptive_ramsey", "AdaptiveRamseyExpt"),
    "v2": ("kexp.experiments.HF_experiments.feedback.adaptive_ramsey.adaptive_ramsey_v2", "AdaptiveRamseyExptV2"),
    "v3": ("kexp.experiments.HF_experiments.feedback.adaptive_ramsey.adaptive_ramsey_v3", "AdaptiveRamseyExptV3"),
    "v4": ("kexp.experiments.HF_experiments.feedback.adaptive_ramsey.adaptive_ramsey_v4", "AdaptiveRamseyExptV4"),
    "v5": ("kexp.experiments.HF_experiments.feedback.adaptive_ramsey.adaptive_ramsey_v5", "AdaptiveRamseyExptV5"),
}

EXPT = '''
from artiq.experiment import *
from MODULE import BASECLASS
import numpy as np

class AdaptiveRamseyCompile(EnvExperiment, BASECLASS):
    def prepare(self):
        BASECLASS.__init__(self, save_data=False, suppress_live_od=True)
        self.p.N_pulses = 4
        self.p.N_repeats = 1
        self.p.ramsey_phase_policy = PHASE_POLICY
        self.xvar('feedback_fractional_initial_offset', np.array([-0.5, 0., 0.5]))
        self.finish_prepare(shuffle=False)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''


def _build(monkeypatch, tmp_path, phase_policy, version="v1"):
    module, base = VERSIONS[version]
    src = (EXPT.replace("PHASE_POLICY", str(phase_policy)).replace("MODULE", module)
           .replace("BASECLASS", base))
    return harness._build(monkeypatch, tmp_path, expt=src)


@pytest.mark.parametrize("version,phase_policy", [("v1", 4), ("v1", 3), ("v2", 4), ("v2", 3), ("v3", 4), ("v3", 3),
                                                  ("v4", 4), ("v4", 3), ("v5", 4), ("v5", 3)])
def test_the_adaptive_ramsey_experiment_compiles(monkeypatch, tmp_path, version, phase_policy):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, phase_policy, version)
    try:
        if version in ("v2", "v3", "v4", "v5"):
            assert "ramsey_set_margin" in exp.data.keys
        if version in ("v3", "v4", "v5"):
            assert "ramsey_n_clamped" in exp.data.keys and hasattr(exp, "push_ramsey_shot")
        assert exp.p.ramsey_gap_policy == 3 and int(exp.p.ramsey_phase_policy) == phase_policy
        assert exp.p.update_raman_frequency_bool == 0 and exp.p.t_raman_pulse_random_bool == 0
        assert "ramsey_t_gap" in exp.data.keys and "ramsey_timing" in exp.data.keys
        # the floor the kernel will use is the production gap formula with the phase-set pretrigger
        assert exp.p.t_between_pulses_mu > exp.p.t_calculation_slack_compensation_mu
        harness._compile(cls, exp)
    finally:
        device_mgr.close_devices()
