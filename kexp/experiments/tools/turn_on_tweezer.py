from artiq.experiment import *
from artiq.language import delay, now_mu, at_mu
from kexp import Base, img_types, cameras
from kexp.base.cameras import img_config

import numpy as np

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2, tweezer_vpd2_to_vpd1

class turn_on_imaging(EnvExperiment, Base):

    @portable(flags={"fast-math"})
    def tweezer_vpd2_to_vpd1_squeezer2(self,vpd_pid2) -> TFloat:
        return (vpd_pid2 - self.p.y_intercept) / self.p.slope

    def prepare(self):
        Base.__init__(self,
                      imaging_type=img_types.ABSORPTION,
                      setup_camera=False,
                      suppress_live_od=True)
        
        # self.p.y_intercept = -1.5
        # self.p.slope = 70.30864948083167
        self.p.y_intercept = -2.1376785723712772
        self.p.slope = 71.67500001330266

        # self.xvar('slope', np.linspace(69., 74., 11))

        # self.xvar('y_intercept', np.linspace(-4., 0., 11))
        
        self.configure_imaging_system(img_config.PID)

        # in case you want to use this to do triggering
        self.ttl.camera = self.ttl.andor 

        self.camera_params = cameras.andor

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(dds_off=False,
                         dds_set=False,
                         init_dds=False,
                         setup_awg=False,
                         setup_slm=False,
                         init_lightsheet=False,
                         init_shuttler=False)
        self.scan()

    @kernel
    def scan_kernel(self):
        self.tweezer.ramp(t=100.e-3, v_end=0.)
        
        self.tweezer.on()
        
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        delay(100.e-3)
        
        if self.p.t_tweezer_paint_rampdown == 0:
            self.tweezer.paint_amp_dac.set(-7.)
        else:
            v0 = self.tweezer.paint_amp_dac.v
            self.tweezer.paint_amp_dac.cubic_ramp(t=self.p.t_tweezer_paint_rampdown,
                                                  v_start=v0,
                                                  v_end=-7.,
                                                  n=100)
        
        self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_1,
                          v_start=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
                          v_end=self.p.v_pd_tweezer_squeeze_rampup_handoff_lp,
                          low_power=True, paint=False, keep_trap_frequency_constant=False,
                          cubic_ramp=True)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)

        vf = self.tweezer_vpd2_to_vpd1_squeezer2(self.p.v_pd_tweezer_squeeze_rampup_handoff_lp)
        if vf < 0.:
            vf = 0.
        if vf > 9.99:
            vf = 9.99

        self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_2,
                          v_start=vf,
                          v_end=self.p.v_pd_hf_tweezer_squeeze_power,
                          paint=False,keep_trap_frequency_constant=False,
                          cubic_ramp=True)
        
        self.core.wait_until_mu(now_mu())

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)