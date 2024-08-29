from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

from kexp.util.artiq.async_print import aprint


class lightsheet_mloop_results_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        self.p.t_tof = 500.e-6
        self.xvar('use_mloop_params',[0,1])

        self.p.N_repeats = 1

        self.p.t_mot_load = .5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        if self.p.use_mloop_params:
        #     self.p.t_lightsheet_rampup = 0.45
            self.p.i_magtrap_ramp_end = 120.0
        #     self.p.t_magtrap_ramp = 0.1
        #     self.p.t_magtrap = 0.0
        #     self.p.t_magtrap_rampdown = 0.09
        aprint

        self.set_high_field_imaging(i_outer = self.p.i_evap2_current)
        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap_and_load_lightsheet()
        
        delay(self.p.t_lightsheet_hold)
        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp(t=self.p.t_feshbach_field_rampup,
                            i_start=0.,
                            i_end=self.p.i_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                            v_start=self.p.v_pd_lightsheet_rampup_end,
                            v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_evap1_current,
                            i_end=self.p.i_evap2_current)

        self.lightsheet.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()
        self.outer_coil.off()

        self.outer_coil.discharge()


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