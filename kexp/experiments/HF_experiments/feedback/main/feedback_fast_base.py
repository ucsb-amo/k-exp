from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.experiments.HF_experiments.feedback.main.feedback_expt_base import FeedbackExpt

class feedback(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)
        
        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1
        
        ### parameters

        # self.p.feedback_fractional_initial_offset = 5.
        self.xvar('feedback_fractional_initial_offset', np.linspace(-5.9,5.9,5))
        
        self.p.N_repeats = 31
        self.p.N_pulses = 25 # number of steps of evolution

        self.p.feedback_guess_span_Omega = 6.

        self.finish_prepare()
    
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