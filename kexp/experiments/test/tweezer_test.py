from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tweezer_test(EnvExperiment, Base):
    def build(self):
        Base.__init__(self)

        self.t_time = 300 * s

    @kernel
    def run(self):
        
        self.init_kernel()

        self.tweezer_trap(self.t_time)