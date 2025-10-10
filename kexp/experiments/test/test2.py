from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class test2(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=False)
        self.xvar('p1',np.linspace(0.,10.,100))
        self.finish_prepare(shuffle=True)
    
    @kernel
    def scan_kernel(self):
        self.power_down_cooling()
        self.abs_image()
        delay(0.5*s)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)