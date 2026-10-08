from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from base_expt_feedback_alt import FeedbackExptAlt as FeedbackExpt  # session copy: fast path + alternating extra gap (PLAN_gap_cycles.md)

class feedback(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)

        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1

        ### parameters

        self.p.feedback_fractional_initial_offset = 2.
        # self.xvar('feedback_fractional_initial_offset', np.linspace(0,4.,5))
        self.xvar('feedback_fractional_initial_offset', np.linspace(-2., 2., 5))
        self.p.N_repeats = 1 # session copy: 5-shot run-only test of the alternating-gap schedule

        self.p.N_warmup_shots = 3 # session copy: 3 warm-up shots (Base.pre_scan)
        self.p.t_calculation_slack_compensation_mu = np.int64(20000) # session copy: fast path, 20 us calc slack (bench 2026-09-29: 21 us min margin; 16 us floor)
        self.p.t_gap_cycle_extra_us = np.array([0., 20.]) # session copy: ALT2 = fast gap / fast gap + 20 us (= standard gap), alternating
        self.finish_prepare()

    @kernel
    def per_feedback_loop_end(self, idx):
        self.data.probabilities.put_data_1d(self.P0, idx+1)

    @kernel
    def per_scan_kernel_end(self):
        # print(self._flat_prob_counter)
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
