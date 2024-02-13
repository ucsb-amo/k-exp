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

        self.dac.outer_coil_supply.set(0.05)
        delay(50*ms)
        with parallel:
            self.ttl.outer_coil_igbt.on()
            self.ttl.pd_scope_trig.on()
        delay(15*ms)
        with parallel:
            self.ttl.outer_coil_igbt.off()
            self.ttl.pd_scope_trig.off()
        self.dac.outer_coil_supply.set(0.0)

        # self.dac.inner_coil_supply.set(1.2)
        # delay(50*ms)
        # with parallel:
        #     self.ttl.inner_coil_igbt.on()
        #     self.ttl.pd_scope_trig.on()
        # delay(15*ms)
        # with parallel:
        #     self.ttl.inner_coil_igbt.off()
        #     self.ttl.pd_scope_trig.off()
        # self.dac.inner_coil_supply.set(0.0)
        
    def analyze(self):

        print("Done!")