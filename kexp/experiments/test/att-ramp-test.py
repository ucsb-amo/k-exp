from artiq.experiment import *
from artiq.experiment import parallel, delay, delay_mu
import numpy as np
from kexp.control import DDS
from kexp.util.artiq import att_list_for_linear_power_ramp

class att_ramp(EnvExperiment):
    def build(self):
        self.core = self.get_device("core")

        self.dds1 = DDS(2,0,0.,30.)
        self.dds1.dds_device = self.get_device(self.dds1.name)
        self.dds1.cpld_device = self.get_device(self.dds1.cpld_name)
        self.ttl = self.get_device("ttl8")

        self.att_i = 1.
        self.att_f = 30.

        t = 3*ms

        dt = self.core.mu_to_seconds(2 * (self.dds1._t_att_delay_mu + 8 + 50))
        N = int(np.floor(t/dt))

        self.att_list = att_list_for_linear_power_ramp(self.att_i,self.att_f,N)

        self.t = t; self.dt = dt; self.N = N

    @kernel
    def ramp_dds_att(self,ddsobj,att_list,dt,N):
        for i in range(N):
            with parallel:
                ddsobj.set_dds(att_dB = att_list[i])
            delay(dt)

    @kernel
    def run(self):
        self.core.reset()
        self.dds1.cpld_device.init()
        delay(1*ms)
        self.dds1.dds_device.init()
        delay(1*ms)

        self.dds1.set_dds(freq_MHz = 40., att_dB = self.att_i)
        
        delay(1*s)
        self.ttl.on()
        self.dds1.on()
        self.ramp_dds_att(self.dds1,self.att_list,self.dt,self.N)
        # self.dds1.set_dds(att_dB = 30.)

        delay(1*s)

        self.ttl.off()
        self.dds1.off()
         