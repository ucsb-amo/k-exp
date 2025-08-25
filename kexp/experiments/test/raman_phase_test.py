from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu, at_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class raman_phase_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.p.t_raman_pulse = 400.e-9
        self.p.N_repeats = 1
        # self.xvar('rel_phase',np.linspace(0.,np.pi,5))

        self.finish_prepare(shuffle=False)

    @kernel
    def get_time(self):
        self.t[self.t_idx] = now_mu()
        self.t_idx = self.t_idx + 1

    @kernel
    def scan_kernel(self):

        self.init_raman_beams(frequency_transition=0.,
                              t_phase_origin_mu=now_mu())

        self.raman.pulse(10.e-6)
        delay(3e-6)
        self.raman.set_phase(relative_phase=np.pi, global_phase=0.,
                            t_phase_origin_mu=now_mu(),
                            pretrigger=True)
        self.raman.pulse(10.e-6)

        delay(-10.e-6)
        self.ttl.test.pulse(1.e-6)
        

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