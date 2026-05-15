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

        self.dds0 = DDS(5,3,1.e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds0.get_devices(self)

        self.dds1 = DDS(4,2,1.e6,0.5,device_db=device_db,dac_device=self.zotino0)
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

        # with parallel:
        self.dds0.cpld_device.init()
        self.dds1.cpld_device.init()
        delay(2.e-3)
        # self.dds0.dds_device.set_att(0.)
        # self.dds1.dds_device.set_att(0.)
        delay(2.e-3)
        self.dds0.dds_device.init()
        self.dds1.dds_device.init()
        delay(2.e-3)

        self.dds0.on()
        self.dds1.on()

        # with parallel:
        #     self.dds0.set_dds(init=True)
        #     self.dds1.set_dds(init=True)
        delay(1.e-6)

        # self.dds0.off()
        # self.dds1.off()
        self.dds0.set_phase_mode(0)
        self.dds1.set_phase_mode(0)

        # dt = T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU + int64(20)

        for _ in range(40):
        
            t0 = (now_mu() + 500500) & ~7

            with parallel:

                self.dds0.set_dds(frequency=88e6,
                                t_phase_origin_mu=t0,
                                phase=0.,
                                init=True)
                self.dds1.set_dds(frequency=88e6,
                                    t_phase_origin_mu=t0,
                                    phase=0.,
                                    init=True)
                
            delay_mu(10000000 & ~7)

            ts = now_mu()

            self.fast_set()

            # at_mu(ts)
            # delay_mu( (104+1256) & ~7 )
            delay_mu(91)

            self.ttl1.on()
            delay_mu(1000 & ~7)
            self.ttl1.off()

            delay_mu(np.int64(0.1*1.e9) & ~7)

        # print(p00)
        # print((p11 - p00))

    @kernel
    def fast_set(self):

        asf0 = self.dds0._asf
        asf1 = self.dds1._asf

        pow0 = 0
        pow1 = 0

        ftw0 = self.dds0.dds_device.frequency_to_ftw(1.e6)
        ftw1 = self.dds1.dds_device.frequency_to_ftw(1.e6)
        
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

        self.dds0.update_phase_at_set()
        self.dds1.update_phase_at_set()

    # @kernel
    # def fast_set(self):

    #     ftw0 = self.dds0.dds_device.frequency_to_ftw(1.e6)
    #     ftw1 = self.dds1.dds_device.frequency_to_ftw(1.e6)
        
    #     at_mu(now_mu() & ~7)
    #     with parallel:
    #             # self.dds0.dds_device.write64(_AD9910_REG_PROFILE0 + 7,
    #             #                 (asf0 << 16) | (pow0 & 0xffff), ftw0)
    #             # self.dds1.dds_device.write64(_AD9910_REG_PROFILE0 + 7,
    #             #                 (asf1 << 16) | (pow1 & 0xffff), ftw1)
    #             self.dds0.dds_device.set_ftw(ftw0)
    #             self.dds1.dds_device.set_ftw(ftw1)
    #     with parallel:
    #         with sequential:
    #             delay_mu(int64(self.dds0.dds_device.sync_data.io_update_delay))
    #             self.dds0.dds_device.cpld.io_update.pulse_mu(8)
    #         with sequential:
    #             delay_mu(int64(self.dds1.dds_device.sync_data.io_update_delay))
    #             self.dds1.dds_device.cpld.io_update.pulse_mu(8)
    #     at_mu(now_mu() & ~7)