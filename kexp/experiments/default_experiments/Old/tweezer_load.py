from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.frequency_tweezer_list = [73.2e6,77.e6]

        a_list = [.45,.5]

        self.p.amp_tweezer_list = a_list

        self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(5.,9.5,10))

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(5.,9.,10))
        self.p.v_pd_tweezer_1064_ramp_end = 8.5

        
        # self.p.v_pd_lightsheet_rampdown_end = 1.6

        # self.xvar("v_pd_lightsheet_rampdown_end", np.linspace(1.,4., 10))
        # self.p.v_tweezer_paint_amp_max = -2.2
        # self.p.v_pd_tweezer_1064_rampdown_end = 1.

        self.p.t_tof = 10.e-6
        self.p.N_repeats = 1

        self.p.t_mot_load = 1.

        # self.xvar('t_tweezer_hold',np.linspace(1.,1000.,2)*1.e-3)
        # self.xvar('t_tof',np.linspace(10.,200.,5)*1.e-6)
    
        # self.xvar('dummy',[0,1])
        # self.p.t_tweezer_hold = 10.e-3

        self.camera_params.amp_imaging = .09
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_evap2_current)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap1_current,
                             i_end=self.p.i_evap2_current)
        
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        self.lightsheet.off()
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

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