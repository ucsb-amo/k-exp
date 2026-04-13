from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu, kernel, delay_mu
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ttl import TTLOut
import numpy as np\


from waxx.control.artiq.DDS import DDS
from kexp.util.db.device_db import device_db
import msvcrt

class dds(EnvExperiment):
    def prepare(self):
        self.core = self.get_device('core')
        self.ttl1 = self.get_device('ttl5')
        self.zotino0 = self.get_device('zotino0')

        self.dds0 = DDS(0,1,1.e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds0.get_devices(self)


        self.dds1 = DDS(0,2,0.71e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds1.get_devices(self)

        N = 300
        T = 1.24
        self.dt = T / N
        f0 = 30.e6
        self.f = f0 + f0 * np.linspace(-0.2,1.2,N)
        self.f = np.concatenate((self.f,np.flip(self.f)))

        self.idx = 0
        self.t_idx = 0
        self.t = np.zeros(2).astype(np.int64)

        self.df = 100.e3

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
        delay(1.e-6)

        self.dds0.on()
        self.dds1.on()

        PHASE_MODE_TRACKING = 2
        self.dds0.dds_device.set_phase_mode(PHASE_MODE_TRACKING)
        self.dds1.dds_device.set_phase_mode(PHASE_MODE_TRACKING)

        i = 0
        while True:

            t_pulse_start = (now_mu() & ~7) + 150000
            self.dds0.set_dds(frequency=self.f[i], amplitude=0.5,
                    t_phase_origin_mu=t_pulse_start)
            self.dds1.set_dds(frequency=self.f[len(self.f)//2], amplitude=0.5,
                    t_phase_origin_mu=t_pulse_start)

            at_mu(t_pulse_start)
            self.ttl1.pulse(1.e-6)
            
            delay(self.dt)
            i += 1
            i = i % len(self.f)

        self.core.break_realtime()


        
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