from artiq.experiment import *
from kexp import Base
import os

import numpy as np

class mot_observe(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self, setup_camera = False)

    @kernel
    def run(self):
        
        self.init_kernel()
        delay(50*ms)
        self.mot_observe()

    def analyze(self):

        print("Done!")