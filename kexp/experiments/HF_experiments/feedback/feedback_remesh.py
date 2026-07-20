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

        self.p.feedback_fractional_initial_offset = 2.
        # self.xvar('feedback_fractional_initial_offset', np.linspace(-4.,4.,5))
        
        self.p.N_repeats = 5

        self.p.feedback_guess_span_Omega = 5.

        self.p.feedback_remesh_threshold_Omega = 0.5
        # self.xvar('feedback_remesh_threshold_Omega', np.linspace(0.0,0.825,7))
        self.p.remesh_interpolate_posterior = 1
        self.p.remesh_interpolate_states = 1

        self.p.remesh_after_n_good_shots = 3
        self.p.remesh_reset_counter_threshold_fraction = 2.
        self.p.n_initial_shots_before_remesh = 2

        self.p.remesh_scale_factor = 0.4
        # self.xvar('remesh_scale_factor', np.linspace(0.325,0.9,6))
        self.p.remesh_threshold_scale_factor = 0.75

        self.finish_prepare()

        self.omega_raman_mesh = np.zeros((*self.xvardims, self.p.N_pulses, self.p.feedback_grid_size))
        self.probabilities = np.zeros((*self.xvardims, self.p.N_pulses + 1, self.p.feedback_grid_size))
        
        for i in range(self.probabilities.shape[0]):
            self.probabilities[i, 0, :] = self.P0

    @kernel
    def per_feedback_loop_end(self, idx):
        """Called at the end of each feedback loop iteration.  Can be used to store data
        to host or update parameters."""
        shot_idx = self.scan_xvars[0].counter
        for i in range(self.m):
            self.probabilities[shot_idx, idx + 1, i] = self.P0[i]
            self.omega_raman_mesh[shot_idx, idx, i] = self.omega_guess_list[i]
    
    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        self.store_mesh_to_params()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)