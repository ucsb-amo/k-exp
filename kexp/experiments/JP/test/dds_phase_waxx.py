from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu, kernel
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ttl import TTLOut
import numpy as np

from waxx.control.artiq.DDS import DDS
from kexp.util.db.device_db import device_db

class dds(EnvExperiment):
    def prepare(self):
        self.core = self.get_device('core')
        self.ttl1 = self.get_device('ttl5')
        self.zotino0 = self.get_device('zotino0')

        self.dds0 = DDS(0,0,1.e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds0.get_devices(self)


        self.dds1 = DDS(0,1,0.71e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds1.get_devices(self)

        self.f = np.linspace(1.,3.,100)*1.e6
        self.f = np.concatenate((self.f,np.flip(self.f)))

        self.t_idx = 0
        self.t = np.zeros(2).astype(np.int64)

    @kernel
    def get_slack(self):
        self.t[self.t_idx] = now_mu() - self.core.get_rtio_counter_mu()
        self.t_idx += 1

    @kernel
    def run(self):
        self.core.reset()

        self.dds0.init()
        delay(1.e-6)
        self.dds1.init()
        # for _ in range(1):
        #     self.dds0.set_dds(init=True)
            # self.dds1.set_dds(init=True)
        delay(1.e-6)

        # self.dds0.off()
        # self.dds1.off()
        PHASE_MODE_CONTINUOUS = 0
        PHASE_MODE_ABSOLUTE = 1
        PHASE_MODE_TRACKING = 2
        self.dds0.dds_device.set_phase_mode(2)
        self.dds1.dds_device.set_phase_mode(2)

        while True:
            for i in range(len(self.f)):
                t_pulse_start = now_mu() + 50000
                self.dds0.set_dds(frequency=2*self.f[i], amplitude=0.5, init=True,
                                   t_phase_origin_mu=t_pulse_start)
                self.dds1.set_dds(frequency=np.pi*self.f[i], amplitude=0.5, init=True,
                                   t_phase_origin_mu=t_pulse_start)

                at_mu(t_pulse_start)
                self.ttl1.pulse(1.e-6)
                
                delay(10.e-3)

        
        # self.dds0.set_dds(frequency=3e6, t_phase_origin_mu=t_pulse_start, phase=0., init=True)
        # # delay(5.e-6)
        # self.dds1.set_dds(frequency=1.2e6, t_phase_origin_mu=t_pulse_start, phase=0., init=True)

        # delay(10.e-6)
        
        # at_mu(t_pulse_start)
        # p00 = self.dds0.update_phase()/(np.pi)
        # p11 = self.dds1.update_phase()/(np.pi)

        # self.ttl1.pulse(1.e-6)

        # print(p00, p11, (p11 - p00))

    # def analyze(self):
        # print(self.t)
        # t = np.zeros_like(self.t)
        # t[1:] = np.diff(self.t)
        # print(t)