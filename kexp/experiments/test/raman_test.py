from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_killa(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.p.t_raman_pulse = 10.e-6
        self.p.f_raman_transition = 44.e6

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel()
        self.raman.set_transition_frequency(40.e6)
        self.raman.dds_minus.set_dds(amplitude=0.25)
        self.raman.dds_plus.set_dds(amplitude=0.25)
        self.raman.on()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)