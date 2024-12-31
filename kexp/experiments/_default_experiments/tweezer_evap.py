from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.frequency_tweezer_list = [73.5e6,77.e6]

        self.p.amp_tweezer_list = [.41,.5]

        self.p.t_tof = 3200.e-6
        # self.xvar('t_tof',np.linspace(50.,1000.,5)*1.e-6)
        self.xvar('t_tof',[200*1.e-6]*3)

        # self.xvar('pfrac_d1_c_gm',np.linspace(.6,.99,8))
        # self.xvar('v_yshim_current_gm',np.linspace(.5,5.,20))

        # self.xvar('pfrac_d1_c_gm',np.linspace(.6,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.6,.99,8))

        # self.xvar('detune_d1_c_gm',np.linspace(1.,10.,8))
        # self.xvar('detune_d1_r_gm',np.linspace(1.,10.,8))

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.1,.5,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,.5,8))
        self.p.pfrac_c_gmramp_end = .271
        self.p.pfrac_r_gmramp_end = .15

        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,1.,8))
        # self.xvar('v_yshim_current_magtrap',np.linspace(3.,7.,8))

        # self.xvar('i_evap1_current',np.linspace(194.,198.,20))
        # self.p.i_evap1_current = 192.

        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(5.,8.5,10))
        self.p.v_pd_lightsheet_rampdown_end = 8.5
        # self.p.v_pd_lightsheet_rampdown_end = 7.1

        # self.xvar('i_evap2_current',np.linspace(196.5,199.,10))
        self.p.i_evap2_current = 198.2

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.012,.9,8))
        self.p.t_tweezer_1064_ramp = .38

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(4.,9.9,20))
        self.p.v_pd_tweezer_1064_ramp_end = 9.

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-.6,.2,10))
        self.p.v_tweezer_paint_amp_max = -1.8

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.012,.3,8))
        self.p.t_tweezer_1064_rampdown = .05

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(0.1,1.5,8))
        self.p.v_pd_tweezer_1064_rampdown_end = .7

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.04,.099,8))
        self.p.v_pd_tweezer_1064_rampdown2_end = .07

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.05,.4,8))
        self.p.t_tweezer_1064_rampdown2 = .15
 
        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.15,.5,10))
        self.p.v_pd_tweezer_1064_rampdown3_end = .4
        # self.p.v_pd_tweezer_1064_rampdown3_end = .35

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.3,8))
        self.p.t_tweezer_1064_rampdown3 = .18
        
        # self.xvar('i_evap3_current',np.linspace(196.5,199.,10))
        # self.p.i_evap3_current = 197.8
        self.p.i_evap3_current = 198.5

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.camera_params.amp_imaging = .08
        # self.xvar('amp_imaging',np.linspace(0.1,0.18,8))
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_evap3_current)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
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
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        self.lightsheet.off()
        
        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)

        # feshbach field ramp to field 3
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                             i_start=self.p.i_evap2_current,
                             i_end=self.p.i_evap3_current)
        
        self.outer_coil.start_pid()
        
        # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        # tweezer evap 3 with constant trap frequency
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.stop_pid()
        delay(10.e-3)

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