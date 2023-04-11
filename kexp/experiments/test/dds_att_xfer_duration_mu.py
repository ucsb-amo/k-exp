from artiq.experiment import *
from artiq.experiment import delay, parallel, delay_mu
import numpy as np

class dds_att_xfer_duration(EnvExperiment):
    def build(self):

        self.core = self.get_device("core")
        self.dds1 = self.get_device("urukul2_ch0")

        self.spi = self.get_device("spi_urukul2")

        self.ttl = self.get_device("ttl8")
    
        self.xfer_t_mu = np.int64(1)

    @kernel
    def run(self):

        self.core.reset()

        self.dds1.cpld.init()
        delay(1*ms)
        self.dds1.init()

        self.core.break_realtime()

        self.dds1.set(frequency = 10 * MHz)
        self.dds1.set_att(5.)
        self.dds1.sw.on()

        delay(2*s)

        with parallel:
            self.dds1.set_att(1.)
            self.ttl.on()

        self.xfer_t_mu = self.spi.xfer_duration_mu
        
        delay(2*s)

        with parallel:
            self.ttl.off()
            self.dds1.sw.off()

    def analyze(self):
        print(f"set_att xfer duration = {self.xfer_t_mu} mu")
        print(f"set_att xfer duration = {self.core.mu_to_seconds(self.xfer_t_mu) * 1e6} us")