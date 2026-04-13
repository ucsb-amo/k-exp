from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu, kernel
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ttl import TTLOut
import numpy as np

from waxx.control.artiq.DDS import DDS
from kexp.util.db.device_db import device_db

@rpc(flags={'async'})
def aprint(*args):
    print(*args)

class dds(EnvExperiment):
    def prepare(self):
        self.core = self.get_device('core')
        self.ttl1 = self.get_device('ttl5')
        self.zotino0 = self.get_device('zotino0')

        self.dds0 = DDS(0,1,3.e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds0.get_devices(self)

        self.dds1 = DDS(0,2,0.71e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds1.get_devices(self)

        self.f = [0.e6, 90.e6]

        self.t_idx = 0
        self.t = np.zeros(2).astype(np.int64)

    @kernel
    def get_slack(self):
        self.t[self.t_idx] = now_mu() - self.core.get_rtio_counter_mu()
        self.t_idx += 1

    def wait(self) -> TBool:
        input('press enter to continue')
        return True

    @kernel
    def run(self):
        self.core.reset()

        self.dds0.init()
        delay(1.e-6)
        self.dds1.init()
        delay(1.e-6)

        # t0 = 0
        # t1 = 0
        # t0 = self.dds0.dds_device.tune_io_update_delay()
        # t1 = self.dds1.dds_device.tune_io_update_delay()
        # aprint(t0,t1)

        delay(10.e-3)
        
        self.dds0.on()
        self.dds1.on()

        t_change_mu = np.int64(0)

        # self.dds0.off()
        # self.dds1.off()
        PHASE_MODE_CONTINUOUS = 0
        PHASE_MODE_ABSOLUTE = 1
        PHASE_MODE_TRACKING = 2
        self.dds0.dds_device.set_phase_mode(PHASE_MODE_TRACKING)
        self.dds1.dds_device.set_phase_mode(PHASE_MODE_TRACKING)

        p = 0.
        b = True
        for _ in range(1000):
            self.core.break_realtime()
            at_mu(now_mu())
            t = now_mu() + 10000
            self.dds0.set_dds(frequency=self.f[1], amplitude=0.5, t_phase_origin_mu=t)
            self.dds1.set_dds(frequency=self.f[1], amplitude=0.5, t_phase_origin_mu=t)
            # self.dds1.dds_device.set_phase_mode(PHASE_MODE_TRACKING)

            # self.dds1.set_phase_mode(1)
            delay(10.e-3)
            # p, t_change_mu = self.dds0.set_dds(frequency=self.f[1], amplitude=0.)
            p, t_change_mu = self.dds0.set_dds(frequency=self.f[0])
            self.dds1.set_dds(frequency=self.f[0])
            # self.dds1.set_dds(frequency=self.f[1], t_phase_origin_mu=t_pulse_start, phase=0., init=True)
            # print(t_change_mu)
            at_mu(t_change_mu)
            self.ttl1.pulse(1.e-6)

            self.core.wait_until_mu(now_mu())
            b = self.wait()
            

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
        