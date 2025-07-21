from artiq.experiment import *
from artiq.experiment import delay
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core, rtio_get_counter
from artiq.language.core import at_mu, now_mu
import numpy as np

class line_trigger(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.ttl_in = self.get_device('ttl40')
        self.ttl_out = self.get_device('ttl21')
        self.ttl_trig = self.get_device('ttl16')

        self.core: Core
        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut
        self.ttl_trig: TTLOut

    @kernel
    def run(self):

        self.core.reset()     

        self.ttl_trig.pulse(1.e-6)
        self.ttl_out.pulse(10.e-3)