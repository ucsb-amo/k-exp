from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "scan lightsheet hold"

        ## Parameters

        self.p = self.params

        

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.mot_observe()