from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt

class feedback(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)
        
        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1
        
        ### parameters

        self.p.feedback_fractional_initial_offset = 8.
        # self.xvar('feedback_fractional_initial_offset', np.linspace(0,4.,5))
        
        self.p.N_repeats = 3
        self.p.N_pulses = 20 # number of steps of evolution

        self.p.feedback_guess_span_Omega = 10.

        self.finish_prepare()

        # self.probabilities = np.zeros((*self.xvardims, self.p.N_pulses + 1, self.p.feedback_grid_size))
        self.data.probabilities = self.data.add_data_container((self.p.N_pulses + 1, self.p.feedback_grid_size))
        self.data.probabilities[0, :] = self.P0

    @kernel
    def per_feedback_loop_end(self, idx):
        self.data.probabilties.put_data_1d(self.P0, idx+1)
    
    @kernel
    def per_scan_kernel_end(self):
        print(self._flat_prob_counter)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)