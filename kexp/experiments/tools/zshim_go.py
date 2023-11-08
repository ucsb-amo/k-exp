from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
from kexp.control.artiq.TTL import TTL

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.test_dds_freqs = np.linspace(.1,5.,100) * 1.e6

    @kernel
    def run(self):
        self.init_kernel()
        for f in self.test_dds_freqs:
            self.ttl.pd_scope_trig.on()
            self.dds.test_dds_1.set_dds(frequency=f,
                                    amplitude=1.)
            self.dds.test_dds_1.on()
            delay(100.e-3)
            self.dds.test_dds_1.off()
            self.ttl.pd_scope_trig.off()
            delay(100.e-3)