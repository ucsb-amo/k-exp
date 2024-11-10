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

        # self.xvar('frequency_detuned_imaging',np.arange(220.,290.,2.)*1.e6)
        
        # self.p.frequency_detuned_imaging = 302.e6 # i-13.8
        # self.p.frequency_detuned_imaging = 438.e6 # i-13.4
        # self.p.frequency_detuned_imaging = 300.e6 # i-14.5
        self.p.frequency_detuned_imaging = 262.e6 # i-19.6
        
        # self.xvar('beans',[0.]*100)
        
        self.p.frequency_tweezer_list = [78.e6]

        # ass = np.linspace(.2,.7,10)
        # a_lists = [[ass1] for ass1 in ass]

        # self.xvar('amp_tweezer_list',a_lists)

        a_list = [.5]
        self.p.amp_tweezer_list = a_list
        self.p.amp_tweezer_auto_compute = False

        self.p.t_mot_load = 1.5

        self.xvar('t_tof',np.linspace(500.,1600.,10)*1.e-6)

        self.p.t_tof = 1500.e-6
        self.p.N_repeats = 20

        self.p.pfrac_c_gmramp_end = 0.32
        self.p.pfrac_r_gmramp_end = 0.32

        self.p.t_magtrap_ramp = .5
        # self.p.t_magtrap = 0.
        self.p.t_magtrap_rampdown = 200.e-3

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.5,9.9,6))
        # self.p.v_pd_lightsheet_rampup_end = 9.9
        
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(5.,8.,10))
        self.p.v_pd_lightsheet_rampdown_end = 6.33

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(0.,6.,6))
        self.p.v_tweezer_paint_amp_max = 6.

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(4.,9.9,10))
        # self.p.v_pd_tweezer_1064_ramp_end = 8.2
        # self.p.v_pd_tweezer_1064_ramp_end = 9.9

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,800.,20)*1.e-3)
        self.p.t_tweezer_1064_ramp = .17

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.1,3.,8)) 
        self.p.v_pd_tweezer_1064_rampdown_end = .9

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.01,.2,20))
        self.p.t_tweezer_1064_rampdown = .04

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.04,.099,8)) 
        # self.p.v_pd_tweezer_1064_rampdown2_end = .1
        self.p.v_pd_tweezer_1064_rampdown2_end = .05

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.02,.55,8))
        self.p.t_tweezer_1064_rampdown2 = .24
        # self.p.t_tweezer_1064_rampdown2 = .5

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(1.,4.,8))
        self.p.v_pd_tweezer_1064_rampdown3_end = 1.4

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.05,.3,8))
        self.p.t_tweezer_1064_rampdown3 = .15
        
        # self.xvar('i_evap3_current',np.linspace(192.,194.,8))
        # self.p.i_evap3_current = 192.3

        # self.xvar('i_lf_evap1_current',np.linspace(12.,15.,20))
        # self.xvar('i_lf_evap2_current',np.linspace(12.6,14.,8))
        # self.xvar('i_lf_evap3_current',np.linspace(12.5,14.,8))
        self.p.i_lf_evap1_current = 14.2
        self.p.i_lf_evap2_current = 13.1
        self.p.i_lf_evap3_current = 13.5

        self.p.i_spin_mixture = 19.6

        # self.camera_params.amp_imaging = .12
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.dds.ry_405.set_dds(set_stored=True)
        self.dds.ry_405.on()

        # self.set_high_field_imaging(i_outer=self.p.i_evap2_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.outer_coil.on()
        self.outer_coil.set_voltage(v_supply=0.)
        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        
        self.outer_coil.v_control_dac.linear_ramp(t=100.e-3,v_start=0.,v_end=1.,n=50)
        delay(30.e-3)
        self.outer_coil.ramp(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_evap1_current,
                             i_end=self.p.i_lf_evap2_current)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)

        # feshbach field ramp to field 3
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp2,
                             i_start=self.p.i_lf_evap2_current,
                             i_end=self.p.i_lf_evap3_current)
        
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

        self.outer_coil.ramp(t=12.e-3,
                             i_start=self.p.i_lf_evap3_current,
                             i_end=self.p.i_spin_mixture)
        
        delay(10.e-3)
        
        self.lightsheet.off()
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)