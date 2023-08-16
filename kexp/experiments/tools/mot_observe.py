from artiq.experiment import *
from kexp import Base

import numpy as np

class mot_observe(EnvExperiment, Base):

    def build(self):
        Base.__init__(self, setup_camera = False)

    @kernel
    def run(self):
        
        self.init_kernel()
        delay(50*ms)
        self.mot_observe()

        self.dds.imaging_fake.set_dds(amplitude=0.188)
        self.dds.imaging_fake.on()

    def analyze(self):

        print("Done!")