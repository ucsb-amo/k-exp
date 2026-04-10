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


        self.dds1 = DDS(0,1,1.e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds1.get_devices(self)

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
        self.dds0.off()
        self.dds1.off()
        self.dds0.set_phase_mode(1)

        self.get_slack()
        self.dds0.set_dds(init=True)
        self.get_slack()
        # self.dds1.set_phase_mode(1)
        # self.dds1.set_dds(init=True)
        # self.get_slack()

        self.dds0.on()
        self.ttl1.pulse(1.e-6)

    def analyze(self):
        print(self.t)
        t = np.zeros_like(self.t)
        t[1:] = np.diff(self.t)
        print(t)