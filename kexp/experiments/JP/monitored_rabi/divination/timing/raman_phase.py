from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.util.artiq.async_print import aprint

T_CONV_MU = 30

from waxx.control.artiq.DDS import T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU

class feedback(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.DISPERSIVE)
        

        self.p.t_synchro_compensation_mu = T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU

        self.p.f0 = 1.e6
        self.p.f1 = 2.e6

        self.p.N_repeats = 6
        
        ###

        # self.scope = self.scope_data.add_siglent_scope("192.168.1.112", label='PD', arm=True)
        
        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.core.break_realtime()

        # t = now_mu()
        # t_pulse_start_mu = t + 50000

        # # self.raman.init(frequency_transition=self.p.f,
        # #                 fraction_power=0.99,
        # #                 phase_mode = 1,
        # #                 t_phase_origin_mu=t_pulse_start_mu)

        # at_mu(t_pulse_start_mu)
        # self.ttl.trigger.pulse(1.e-6)

        with parallel:
            self.dds.raman_80_plus.init()
            self.dds.raman_150_plus.init()


    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,setup_slm=False,init_imaging=False,init_sampler=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)