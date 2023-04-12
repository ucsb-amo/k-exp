from artiq.experiment import *
from artiq.language.core import now_mu, at_mu
import numpy as np

from kexp.control import DDS

class dds_att_test(EnvExperiment):

    @rpc(flags={"async"})
    def printme(self,a):
        print(a)

    def build(self):

        self.core = self.get_device("core")

        self.dds1 = DDS(2,0,0.,30.)
        self.dds2 = DDS(2,1,0.,30.)

        self.dds1.cpld_device = self.get_device(self.dds1.cpld_name)
        self.dds2.cpld_device = self.get_device(self.dds2.cpld_name)

        self.dds1.dds_device = self.get_device(self.dds1.name)
        self.dds2.dds_device = self.get_device(self.dds2.name)

        self.ttl = self.get_device("ttl8")

        self.t = np.zeros(5, dtype=np.int64)

    @kernel
    def run(self):

        idx = 0

        self.core.reset()

        self.dds1.cpld_device.init()
        delay(1*ms)
        self.dds1.dds_device.init()
        self.dds2.dds_device.init()

        self.core.break_realtime()

        self.dds1.dds_device.set(20. * MHz)
        delay(1*ms)
        self.dds2.dds_device.set(20. * MHz)
        delay(1*ms)
        self.dds1.dds_device.set_att(20.)
        delay(1*ms)
        self.dds2.dds_device.set_att(2.)
        delay(1*ms)

        with parallel:
            self.dds1.on()
            self.dds2.on()

        delay(2*s)

        # self.dds1.dds_device.set_att(20.)
        self.t[idx] = now_mu(); idx+=1
        self.dds1.set_dds(freq_MHz = 60., att_dB=10.)
        # self.dds1.set_dds(att_dB=10.)
        # self.dds1.set_dds(freq_MHz=60.)
        delay_mu(self.dds1._t_set_delay_mu)
        self.dds2.set_dds(freq_MHz = 60., att_dB=10.)
        self.t[idx] = now_mu(); idx+=1
        self.ttl.on()

        self.t[idx] = now_mu(); idx+=1
        
        delay(2*s)

        self.ttl.off()
        self.dds1.off()
        self.dds2.off()

        self.core.break_realtime()

    def analyze(self):
        print('d')
        print(np.diff(self.t))