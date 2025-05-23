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

        # self.p.imaging_state = 2.

        # self.xvar('frequency_detuned_imaging',np.arange(240.,550.,6)*1.e6)
        
        self.p.frequency_detuned_imaging = 294.e6 # i-18.3

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.5,9.9,6))
        # self.p.v_pd_lightsheet_rampup_end = 9.9
        
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(.5,2.5,20))
        self.p.v_pd_lightsheet_rampdown_end = 1.2
        # self.p.v_pd_lightsheet_rampdown_end = .78


        # self.xvar('t_lightsheet_hold',np.linspace(1.,5000.,5)*1.e-3)
        # self.p.t_lightsheet_hold = .1

        # self.xvar('t_tweezer_hold',np.linspace(1.,800.,10)*1.e-3)

        self.p.t_tweezer_hold = 300.e-3

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-7.,0.,10))
        self.p.v_tweezer_paint_amp_max = -7.

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(3.,9.,15))
        self.p.v_pd_tweezer_1064_ramp_end = 6.5
        
        # self.p.v_pd_tweezer_1064_ramp_end = 9.9

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,800.,20)*1.e-3)
        # self.p.t_tweezer_1064_ramp = .17

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.1,3.,8)) 
        # self.p.v_pd_tweezer_1064_rampdown_end = .9

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.01,.2,20))
        # self.p.t_tweezer_1064_rampdown = .04

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.04,.099,8)) 
        # self.p.v_pd_tweezer_1064_rampdown2_end = .1
        # self.p.v_pd_tweezer_1064_rampdown2_end = .05

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.02,.55,8))
        # self.p.t_tweezer_1064_rampdown2 = .15
        # self.p.t_tweezer_1064_rampdown2 = .5

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(1.,4.,8))
        # self.p.v_pd_tweezer_1064_rampdown3_end = .35

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.05,.3,8))
        # self.p.t_tweezer_1064_rampdown3 = .06
        
        # self.xvar('i_evap3_current',np.linspace(192.,194.,8))
        # self.p.i_evap3_current = 192.3

        # self.xvar('i_lf_lightsheet_evap1_current',np.linspace(14.,17.,8))
        # self.xvar('i_lf_evap2_current',np.linspace(17.,19.,8))
        # self.xvar('i_lf_evap3_current',np.linspace(17.,19.,8))
        # self.xvar('i_lf_tweezer_load_current',np.linspace(14.,20.,8))
        self.p.i_lf_lightsheet_evap1_current = 16.

        self.p.i_lf_tweezer_load_current = 14.5
        # self.p.i_lf_evap3_current = 18.23

        # self.p.i_spin_mixture = 24.3
        self.p.i_spin_mixture = 20.57

        # self.xvar('f_raman_transition',43.4222e6 + np.linspace(-7.e3,7.e3,15))
        self.p.f_raman_transition = 43.4222e6

        # self.xvar('t_raman_pulse',np.linspace(.1,80.,20)*1.e-6)
        self.p.t_raman_pulse = 500.e-6

        # self.xvar('f_raman_sweep_center',np.linspace(43.35e6,43.48e6,10))
        self.p.f_raman_sweep_center = 43.4222e6

        # self.xvar('t_raman_sweep',np.linspace(200.e-6,3.e-3,10))
        self.p.t_raman_sweep = 1.e-3

        # self.xvar('f_raman_sweep_width',np.linspace(3.e3,30.e3,20))
        self.p.f_raman_sweep_width = 15.e3

        # self.xvar('amp_raman',np.linspace(.02,.15,20))
        self.p.amp_raman = .25
        # self.p.amp_raman = .11

        # self.p.frequency_tweezer_list = [73.7e6,76.e6]
        self.p.frequency_tweezer_list = [76.e6]
        # self.p.frequency_tweezer_list = np.linspace(76.e6,78.e6,6)

        # a_list = [.45,.55]
        # a_list = [.14,.145]
        a_list = [.145]
        self.p.amp_tweezer_list = a_list

        # self.xvar('beans',[0,1]*10)

        self.p.t_mot_load = 1.

        # self.xvar('t_tof',np.linspace(100.,3000.,10)*1.e-6)

        self.p.t_tof = 20.e-6
        self.p.N_repeats = 1

        # self.xvar('turn_off_pid_before_imaging_bool',[0,1])

        # self.camera_params.amp_imaging = .12
        # self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # if self.p.turn_off_pid_before_imaging_bool:
        #     pid_during_imaging = False
        # else:
        #     pid_during_imaging = True
        # self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,
        #                             pid_bool=pid_during_imaging)
        self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,pid_bool=True)

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
                             i_end=self.p.i_lf_lightsheet_evap1_current)
        
        # 
        # self.outer_coil.start_pid(i_pid = self.p.i_lf_lightsheet_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_lightsheet_evap1_current,
                             i_end=self.p.i_lf_tweezer_load_current)
        
        #
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=20.e-3,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_spin_mixture)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid()

        delay(40.e-3)

        # self.dds.raman_minus.set_dds(amplitude=self.p.amp_raman)
        # self.dds.raman_plus.set_dds(amplitude=self.p.amp_raman)

        # self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.f_raman_transition)

        # self.raman.sweep(t=self.p.t_raman_sweep,frequency_center=self.p.f_raman_sweep_center,frequency_sweep_fullwidth=self.p.f_raman_sweep_width)

        # delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.stop_pid()

        self.outer_coil.off()
        self.outer_coil.discharge()

        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)

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