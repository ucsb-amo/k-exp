from artiq.experiment import *
from kexp import Base

class dds_set(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self,setup_camera=False)

    @kernel
    def run(self):
        self.init_kernel()

        self.switch_all_dds(1)