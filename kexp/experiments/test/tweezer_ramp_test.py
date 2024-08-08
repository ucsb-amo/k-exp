from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint
from artiq.language.core import kernel_from_string, now_mu

RPC_DELAY = 10.e-3

import numpy as np

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)

        # self.xvar('dummy',[1]*30)
        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.98,0.1))
        self.p.v_pd_tweezer_1064_rampdown2_end = 0.098

        self.finish_build(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.tweezer.on()
        self.tweezer.ramp(100.e-3,
                          v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list,
                          paint=True)
        # delay(10.e-3)
        self.tweezer.ramp(500.e-3,
                          v_ramp_list=self.p.v_pd_tweezer_1064_rampdown2_list,
                          paint=True,
                          low_power=False)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.ramp(100.e-3,
                            v_ramp_list=self.p.v_pd_tweezer_1064_rampdown3_list,
                            paint=True,
                            low_power=True)
        self.tweezer.off()

        delay(100*ms)

    @kernel
    def run(self):

        self.init_kernel()
        self.scan()