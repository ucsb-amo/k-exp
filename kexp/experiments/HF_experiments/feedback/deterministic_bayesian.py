from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.util.artiq.async_print import aprint

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt

class feedback_deterministic_bayesian(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)
        
        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 1

        self.p.N_repeats = 7
        self.p.N_pulses = 17 # number of steps of evolution
        
        ### parameters

        self.get_new_pulse_list()
        self.finish_prepare()

    @rpc 
    def get_new_pulse_list(self, seed=0):
        '''linearly spaced (rounded to grid)'''
        m = self.p.feedback_grid_size
        omega_grid = self.p.omega_guess_list

        sample_idx = np.rint(np.linspace(0, m - 1, self.p.N_pulses))
        sample_idx = np.clip(sample_idx, 0, m - 1).astype(int)
        self.p.omega_pulse_list = omega_grid[sample_idx]

    @kernel
    def per_feedback_loop_top(self, idx):
        self.omega_raman = self.p.omega_pulse_list[idx]

    @kernel
    def per_feedback_loop_end(self, idx):
        """
        Store the probabilities and the frequency mesh at each step. Note the
        use of +1 on the index, this accounts for the first row of each
        corresponding to before the first shot.
        """
        self.data.probabilities.put_data_1d(self.P0, i=idx+1)
    
    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)