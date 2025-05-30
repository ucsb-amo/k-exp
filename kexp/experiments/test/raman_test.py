from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_killa(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.p.t_raman_pulse = 10.e-6
        self.p.f_raman_transition = 44.e6
        self.xvar('dum',[0])

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.f_raman_transition)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)