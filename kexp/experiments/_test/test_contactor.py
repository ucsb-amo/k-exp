from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)
        self.finish_build()
        
    @kernel
    def run(self):
        self.init_kernel()
        for _ in range(10):
            self.ttl.pd_scope_trig.on()
            self.ttl.inner_coil_contactor.on()
            delay(30*ms)
            self.ttl.inner_coil_contactor.off()
            self.ttl.pd_scope_trig.off()
            delay(1*s)