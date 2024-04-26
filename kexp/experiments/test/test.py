from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)

        self.f = 1.e3
        tf = 30.

        fs = 2*self.f
        N = np.int(fs * tf)
        
        self.t = np.linspace(0.,tf,N)
        
        self.v_pd = 0.5*np.sin(2*np.pi*self.f*self.t)+1.
        self.dt = tf / N

        # self.p.v_pd_tweezer_1064_ramp_start = 0.
        self.p.v_pd_tweezer_1064_ramp_start = 0.
        self.p.v_pd_tweezer_1064_ramp_end = 1.

        self.finish_build()

    @kernel
    def run(self):

        self.init_kernel()

        # self.tweezer.on()
        # for v in self.v_pd:
        #     self.tweezer.set_power(v_tweezer_vva=v)
        #     delay(self.dt)
        # self.tweezer.off()

        for _ in range(50):
            self.tweezer.ramp(0.25)
            self.tweezer.off()
            delay(0.25)

        # self.tweezer.on()
        # self.tweezer.set_power(v_tweezer_vva=2.5)