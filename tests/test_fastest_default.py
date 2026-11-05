"""FeedbackExpt runs the fastest loop by default, falls back to the standard loop where the fastest
loop would not run the class as written, records the loop that ran, and both compile.

Compile only, against the real device db with every network client stubbed
(feedback_compile_harness): no core-device connection, nothing written outside pytest's temp dir.
~10 s per compile. Skipped without %db% / %code%.
"""
import os

import pytest

from feedback_compile_harness import EXPT, _build, _compile

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

FAST_OFF = EXPT.replace("        self.p.N_pulses = 3\n",
                        "        self.p.N_pulses = 3\n        self.p.fast_path = 0\n")

OVERRIDES_READ = EXPT.replace(
    "    @kernel\n    def run(self):",
    "    @kernel\n    def measurement(self, i):\n        return FeedbackExpt.measurement(self, i)\n\n"
    "    @kernel\n    def run(self):")

SCANS_IMAGING = EXPT.replace(
    "        self.xvar('feedback_fractional_initial_offset', np.array([0., 0.5, 1.]))\n",
    "        self.xvar('t_img_pulse', np.array([4.e-6, 5.e-6]))\n")

OWN_LOOP = '''
from artiq.experiment import *
from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
import numpy as np

class OwnLoop(EnvExperiment, FeedbackExpt):
    def prepare(self):
        FeedbackExpt.__init__(self, save_data=False, suppress_live_od=True)
        self.p.N_pulses = 3
        self.p.N_repeats = 1
        self.xvar('feedback_fractional_initial_offset', np.array([0., 0.5, 1.]))
        self.finish_prepare(shuffle=False)

    @kernel
    def feedback_loop(self, t_start_mu, update_raman_frequency=0, update_rabi_frequency=0,
                      include_photon_noise=1):
        self.feedback_loop_standard(t_start_mu, update_raman_frequency, update_rabi_frequency,
                                    include_photon_noise)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''


def _prepared(monkeypatch, tmp_path, text):
    return _build(monkeypatch, tmp_path, expt=text)


def test_the_default_is_the_fastest_loop_and_it_compiles(monkeypatch, tmp_path, capsys):
    from kexp.experiments.HF_experiments.feedback.fastest.fastest_loop import FastestLoop
    from waxx.control.raman_beams import RAMAN_AO_SINGLE
    cls, exp, dm = _prepared(monkeypatch, tmp_path, EXPT)
    try:
        assert int(exp.p.fast_path) == 2 and exp.fast_loop == 1
        assert exp._feedback_loop_kernels == [FastestLoop.feedback_loop_fastest]
        assert exp._fastest_shot_kernels == [FastestLoop.fastest_shot_setup]
        assert exp._fastest_cleanup_kernels == [FastestLoop.fastest_cleanup]
        assert int(exp.p.raman_ao_mode) == RAMAN_AO_SINGLE and int(exp.p.raman_fast_direct) == 1
        assert float(exp.p.frequency_raman_ao_reference) == float(exp.p.frequency_raman_transition)
        # the chained read starts 1-15 ns after the pulse end, on the 8 ns grid
        assert int(exp.fast_G_mu) % 8 == 0 and int(exp.fast_G_mu) > 0
        assert "fastest loop" in capsys.readouterr().out
        _compile(cls, exp)
    finally:
        dm.close_devices()


def test_fast_path_0_runs_the_standard_loop_unchanged(monkeypatch, tmp_path):
    from waxx.control.raman_beams import RAMAN_AO_BOTH
    cls, exp, dm = _prepared(monkeypatch, tmp_path, FAST_OFF)
    try:
        assert int(exp.p.fast_path) == 0 and exp.fast_loop == 0
        assert exp._feedback_loop_kernels == [type(exp).feedback_loop_standard]
        # the Raman pair is left as the standard loop has always run it
        assert int(getattr(exp.p, "raman_ao_mode", RAMAN_AO_BOTH)) == RAMAN_AO_BOTH
        assert not hasattr(exp, "fast_G_mu")
        _compile(cls, exp)
    finally:
        dm.close_devices()


@pytest.mark.parametrize("text, reason", [(OVERRIDES_READ, "overrides measurement"),
                                          (SCANS_IMAGING, "scans t_img_pulse")])
def test_a_class_the_fastest_loop_would_change_gets_the_standard_loop(monkeypatch, tmp_path, capsys,
                                                                      text, reason):
    cls, exp, dm = _prepared(monkeypatch, tmp_path, text)
    try:
        assert int(exp.p.fast_path) == 0 and exp.fast_loop == 0
        out = capsys.readouterr().out
        assert "the standard loop runs" in out and reason in out
    finally:
        dm.close_devices()


def test_a_class_with_its_own_loop_records_0_and_compiles(monkeypatch, tmp_path):
    cls, exp, dm = _prepared(monkeypatch, tmp_path, OWN_LOOP)
    try:
        assert int(exp.p.fast_path) == 0 and exp.fast_loop == 0
        _compile(cls, exp)
    finally:
        dm.close_devices()


def test_scanning_fast_path_is_refused_before_a_run_id(monkeypatch, tmp_path):
    text = EXPT.replace(
        "        self.xvar('feedback_fractional_initial_offset', np.array([0., 0.5, 1.]))\n",
        "        self.p.fast_path = 2\n        self.xvar('fast_path', np.array([0, 2]))\n")
    with pytest.raises(ValueError, match="fast_path cannot be scanned"):
        _prepared(monkeypatch, tmp_path, text)
