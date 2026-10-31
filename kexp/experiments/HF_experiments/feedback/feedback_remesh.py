from artiq.experiment import *
import numpy as np

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt

class feedback_remesh(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                        save_data=True,
                        save_on_underflow=True)
        
        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1
        
        ### parameters

        # hypothesis grid: the params defaults (feedback_grid_convention 2)
        # self.p.frequency_feedback_grid_full_span = 1274.6e3 # 10 Omega at t_pi 3.9229 us, the old +-5 Omega
        # self.p.feedback_guess_span_Omega = 5. # convention 1

        # initial offset as a fraction of the largest allowed: the old 2. Omega was 4 of a
        # largest 9.5 steps on the 21-point +-5 Omega grid
        self.p.feedback_fractional_initial_offset = 4. / 9.5
        # self.xvar('feedback_fractional_initial_offset',
        #           np.array([-8., -4., 0., 4., 8.]) / 9.5) # was linspace(-4.,4.,5) Omega

        self.p.N_repeats = 5

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

    @kernel
    def per_feedback_loop_end(self, idx):
        # +1: row 0 holds the prior
        self.data.probabilities.put_data_1d(self.P0, i=idx+1)
        self.data.omega_raman_mesh.put_data_1d(self.omega_guess_list, i=idx+1)
    
    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)