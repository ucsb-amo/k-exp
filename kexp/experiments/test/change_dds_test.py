from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,)
        
        self.xvar('dummy',[1]*1)

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel()
        self.dds.test.set_dds(frequency=1.e6)
        self.dds.test_2.set_dds(frequency=1.e6)
        self.dds.test_2.on()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)