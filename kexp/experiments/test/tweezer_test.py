from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tweezer_test(EnvExperiment, Base):
    def build(self):
        Base.__init__(self)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.mot_observe()

        self.dds.tweezer.set_dds(v_pd=5.)
        self.dds.tweezer.on()

        self.lightsheet.set(paint_amplitude=0.,v_lightsheet_vva=1.0)

        self.lightsheet.on()