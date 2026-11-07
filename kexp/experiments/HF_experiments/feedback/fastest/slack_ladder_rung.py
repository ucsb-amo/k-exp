"""One rung of the slack ladder for the fastest feedback loop (README.md in this folder, "Slack test").

A timing test, not a measurement: the default loop (p.fast_path 2, deadline guard on) on atoms at grid size
GRID_SIZE and a fixed slack SLACK_US, adaptive drive on, the read settings of ExptParamsFeedback unchanged,
the per-step posterior record of the feedback runs (per_feedback_loop_end).
The only result is whether a shot underflowed. Copy this file into the night's run folder once per rung
(e.g. slack_m31_s20.py) and set the three constants there; never edit a queued copy.

Clean rung: the log shows "feedback: fastest loop" and "slack ... us as set", no RTIOUnderflow line, and the
run stored every planned shot (the "complete, N shots" line is the planned count, not the stored count).
"""
from artiq.experiment import *
from numpy import int64
import numpy as np

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt

GRID_SIZE = 31      # feedback_grid_size under test
SLACK_US = 20.0     # t_calculation_slack_compensation_mu of this rung, in us
N_SHOTS = 20        # 100 for the confirmation run at the floor


class fastest_slack_rung(EnvExperiment, FeedbackExpt):

    def prepare(self):
        FeedbackExpt.__init__(self, save_data=True, save_on_underflow=True, warmup_shots=3)

        self.p.feedback_grid_size = GRID_SIZE
        # this rung's slack, kept as set (fastest_slack_auto 0: never the table's value)
        self.p.fastest_slack_auto = 0
        self.p.t_calculation_slack_compensation_mu = int64(round(SLACK_US * 1.e3))
        # the bench's first-gap stretch, as the default loop runs it with the table slack: auto (-1) gives
        # none to a run that sets its own slack, so a rung sets it (organizer [040b75], 2026-11-05)
        self.p.fastest_first_gap_extra_mu = int64(5000)
        # adaptive drive: the frequency word and remesh the feedback runs use
        self.p.update_raman_frequency_bool = 1
        self.p.N_repeats = N_SHOTS

        self.xvar('feedback_fractional_initial_offset', np.zeros(1))

        self.finish_prepare()

    @kernel
    def per_feedback_loop_end(self, idx):
        # the per-step posterior record the feedback runs make (fbna_fb.py / fbna_na.py, 11-04): its time
        # is part of the step, so the rung times it too; it also lets read_rungs.py count flat and
        # degenerate steps (plain FeedbackExpt stores only the prior row)
        self.data.probabilities.put_data_1d(self.P0, idx+1)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__))
