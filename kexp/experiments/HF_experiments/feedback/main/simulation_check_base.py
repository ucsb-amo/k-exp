from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.util.artiq.async_print import aprint


from kexp.experiments.HF_experiments.feedback.main.feedback_expt_base import FeedbackExpt

class feedback(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)
        
        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 1

        self.p.N_repeats = 1
        self.p.N_pulses = 12 # number of steps of evolution
        
        ### parameters

        # self.xvar('pulse_list_span_Omega', [-5.3,0.,10.])
        self.p.pulse_list_span_Omega = 3.
        # self.xvar('pulse_list_seed', np.linspace(1056, 15432, 5, dtype=np.int32))
        self.p.pulse_list_seed = 1055633

        self.get_new_pulse_list()
        self.finish_prepare()

    @kernel
    def per_feedback_loop_top(self, idx):
        self.omega_raman = self.p.omega_pulse_list[idx]
    
    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)