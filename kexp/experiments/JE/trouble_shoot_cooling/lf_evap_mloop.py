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

        # self.xvar('t_tof',np.linspace(10.,200.,10)*1.e-6)
        self.p.t_tof = 1000.e-6

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(.5,2.5,10))
        self.p.v_pd_lightsheet_rampdown_end = 1.1

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-6.5,0.,15))
        self.p.v_tweezer_paint_amp_max = -1.8

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(4.,9.2,10))
        self.p.v_pd_tweezer_1064_ramp_end = 9.2
        
        # self.xvar('i_lf_lightsheet_evap1_current',np.linspace(12.,18.,8))
        self.p.i_lf_lightsheet_evap1_current = 16.

        # self.xvar('i_lf_tweezer_load_current',np.linspace(12.,18.,8))
        self.p.i_lf_tweezer_load_current = 16.57

        # self.xvar('i_lf_tweezer_evap1_current',np.linspace(12.,15.,20))
        self.p.i_lf_tweezer_evap1_current = 16.

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.2,4.,15))
        self.p.v_pd_tweezer_1064_rampdown_end = .95

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(20.,180.,20)*1.e-3) 
        self.p.t_tweezer_1064_rampdown = 62.e-3  

        # self.xvar('i_lf_tweezer_evap2_current',np.linspace(12.,15.,20))
        self.p.i_lf_tweezer_evap2_current = 16.

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.05,.19,15))
        self.p.v_pd_tweezer_1064_rampdown2_end = .95

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(20.,500.,20)*1.e-3) 
        self.p.t_tweezer_1064_rampdown2 = 62.e-3 

        self.p.frequency_tweezer_list = [74.e6]
        a_list = [.145]
        self.p.amp_tweezer_list = a_list

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_evap1_current,pid_bool=False)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=0.,
                        v_xshim_current=0.)

        # feshbach field on, ramp up to field 1  
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_tweezer_load_current)
        
        # self.outer_coil.start_pid(i_pid = self.p.i_lf_lightsheet_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_lightsheet_evap1_current,
                             i_end=self.p.i_lf_tweezer_load_current)
        
        # load tweezers
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_lf_tweezer_evap1_current)

        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)

        self.outer_coil.ramp_supply(t=20.e-3,
                             i_start=self.p.i_lf_tweezer_evap1_current,
                             i_end=self.p.i_lf_tweezer_evap2_current)
        
        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)

        # delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        # self.outer_coil.stop_pid()
        # delay(50.e-3)

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