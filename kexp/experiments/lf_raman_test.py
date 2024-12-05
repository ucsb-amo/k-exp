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

        self.p.imaging_state = 1.

        # self.xvar('frequency_detuned_imaging',np.arange(240.,550.,6)*1.e6)
        
        # self.p.frequency_detuned_imaging = 322.e6 # i-17.8
        # self.p.frequency_detuned_imaging = 320.e6 # i-18.2
        # self.p.frequency_detuned_imaging = 254.e6 # i-24.3
        self.p.frequency_detuned_imaging = 520.e6 # i-24.3
        
        # self.xvar('beans',[0.]*3)
        
        self.p.frequency_tweezer_list = [77.e6]

        # ass = np.linspace(.2,.7,10)
        # a_lists = [[ass1] for ass1 in ass]

        # self.xvar('amp_tweezer_list',a_lists)

        a_list = [.52]
        self.p.amp_tweezer_list = a_list
        self.p.amp_tweezer_auto_compute = False

        self.p.t_mot_load = 1.5

        # self.xvar('t_tof',np.linspace(100.,3000.,10)*1.e-6)

        self.p.t_tof = 40.e-6
        self.p.N_repeats = 1

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.5,9.9,6))
        # self.p.v_pd_lightsheet_rampup_end = 9.9
        
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(5.,8.,10))
        self.p.v_pd_lightsheet_rampdown_end = 6.3

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-6.5,6.,20))
        self.p.v_tweezer_paint_amp_max = .7

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(4.,9.9,10))
        # self.p.v_pd_tweezer_1064_ramp_end = 8.2
        # self.p.v_pd_tweezer_1064_ramp_end = 9.9

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,800.,20)*1.e-3)
        # self.p.t_tweezer_1064_ramp = .17

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(2.,9.9,20))
        self.p.v_pd_tweezer_1064_ramp_end = 6.5

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.1,3.,8)) 
        # self.p.v_pd_tweezer_1064_rampdown_end = .9

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.01,.2,20))
        self.p.t_tweezer_1064_rampdown = .04

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.04,.099,8)) 
        # self.p.v_pd_tweezer_1064_rampdown2_end = .1
        # self.p.v_pd_tweezer_1064_rampdown2_end = .05

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.02,.55,8))
        self.p.t_tweezer_1064_rampdown2 = .15
        # self.p.t_tweezer_1064_rampdown2 = .5

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(1.,4.,8))
        self.p.v_pd_tweezer_1064_rampdown3_end = .35

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.05,.3,8))
        self.p.t_tweezer_1064_rampdown3 = .06
        
        # self.xvar('i_evap3_current',np.linspace(192.,194.,8))
        # self.p.i_evap3_current = 192.3

        # self.xvar('i_lf_evap1_current',np.linspace(16.,19.,20))
        # self.xvar('i_lf_evap2_current',np.linspace(17.,19.,8))
        # self.xvar('i_lf_evap3_current',np.linspace(17.,19.,8))
        self.p.i_lf_evap1_current = 18.37
        # self.p.i_lf_evap1_current = 17.58
        self.p.i_lf_evap2_current = 17.83
        self.p.i_lf_evap3_current = 18.23

        self.p.i_spin_mixture = 24.3

        # self.xvar('t_raman_pulse',np.linspace(10.e-6,20.e-3,5))
        # self.p.t_raman_pulse = 500.e-6
        # self.p.f_raman_transition = 41.23e6
        self.p.f_raman_transition = 50.e6

        self.xvar('f_raman_sweep_center',np.linspace(40.e6,42.e6,60))
        self.p.f_raman_sweep_center = 41.238e6

        # self.xvar('t_raman_sweep',np.linspace(10.e-6,20.e-3,20))
        self.p.t_raman_sweep = 30.e-3
        
        # self.xvar('f_raman_sweep_width',np.linspace(10.e3,2000.e3,30))
        self.p.f_raman_sweep_width = 34.e3

        # self.camera_params.amp_imaging = .12
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

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
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
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
        
        self.lightsheet.off()
        
        # # tweezer evap 1 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
        #                   v_start=self.p.v_pd_tweezer_1064_ramp_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=True,keep_trap_frequency_constant=True)

        # # feshbach field ramp to field 3
        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_lf_evap2_current,
        #                      i_end=self.p.i_lf_evap3_current)
        
        # # tweezer evap 2 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
        #                   paint=True,keep_trap_frequency_constant=True)
        
        # # tweezer evap 3 with constant trap frequency
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.outer_coil.ramp_supply(t=40.e-3,
                             i_start=self.p.i_lf_evap2_current,
                             i_end=self.p.i_spin_mixture)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid()

        delay(100.e-3)

        self.dds.raman_minus.set_dds(amplitude=.12)
        self.dds.raman_plus.set_dds(amplitude=.12)

        # self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.f_raman_transition)
        self.raman.sweep(t=self.p.t_raman_sweep,frequency_center=self.p.f_raman_sweep_center,frequency_sweep_fullwidth=self.p.f_raman_sweep_width)
        # delay(self.p.t_raman_sweep)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.stop_pid()
        delay(50.e-3)

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