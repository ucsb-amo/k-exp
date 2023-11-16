from artiq.experiment import *
import numpy as np

class drtio_test(EnvExperiment):
    def build(self):
        self.core = self.get_device("core")
        self.ttl = self.get_device("ttl24")
        self.dds = self.get_device("urukul3_ch0")
        self.cpld = self.get_device("urukul3_cpld")
        self.a = 1

    @kernel
    def run(self):
        self.core.reset()
        self.cpld.init()
        self.dds.init()

        self.core.break_realtime()
        self.dds.set(frequency=1.e6)
        self.dds.sw.on()
        delay(1*ms)
        self.dds.sw.off()
        # for _ in range(300):
        #     self.ttl.on()
        #     delay(10*us)
        #     self.ttl.off()
        #     delay(10*us)