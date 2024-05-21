from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False,save_data=False)

        # self.p.v_pd_tweezer_1064_ramp_start = 
        # self.p.v_pd_tweezer_1064_ramp_start = 0.
        # self.p.v_pd_tweezer_1064_ramp_end = 4.5
        
        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,500.,10)*1.e-3)
        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,10.,100)*1.e-3)

        self.p.v_pd_lightsheet_rampup_start = 0.
        self.p.v_pd_lightsheet_rampup_end = 5.
        # self.xvar('t_lightsheet_rampup',np.linspace(10.,500.,10)*1.e-3)
        # self.xvar('t_lightsheet_rampup',np.linspace(10.,10.,100)*1.e-3)

        self.p.v_pd_tweezer_1064_rampdown_start = self.p.v_pd_tweezer_1064_ramp_end
        self.p.v_pd_tweezer_1064_rampdown_end = 0.

        # self.xvar('dummy',[0.]*200)
        # self.xvar('t_tweezer_1064_ramp',np.linspace(.01,.5,10))
        self.xvar('frequency_tweezer_array_width',np.linspace(.2e6,2.e6,5))
        self.p.t_delay = 400.e-3
        self.p.t_tweezer_1064_ramp = .2
        self.p.frequency_tweezer_array_width = .7e6
        self.p.n_tweezers = 2
        self.p.v_pd_tweezer_1064_ramp_start = 5.8
        self.p.v_pd_tweezer_1064_ramp_end = 2.1
   
        self.finish_build(shuffle=False)

    @kernel
    def scan_kernel(self):

        # self.tweezer.set_static_tweezers
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.ttl.pd_scope_trig_2.pulse(1.e-6)
        delay(100.e-3)
        
        # self.tweezer.vva_dac.set(v=3.)

        # self.tweezer.sw_ttl.on()
        # self.tweezer.awg_trg_ttl.pulse(t=1.e-6)
        self.tweezer.ramp(self.p.t_tweezer_1064_ramp,zero_integrator=True)
        # self.tweezer.on()
        delay(5.)
        # self.tweezer.ramp(t=500.e-3,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list)
        # self.tweezer.awg_trg_ttl.pulse(t=1.e-6)
        self.tweezer.off()
        # delay(1.0)

        # self.lightsheet.ramp(self.p.t_lightsheet_rampup)
        # self.lightsheet.off()
        delay(self.p.t_delay)

    @kernel
    def run(self):

        self.init_kernel()

        self.scan()