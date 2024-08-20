from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class lightsheet_from_magtrap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('t_tof',np.linspace(20.,1000.,15)*1.e-6)
        self.p.t_lightsheet_hold = .1
        self.p.t_tof = 800.e-6
        self.p.N_repeats = 8

        self.p.v_pd_lightsheet_rampup_end = 9.99

        self.p.magtrap_hold_then_lightsheet = 1.
        self.p.lightsheet_before_magtrap_ramp = 1.
        self.p.t_magtrap0_total = 0.
        self.p.t_lightsheet_rampup = 0.3
        # self.p.t_magtrap1_total = 1.
        self.p.t_magtrap_total = 1.
        # self.p.t_magtrap_hold

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(7.5,9.99,5))
        # self.xvar('v_lightsheet_paint_amp_max',np.arange(-7.,6.,1))
        # self.xvar('t_lightsheet_rampup',np.linspace(0.01,1.,10))
        self.xvar('t_magtrap_total',np.linspace(0.0,1.0,7))

        # self.xvar('t_lightsheet_rampup',np.linspace(0.01,1.,10))
        # self.xvar('t_magtrap',self.logspace(0.1,3.,15))

        # self.xvar('lightsheet_before_magtrap_ramp',[0,1])
        # self.xvar('magtrap_hold_then_lightsheet',[0,1])

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.start_magtrap()

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(self.p.t_magtrap0_total)

        # if self.p.lightsheet_before_magtrap_ramp:
        #     if self.p.magtrap_hold_then_lightsheet:
        #         delay(self.p.t_magtrap0_total - self.p.t_lightsheet_rampup)
        #     self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        #     if not self.p.magtrap_hold_then_lightsheet:
        #         delay(self.p.t_magtrap0_total - self.p.t_lightsheet_rampup)
        # else:
        #     delay(self.p.t_magtrap0_total)

        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_init,
                             i_end=self.p.i_magtrap_ramp_end,
                             n_steps=self.p.n_field_ramp_steps)
        delay(self.p.t_magtrap_total - self.p.t_magtrap0_total)
        
        # if not self.p.lightsheet_before_magtrap_ramp:
        #     if self.p.magtrap_hold_then_lightsheet:
        #         delay(self.p.t_magtrap1_total - self.p.t_lightsheet_rampup)
        #     self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        #     if not self.p.magtrap_hold_then_lightsheet:
        #         delay(self.p.t_magtrap1_total - self.p.t_lightsheet_rampup)
        # else:
        #     delay(self.p.t_magtrap1_total)

        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_ramp_end,
                             i_end=0.,
                             n_steps=self.p.n_field_ramp_steps)
        self.inner_coil.off()
        
        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()
    
        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        # self.lightsheet.off()

        self.outer_coil.discharge()

    @kernel
    def pre_scan(self):
        self.tweezer.on()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)