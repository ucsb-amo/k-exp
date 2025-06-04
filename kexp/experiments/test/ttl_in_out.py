from artiq.experiment import *
from artiq.experiment import delay
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core

class trap_frequency(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.ttl_in = self.get_device('ttl0')
        self.ttl_out = self.get_device('ttl4')

        self.core: Core
        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut

    @kernel
    def run(self):
        self.core.reset()
        self.ttl_out.pulse(1.e-6)

    def analyze(self):
        pass