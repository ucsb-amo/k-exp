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

        self.p.N_repeats = 11
        
        ### parameters

        # hypothesis grid (feedback_grid_convention 2; defaults in expt_params_feedback):
        # full width in Hz, initial offset as a fraction of the largest allowed (-1..1),
        # grid shift in grid steps (-1/2..1/2)
        # self.p.frequency_feedback_grid_full_span = 12.75e3
        # self.xvar('feedback_fractional_initial_offset', np.linspace(-1., 1., 8))
        # self.xvar('feedback_grid_shift', np.linspace(-0.5, 0.5, 5))

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
        self.end(expt_filepath)