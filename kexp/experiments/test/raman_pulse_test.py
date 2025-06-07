from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu, at_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class rabi_surf(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.p.t_raman_pulse = 400.e-9
        # self.xvar('t_raman_pulse',np.linspace(0.))
        # self.xvar('f',np.linspace(140.,160.,5)*1.e6)
        # self.xvar('amp',0.36 + 0.02 * np.linspace(-1,1,5))
        self.p.amp = 0.35
        # self.xvar('n',[0]*20)
        # self.xvar('f',np.linspace(130.,170.,20)*1.e6)
        self.p.N_repeats = 1
        self.xvar('x',[1])

        self.finish_prepare(shuffle=False)

    @kernel
    def get_time(self):
        self.t[self.t_idx] = now_mu()
        self.t_idx = self.t_idx + 1

    @kernel
    def scan_kernel(self):
        # set up raman beams
        self.raman.set_transition_frequency(self.p.frequency_raman_transition)

        # self.raman.dds_plus.set_dds(160.e6,amplitude=self.p.amp)
        # self.raman.dds_plus.set_dds(frequency=self.p.f,amplitude=self.p.amp)
        self.raman.dds_minus.set_dds(140.e6,amplitude=self.p.amp)

        delay(1*ms)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        delay(-1.68e-6)
        # self.raman.on()
        self.raman.dds_minus.on()
        delay(self.p.t_raman_pulse)
        # self.raman.off()
        self.raman.dds_minus.off()

        delay(0.05)
        # self.raman.pulse(self.p.t_raman_pulse,self.p.frequency_raman_transition)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,setup_slm=False,init_lightsheet=False,init_shuttler=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)