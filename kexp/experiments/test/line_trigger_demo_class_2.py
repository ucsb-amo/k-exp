from artiq.experiment import *
from artiq.experiment import delay
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core, rtio_get_counter
from artiq.language.core import at_mu, now_mu
import numpy as np
from kexp.control.artiq.TTL import TTL, TTL_OUT, TTL_IN

class ttl_frame():
    def __init__(self,core):
        self.ttl_out = TTL_OUT(4)
        self.ttl_trig = TTL_OUT(5)
        self.ttl_in = TTL_IN(0)

        self.ttl_out.get_device(core)
        self.ttl_trig.get_device(core)
        self.ttl_in.get_device(core)

class line_trigger(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.core: Core

        self.ttl = ttl_frame(self)

        self.N = 10

    @kernel
    def run(self):

        self.core.reset()     
        self.core.break_realtime()

        delay(1.e-6)

        self.ttl_trig.pulse(1.e-6)  

        for _ in range(self.N):

            self.ttl_in.wait_for_line_trigger()
            self.ttl_out.pulse(1.e-3)

            self.core.break_realtime()
            self.ttl_in.clear_input_events()
            self.core.break_realtime()

        delay(1.e-3)