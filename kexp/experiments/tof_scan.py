from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True)
        self.xvar('t_tof',np.linspace(1000,12000,3)*1.e-6)
        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.mot(self.p.t_mot_load)
        self.release()
        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


        