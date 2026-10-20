from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from base_expt_feedback_bimodal import FeedbackExptBimodal as FeedbackExpt  # session copy: grid rule + alt gaps + bimodality drive rule (REPORT Addendum 8)

class feedback(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)

        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1

        ### parameters (user 2026-10-07 23:2x: 15 points, q = n + 0.4, 9 pulses per preparation)
        self.p.N_pulses = 12                                  # user 2026-10-08 ~09:xx: 12 pulses (cycle files too)
        self.p.feedback_grid_size = 15
        self.p.feedback_grid_alias_frac = 0.4
        self.p.feedback_grid_alias_order = -1
        self.p.feedback_grid_alias_T_ref = "long"
        self.p.t_calculation_slack_compensation_mu = np.int64(18000) # fast path, 15-pt bench 2026-10-07 23:44 (85431-85434): 14 us runs (min margin 11.2 us), 12 us underflows -> floor 14 + 4 us
        self.p.t_gap_cycle_extra_us = np.array([0., 15.])     # ALT2 gaps; 15 us from the X sweep for the rule grid (q_short 1.82; REPORT Addendum 5)
        self.p.feedback_remesh_threshold_Omega = 0.0          # remesh off
        self.p.bimodal_mode_ratio = 0.5                       # second mode >= half the max -> drive the mean
        self.p.bimodal_min_separation = 2

        step = self.grid_step_Omega()
        self.p.feedback_fractional_initial_offset = 2.
        # session copy: initial offsets on grid points, step * k, k = -7..7 (15 values, within the span)
        self.xvar("feedback_fractional_initial_offset", step * np.array([-6., -3., 3., 6.]))
        self.p.N_repeats = 1                                  # run-only test: 4 shots

        self.p.N_warmup_shots = 3
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
