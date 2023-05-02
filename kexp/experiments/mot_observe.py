from artiq.experiment import *
from kexp import Base

import numpy as np

class mot_observe(EnvExperiment, Base):

    def build(self):
        Base.__init__(self, setup_camera = False)

    @kernel
    def run(self):
        
        self.init_kernel()
        self.mot_observe()

    def analyze(self):

        print("Done!")