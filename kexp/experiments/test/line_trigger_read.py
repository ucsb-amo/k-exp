from artiq.experiment import *
from artiq.experiment import delay
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core
from artiq.language.core import at_mu
from artiq.coredevice.sampler import Sampler

class trap_frequency(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.ttl_in = self.get_device('ttl0')
        self.ttl_out = self.get_device('ttl4')

        self.sampler = self.get_device("sampler0")
        self.sampler: Sampler
        self.data = np.zeros(8)

        self.readings = np.zeros(500)

        self.core: Core
        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut

    @kernel
    def run(self):
        self.core.reset()

        for i in range(len(self.data)):
            self.sampler.set_gain_mu(i,0)

        self.core.break_realtime()

        for i in range(len(self.readings)):
            self.sampler.sample(self.data)
            self.readings[i] = self.data[0]
            delay(50.e-6)
        
    def analyze(self):
        print(np.sum(self.readings > 2.))