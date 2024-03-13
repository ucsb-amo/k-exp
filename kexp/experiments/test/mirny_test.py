from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)

        self.mirny = ADF5356
        self.mirny_cpld = Mirny

        self.mirny = self.get_device("mirny0_ch0")
        self.mirny_cpld = self.get_device("mirny0_cpld")

        self.freqs = np.linspace(455.e6,465.e6,1)

    @kernel
    def run(self):
        dt = 1.

        self.core.reset()

        self.mirny_cpld.init()
        # delay(1*ms)
        self.mirny.init()
        # self.mirny.sw.off()
        # self.core.break_realtime()
        self.mirny.set_att(20.)
        self.mirny.set_output_power_mu(3)
        delay(dt*s)
        for f in self.freqs:
            self.mirny.set_frequency(f)
            self.mirny.sw.on()
            delay(dt*s)
            self.mirny.sw.off()
        

        # for f in [460,461]:
        #     self.mirny.set_frequency(f*(1.e6))
        #     delay(dt)

