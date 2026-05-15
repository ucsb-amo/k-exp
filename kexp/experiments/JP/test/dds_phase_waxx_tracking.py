from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, at_mu, kernel, parallel, sequential
from artiq.coredevice.ad9910 import AD9910, _AD9910_REG_PROFILE0
from artiq.coredevice.ttl import TTLOut
import numpy as np
from numpy import int64

from waxx.control.artiq.DDS import DDS, T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU
from kexp.util.db.device_db import device_db

from waxx.util.artiq.async_print import aprint

T_AD9910_CONTINUOUS_MODE_UPDATE_LAG_MU = int64(104)

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

        self.t_phase_origin_mu = np.int64(0)

        self.T = 4.
        self.N = 50
        self.dt = self.T / self.N
        self.df = np.linspace(-1.e6,1.e6,self.N)
        self.df = np.concat([np.flip(self.df),self.df])
        print(self.df)

    @kernel
    def get_slack(self):
        self.t[self.t_idx] = now_mu() - self.core.get_rtio_counter_mu()
        self.t_idx += 1

    @kernel
    def run(self):
        self.core.reset()

        # with parallel:
        # self.dds0.init()
        # delay(1.e-3)
        # self.dds1.init()
        # delay(10.e-3)

        self.dds0.on()
        self.dds1.off()

        with parallel:
            self.dds0.set_dds(init=True)
            self.dds1.set_dds(init=True)
        delay(1.e-6)

        self.dds0.set_phase_mode(1)
        self.dds1.set_phase_mode(1)

        self.set_up_fast_frequency_update()

        delay(1.e-3)

        t = now_mu() & ~7
        t0 = (t + 30000) & ~7

        at_mu(t)

        dt = int64(self.dt * 1.e9)

        x = 0
        while x < 120:
            for i in range(len(self.df)):

                df = self.df[i]

                at_mu((t0 + dt - 1000) & ~7)

                t = now_mu() & ~7
                t0 = (t + 30000) & ~7
                # dt = T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU + int64(20)
                self.t_phase_origin_mu = t0
                self.fast_set(f0=27.214e6 + df,
                            f1=31.4e6 - df,
                            t_phase_origin_mu=t0,
                            dt_phase_origin_shift_mu=-int64(648))
                
                at_mu(t0 & ~7)
                self.ttl1.on()
                delay_mu(1000 & ~7)
                self.ttl1.off()

            x += 1

        self.clean_up_fast_frequency_update()

    @kernel
    def fast_set(self, f0, f1,
                 t_phase_origin_mu=int64(0),
                 dt_phase_origin_shift_mu=T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU):
        
        ftw0 = self.dds0.dds_device.frequency_to_ftw(f0)
        ftw1 = self.dds1.dds_device.frequency_to_ftw(f1)

        asf0 = self.dds0._asf
        asf1 = self.dds1._asf
        
        at_mu(now_mu() & ~7)

        dt = np.int32(now_mu()) - np.int32(t_phase_origin_mu - dt_phase_origin_shift_mu)
        a = np.int32(dt * self.dds0.dds_device.sysclk_per_mu / 2)
        
        pow0 = a * ftw0
        pow1 = a * ftw1

        with parallel:
                self.dds0.dds_device.write64(_AD9910_REG_PROFILE0 + 7,
                                (asf0 << 16) | (pow0 & 0xffff), ftw0)
                self.dds1.dds_device.write64(_AD9910_REG_PROFILE0 + 7,
                                (asf1 << 16) | (pow1 & 0xffff), ftw1)
        with parallel:
            with sequential:
                # delay_mu(int64(self.dds0.dds_device.sync_data.io_update_delay))
                self.dds0.dds_device.cpld.io_update.pulse_mu(8)

                self.dds0.frequency = f0
                self.dds0._ftw = ftw0

            # with sequential:
            #     delay_mu(int64(self.dds1.dds_device.sync_data.io_update_delay))
            #     self.dds1.dds_device.cpld.io_update.pulse_mu(8)

            #     self.dds1.frequency = f1
            #     self.dds1._ftw = ftw1
                
        at_mu(now_mu() & ~7)
    
    @kernel
    def set_up_fast_frequency_update(self):
        at_mu(now_mu() & ~7)
        with parallel:
            self.dds0.dds_device.set_cfr1(phase_autoclear=1)
            self.dds1.dds_device.set_cfr1(phase_autoclear=1)
        at_mu(now_mu() & ~7)

    @kernel
    def clean_up_fast_frequency_update(self):
        at_mu(now_mu() & ~7)
        with parallel:
            self.dds0.dds_device.set_cfr1()
            self.dds1.dds_device.set_cfr1()
        at_mu(now_mu() & ~7)

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