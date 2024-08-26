from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.xvar('t_tof',np.linspace(20.,1000.,10)*1.e-6)
        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(1.,9.,10))
        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-7.,6.,10))
        self.p.frequency_tweezer_list = [70.e6]
        self.p.t_tof = 10.e-6
        self.p.N_repeats = 1

        self.p.t_magtrap_ramp = 75.e-3
        self.p.t_magtrap = 0.
        self.p.t_magtrap_rampdown = 75.e-3

        self.p.t_feshbach_field_rampup = 100.e-3
        self.p.t_feshbach_field_ramp = 15.e-3
        self.p.t_feshbach_field_ramp2 = 15.e-3

        self.p.t_mot_load = .75

        # self.xvar('v_lightsheet_paint_amp_max',np.arange(-7.,6.,10))

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.5,9.99,6))
        self.p.v_pd_lightsheet_rampup_end = 9.2

        # self.xvar('i_evap1_current',np.linspace(190.,194.,8))
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(1.,6.,6))
        self.p.v_pd_lightsheet_rampdown_end = 3.

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-6.,6.,10))
        self.p.v_tweezer_paint_amp_max = -2.

        # self.xvar('i_evap2_current',np.linspace(191.,194.,8))
        self.p.i_evap2_current = 191.9

        ## v_pd 6.5, paint amp 6. gives long lifetime at 200-300 kHz painting
        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(5.,9.9,10))
        self.p.v_pd_tweezer_1064_ramp_end = 8.2

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,200.,10)*1.e-3)
        self.p.t_tweezer_1064_ramp = .09

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.1,3.,8)) 
        self.p.v_pd_tweezer_1064_rampdown_end = .9

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.01,.1,8))
        self.p.t_tweezer_1064_rampdown = .02

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.04,.09,8)) 
        self.p.v_pd_tweezer_1064_rampdown2_end = .07

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.01,.15,8))
        self.p.t_tweezer_1064_rampdown2 = .11

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.16,.9,6)) 
        self.p.v_pd_tweezer_1064_rampdown3_end = .16

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.06,.4,4))
        self.p.t_tweezer_1064_rampdown3 = .35
        
        # self.xvar('i_evap3_current',np.linspace(191.,194.5,8))
        self.p.i_evap3_current = 193.

        # self.xvar('t_tweezer_hold',np.linspace(1.,1000.,10)*1.e-3)
        self.p.t_tweezer_hold = 10.e-3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_evap1_current)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

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
        
        # # feshbach field ramp to field 2
        # self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
        #                      i_start=self.p.i_evap1_current,
        #                      i_end=self.p.i_evap2_current)
        
        # self.tweezer.on(paint=False)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
        #                   v_start=0.,
        #                   v_end=self.p.v_pd_tweezer_1064_ramp_end,
        #                   paint=False,keep_trap_frequency_constant=False)
        
        # # lightsheet ramp down (to off)
        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
        #                      v_start=self.p.v_pd_lightsheet_rampdown_end,
        #                      v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # tweezer evap 1 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
        #                   v_start=self.p.v_pd_tweezer_1064_ramp_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=False,keep_trap_frequency_constant=True)

        # feshbach field ramp to field 3
        # self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_evap2_current,
        #                      i_end=self.p.i_evap3_current)
        
        # tweezer evap 2 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
        #                   paint=False,keep_trap_frequency_constant=True)
        
        # tweezer evap 3 with constant trap frequency
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
        #                   paint=False,keep_trap_frequency_constant=True,low_power=True)
        
        self.tweezer.off()
        self.lightsheet.off()
    
        delay(self.p.t_tof)
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