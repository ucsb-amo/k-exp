from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu, kernel
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ttl import TTLOut
import numpy as np

class dds(EnvExperiment):
    def prepare(self):
        self.core = self.get_device('core')
        self.dds0 = self.get_device('urukul0_ch0')
        self.dds1 = self.get_device('urukul0_ch1')
        self.ttl = self.get_device('ttl4')
        self.ttl1 = self.get_device('ttl5')

        self.dds = [self.dds0, self.dds1]

        self.cpld = self.get_device('urukul0_cpld')

        self.f = 1.e6 + np.array([0., 0.])

        self.p = np.array([0.,0.5])

    @kernel
    def run(self):
        self.core.reset()

        self.cpld.init()
        self.dds0.init()
        self.dds1.init()

        for dds in self.dds:
            dds.sw.off()

        self.core.break_realtime()

        delay(10.e-3)

        t = now_mu()
        for i in range(len(self.dds)):
            dds = self.dds[i]
            # dds: AD9910
            self.p[i] = dds.set(frequency=self.f[i],amplitude=0.5)
            
        for dds in self.dds:
            dds.sw.on()

        delay(1.e-3)

        df = 100.e6

        with parallel:
            self.ttl.pulse(8.e-9)
            self.ttl1.on()
            self.dds[0].set(frequency=self.f[1] + df,
                            amplitude=0.5)
        
        delay_mu(80)
        self.ttl1.off()
        delay(10.e-3)
        