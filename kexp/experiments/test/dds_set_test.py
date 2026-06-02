from artiq.experiment import *
from artiq.experiment import delay
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.urukul import CPLD
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core, rtio_get_counter
from artiq.language.core import at_mu, now_mu
import numpy as np

class line_trigger(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.dds = self.get_device('urukul2_ch2')
        self.cpld = self.get_device('urukul2_cpld')

        self.core: Core
        self.dds: AD9910
        self.cpld: CPLD

    @kernel
    def run(self):

        self.core.reset()     

        self.cpld.init()

        self.dds.init()

        self.dds.set(frequency = 122.2650e6, amplitude=0.188)
        self.dds.set_att(0.)

        self.dds.sw.on()