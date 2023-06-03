from artiq.experiment import *
from kexp import Base

from artiq.experiment import delay, delay_mu, parallel, sequential

class dds_d1_change(EnvExperiment,Base):
    def build(self):
        Base.__init__(self,setup_camera=False)

    @kernel
    def run(self):
        self.init_kernel()
        self.dds_test(self.dds.d1_3d_r)

    @kernel
    def dds_test(self,dds):
        dds.set_dds_gamma(delta = 0.)
        dds.on()
        delay(2*s)
        dds.set_dds_gamma(delta = 1.)
        delay(2*s)
        dds.off()