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

        self.p.v_pd_tweezer_1064_ramp_start = 0.
        self.p.v_pd_tweezer_1064_ramp_end = 4.
        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,500.,10)*1.e-3)
        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,10.,100)*1.e-3)

        self.p.v_pd_lightsheet_rampup_start = 0.
        self.p.v_pd_lightsheet_rampup_end = 8.88
        self.xvar('t_lightsheet_rampup',np.linspace(10.,500.,10)*1.e-3)
        # self.xvar('t_lightsheet_rampup',np.linspace(10.,10.,100)*1.e-3)

        self.finish_build(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.ttl.pd_scope_trig.pulse(1.e-6)
        
        # self.tweezer.ramp(self.p.t_tweezer_1064_ramp)
        # self.tweezer.off()
        # delay(1.0)

        self.lightsheet.ramp(self.p.t_lightsheet_rampup)
        self.lightsheet.off()
        delay(1.)

    @kernel
    def run(self):

        self.init_kernel()

        self.scan()