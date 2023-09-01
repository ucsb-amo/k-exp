from artiq.experiment import *
from kexp.base.base import Base

class Startup(EnvExperiment, Base):
    def build(self):
        '''
        Get core device, dds, zotino drivers.
        '''
        Base.__init__(self,setup_camera=False)

    @kernel
    def run(self):
        '''
        Init all devices, set dds to default values and turn on
        '''
        self.init_kernel()
        self.mot_observe()