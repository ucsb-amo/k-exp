from artiq.experiment import *
from kexp.base.base import Base

class dds_set(EnvExperiment, Base):
    def build(self):
        Base.__init__(self,setup_camera=False)

    @kernel
    def run(self):
        self.init_kernel()

        self.switch_all_dds(1)