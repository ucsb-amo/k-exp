from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from base_expt_feedback_grid import FeedbackExptGrid as FeedbackExpt  # session copy: grid from the pulse period (DESIGN_grid_rule.md section 5)

class feedback(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)

        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1

        ### parameters -- ONE-PERIOD GRID TEST: single (fast) gap, 15 points spanning exactly one
        ### comb period 1/T around the initial drive: q = 0 + 1/14 -> 14 steps = 1/T
        self.p.N_pulses = 9
        self.p.feedback_grid_size = 15
        self.p.feedback_grid_alias_frac = 1.0 / 14.0
        self.p.feedback_grid_alias_order = 0
        self.p.feedback_grid_alias_T_ref = "long"
        self.p.t_calculation_slack_compensation_mu = np.int64(18000) # fast path, 15-pt bench 2026-10-07 23:44: floor 14 us + 4
        self.p.t_gap_cycle_extra_us = np.array([0.])          # no alternation: one period only
        self.p.feedback_remesh_threshold_Omega = 0.0

        step = self.grid_step_Omega()
        self.p.feedback_fractional_initial_offset = 2.
        # initial offsets on grid points inside the one-period span: step * k, k = -6..6 (13 points)
        self.xvar('feedback_fractional_initial_offset', step * np.arange(-6., 7.))
        self.p.N_repeats = 5

        self.p.N_warmup_shots = 20
        self.finish_prepare()

    @kernel
    def per_feedback_loop_end(self, idx):
        self.data.probabilities.put_data_1d(self.P0, idx+1)

    @kernel
    def per_scan_kernel_end(self):
        pass

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, notify=False, restart_monitor=False)
