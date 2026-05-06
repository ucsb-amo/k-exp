from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, at_mu, kernel, parallel, sequential
from artiq.coredevice.ad9910 import AD9910, _AD9910_REG_PROFILE0
from artiq.coredevice.ttl import TTLOut
import numpy as np
from numpy import int64

from waxx.control.artiq.DDS import DDS, T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU
from kexp.util.db.device_db import device_db

class dds(EnvExperiment):
    def prepare(self):
        self.core = self.get_device('core')
        self.ttl1 = self.get_device('ttl32')
        self.zotino0 = self.get_device('zotino0')

        # raman 150+
        self.dds0 = DDS(5,3,10.e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds0.get_devices(self)

        # raman 80-
        self.dds1 = DDS(4,2,10.e6,0.5,device_db=device_db,dac_device=self.zotino0)
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

        self.dds0.dds_device.sync_data.io_update_delay = np.int32(-2)
        self.dds1.dds_device.sync_data.io_update_delay = np.int32(0)

        self.core.reset()

        self.dds0.init()
        delay(1.e-3)
        self.dds1.init()
        delay(10.e-3)

        self.dds0.on()
        self.dds1.on()

        with parallel:
            self.dds0.set_dds(init=True)
            self.dds1.set_dds(init=True)
        delay(1.e-6)

        self.dds0.set_phase_mode(0)
        self.dds1.set_phase_mode(0)

        t = now_mu()
        
        t0 = now_mu() + 500500

        with parallel:
            self.dds0.set_dds(frequency=10e6,
                            t_phase_origin_mu=t0,
                            phase=0.,
                            init=True)
            self.dds1.set_dds(frequency=10e6,
                                t_phase_origin_mu=t0,
                                phase=0.,
                                init=True)
        
        delay(10.e-3)

        self.fast_set()
        self.dds0.reset_phase()
        self.dds1.reset_phase()
        p02 = self.dds0.get_phase()
        p12 = self.dds1.get_phase()

        delay_mu(104)
        t_update = now_mu()
        p0 = self.dds0.get_phase()
        p1 = self.dds1.get_phase()
        self.ttl1.pulse(100.e-9)
        
        at_mu(t_update + 100)
        p01 = self.dds0.get_phase()
        p11 = self.dds1.get_phase()

        # print(p00)
        print(np.array([p02,p0,p01,p12,p1,p11])/(2*np.pi))

    @kernel
    def fast_set(self):

        asf0 = self.dds0.dds_device.amplitude_to_asf(self.dds0.amplitude)
        asf1 = self.dds1.dds_device.amplitude_to_asf(self.dds1.amplitude)

        pow0 = 0
        pow1 = 0

        self.dds0._last_frequency = self.dds0.frequency
        self.dds1._last_frequency = self.dds1.frequency

        f0 = 5.e6
        f1 = 2.5e6

        ftw0 = self.dds0.dds_device.frequency_to_ftw(f0)
        ftw1 = self.dds1.dds_device.frequency_to_ftw(f1)
        
        at_mu(now_mu() & ~7)
        with parallel:
                self.dds0.dds_device.write64(_AD9910_REG_PROFILE0 + 7,
                                (asf0 << 16) | (pow0 & 0xffff), ftw0)
                self.dds1.dds_device.write64(_AD9910_REG_PROFILE0 + 7,
                                (asf1 << 16) | (pow1 & 0xffff), ftw1)
        with parallel:
            with sequential:
                delay_mu(int64(self.dds0.dds_device.sync_data.io_update_delay))
                self.dds0.dds_device.cpld.io_update.pulse_mu(8)
            with sequential:
                delay_mu(int64(self.dds1.dds_device.sync_data.io_update_delay))
                self.dds1.dds_device.cpld.io_update.pulse_mu(8)
        at_mu(now_mu() & ~7)