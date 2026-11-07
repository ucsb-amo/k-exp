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
        # the lean posterior and the 5 us first-gap stretch, recorded and folded (2026-11-05)
        assert int(exp.p.fastest_posterior) == 1 and exp.hc_lean == 1
        assert int(exp.p.fastest_first_gap_extra_mu) == 5000 and int(exp.hc_first_gap_extra_mu) == 5000
        assert exp.hc_lean_need_std == 0          # the remesh is off by default: no std
        out = capsys.readouterr().out
        assert "fastest loop" in out and "lean posterior" in out and "first gap +5.000 us" in out
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


def test_the_fastest_loop_takes_the_measured_required_slack(monkeypatch, tmp_path, capsys):
    from kexp.experiments.HF_experiments.feedback.fastest import fastest_timing as ft
    cls, exp, dm = _prepared(monkeypatch, tmp_path, EXPT)
    try:
        assert int(exp.p.fastest_slack_auto) == 1
        assert int(exp.p.t_calculation_slack_compensation_mu) == ft.required_slack_mu(exp.p)
        # the spacing the run records is built from that slack
        assert int(exp.p.t_between_pulses_mu) == int(exp.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=exp.p.t_calculation_slack_compensation_mu,
            t_raman_pulse=exp.p.t_raman_pulse, t_img_pulse=exp.p.t_img_pulse,
            t_raman_pretrigger=exp.p.t_raman_set_pretrigger_mu, t_fifo_mu=exp.p.t_fifo_mu))
        assert "from the measured required slack" in capsys.readouterr().out
    finally:
        dm.close_devices()


@pytest.mark.parametrize("line, slack", [("        self.p.t_calculation_slack_compensation_mu = 20000\n", 20000),
                                         ("        self.p.fastest_slack_auto = 0\n", None)])
def test_a_slack_the_experiment_chose_is_kept(monkeypatch, tmp_path, line, slack):
    text = EXPT.replace("        self.p.N_pulses = 3\n", "        self.p.N_pulses = 3\n" + line)
    cls, exp, dm = _prepared(monkeypatch, tmp_path, text)
    try:
        assert int(exp.p.fast_path) == 2
        assert int(exp.p.fastest_slack_auto) == 0
        want = slack if slack is not None else exp._slack_default_mu
        assert int(exp.p.t_calculation_slack_compensation_mu) == want
        # the first-gap stretch is auto: none when the experiment keeps its own slack (its timeline as it was)
        assert int(exp.p.fastest_first_gap_extra_mu) == 0
    finally:
        dm.close_devices()


def test_the_standard_loop_keeps_the_params_slack(monkeypatch, tmp_path):
    cls, exp, dm = _prepared(monkeypatch, tmp_path, FAST_OFF)
    try:
        assert int(exp.p.fastest_slack_auto) == 0
        assert int(exp.p.t_calculation_slack_compensation_mu) == exp._slack_default_mu
    finally:
        dm.close_devices()


def test_a_grid_above_21_without_a_slack_test_is_refused_before_a_run_id(monkeypatch, tmp_path):
    from kexp.experiments.HF_experiments.feedback.fastest.fastest_timing import SlackUntested
    text = EXPT.replace("        self.p.N_pulses = 3\n",
                        "        self.p.N_pulses = 3\n        self.p.feedback_grid_size = 41\n")   # m 31/51 have ladders
    with pytest.raises(SlackUntested):
        _prepared(monkeypatch, tmp_path, text)


def test_the_slack_ladder_rung_keeps_its_slack_on_the_fastest_loop(monkeypatch, tmp_path):
    import pathlib
    rung = (pathlib.Path(__file__).parents[1] / "kexp/experiments/HF_experiments/feedback/fastest/"
            "slack_ladder_rung.py").read_text(encoding="utf-8")
    rung = rung.replace("save_data=True", "save_data=False, suppress_live_od=True")
    rung = rung.replace("N_SHOTS = 20 ", "N_SHOTS = 1 ")
    cls, exp, dm = _prepared(monkeypatch, tmp_path, rung)
    try:
        assert int(exp.p.fast_path) == 2 and int(exp.p.feedback_grid_size) == 31
        assert int(exp.p.fastest_slack_auto) == 0
        assert int(exp.p.t_calculation_slack_compensation_mu) == 20000
        _compile(cls, exp)
    finally:
        dm.close_devices()


LIBRARY_POSTERIOR = EXPT.replace("        self.p.N_pulses = 3\n",
                                 "        self.p.N_pulses = 3\n        self.p.fastest_posterior = 0\n")

OVERRIDES_P1 = EXPT.replace(
    "    @kernel\n    def run(self):",
    "    @portable(flags={'fast-math'})\n    def expected_photon_fraction(self, hz):\n"
    "        return FeedbackExpt.expected_photon_fraction(self, hz)\n\n"
    "    @kernel\n    def run(self):")


def test_the_library_posterior_on_the_fastest_loop_compiles(monkeypatch, tmp_path):
    cls, exp, dm = _prepared(monkeypatch, tmp_path, LIBRARY_POSTERIOR)
    try:
        assert int(exp.p.fast_path) == 2 and int(exp.p.fastest_posterior) == 0 and exp.hc_lean == 0
        _compile(cls, exp)
    finally:
        dm.close_devices()


def test_a_class_that_changes_an_inlined_helper_gets_the_library_posterior(monkeypatch, tmp_path, capsys):
    cls, exp, dm = _prepared(monkeypatch, tmp_path, OVERRIDES_P1)
    try:
        assert int(exp.p.fast_path) == 2 and int(exp.p.fastest_posterior) == 0
        assert "the library posterior runs" in capsys.readouterr().out
    finally:
        dm.close_devices()


@pytest.mark.parametrize("key, values", [("fastest_posterior", "[0, 1]"),
                                         ("fastest_first_gap_extra_mu", "[0, 5000]")])
def test_scanning_the_fastest_choices_is_refused(monkeypatch, tmp_path, key, values):
    text = EXPT.replace(
        "        self.xvar('feedback_fractional_initial_offset', np.array([0., 0.5, 1.]))\n",
        f"        self.xvar('{key}', np.array({values}))\n")
    with pytest.raises(ValueError, match=f"{key} cannot be scanned"):
        _prepared(monkeypatch, tmp_path, text)


def test_a_first_gap_off_the_8_ns_grid_is_refused(monkeypatch, tmp_path):
    text = EXPT.replace("        self.p.N_pulses = 3\n",
                        "        self.p.N_pulses = 3\n        self.p.fastest_first_gap_extra_mu = 5001\n")
    with pytest.raises(ValueError, match="multiple of 8"):
        _prepared(monkeypatch, tmp_path, text)


def test_a_first_gap_stretch_set_by_the_experiment_is_kept_with_its_own_slack(monkeypatch, tmp_path, capsys):
    text = EXPT.replace("        self.p.N_pulses = 3\n",
                        "        self.p.N_pulses = 3\n        self.p.fastest_slack_auto = 0\n"
                        "        self.p.fastest_first_gap_extra_mu = 5000\n")
    cls, exp, dm = _prepared(monkeypatch, tmp_path, text)
    try:
        assert int(exp.p.fastest_slack_auto) == 0 and int(exp.p.fastest_first_gap_extra_mu) == 5000
        assert "first gap +5.000 us (as set)" in capsys.readouterr().out
    finally:
        dm.close_devices()
