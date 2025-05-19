from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.coredevice.ttl import TTLInOut, TTLOut

class trap_frequency(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.ttl_in = self.get_device('ttl40')
        self.ttl_out = self.get_device('ttl48')

        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.core.reset()

        
        

    def analyze(self):
        pass