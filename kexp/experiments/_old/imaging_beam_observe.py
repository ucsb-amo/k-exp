from artiq.experiment import *
from kexp import Base

class imaging_beam_observe(EnvExperiment, Base):

    def build(self):
        Base.__init__(self, setup_camera = False)

    @kernel
    def run(self):
        
        self.init_kernel()
        delay(50*ms)
        self.dds.imaging.on()