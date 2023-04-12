from artiq.experiment import *
import numpy as np

class dds_att_test(EnvExperiment):
    def build(self):

        self.core = self.get_device("core")
        self.dds1 = self.get_device("urukul2_ch0")
        self.dds2 = self.get_device("urukul2_ch1")

        print(self.dds1.sync_data.io_update_delay)

        self.ttl = self.get_device("ttl8")

    @kernel
    def run(self):

        self.core.reset()

        self.dds1.cpld.init()
        delay(1*ms)
        self.dds1.init()
        self.dds2.init()

        self.core.break_realtime()

        self.dds1.set(frequency = 10. * MHz)
        self.dds2.set(frequency = 10. * MHz)

        self.dds1.set_att(10.)
        self.dds2.set_att(2.)

        with parallel:
            self.dds1.sw.on()
            self.dds2.sw.on()

        delay(2*s)

        with parallel:
            self.dds1.set_att(15.)
            self.ttl.on()
        
        delay(2*s)

        with parallel:
            self.ttl.off()
            self.dds1.sw.off()
            self.dds2.sw.off()

        self.core.break_realtime()
        print(self.dds1.sync_data.io_update_delay)