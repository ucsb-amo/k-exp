from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(300.,336.,2)*1.e6)
        
        # IMAGING FREQUENCIES IN FREE SPACE
        # self.xvar('frequency_detuned_imaging',[298.2e6, 284.e6])
        self.p.frequency_detuned_imaging_m1 = 286.e6
        self.p.frequency_detuned_imaging_0 = 318.e6
        # self.p.frequency_detuned_imaging_midpoint = 298.e6
        self.p.frequency_detuned_imaging_midpoint = 615.e6
        # self.xvar('frequency_detuned_imaging_midpoint',np.arange(280.,400.,6)*1.e6)

        # self.xvar('amp_imaging',np.linspace(0.0,.15,5))
        self.p.amp_imaging = .16

        # self.xvar('do_pi_pulse_bool',[0,1])

        # self.xvar('t_tweezer_hold',np.linspace(0.,1000.e-3,10))

        self.p.v_pd_tweezer_1064_rampdown3_end = .8

        self.p.i_spin_mixture = 19.48

        # self.xvar('f_raman_transition',43.4222e6 + np.linspace(-7.e3,7.e3,15))
        self.p.frequency_raman_transition = 41.236e6
        self.p.frequency_detuned_raman_transition = 41.5e6

        # self.p.t_raman_pi_pulse = 4.2157e-06
        # self.xvar('t_raman_pulse',np.linspace(0.,self.p.t_raman_pi_pulse,15))
        self.xvar('t_raman_pulse',np.linspace(0.,15.,40)*1.e-6)
        self.p.t_raman_pulse = 10.e-6

        # self.xvar('f_raman_sweep_width',np.linspace(3.e3,30.e3,20))
        # self.p.f_raman_sweep_width = 15.e3
        self.p.f_raman_sweep_width = 7.e3

        # self.xvar('f_raman_sweep_center',np.arange(43.41e6, 43.5e6, self.p.f_raman_sweep_width))
        # self.xvar('f_raman_sweep_center',np.linspace(43.41e6, 43.43e6,5))
        # self.xvar('f_raman_sweep_center',np.linspace(41.21e6, 41.27e6,10))
        # self.p.f_raman_sweep_center = 43.408e6

        # self.xvar('t_raman_sweep',np.linspace(200.e-6,3.e-3,10))
        self.p.t_raman_sweep = 1.e-3

        # self.xvar('amp_raman',np.linspace(.02,.15,20))
        self.p.amp_raman_plus = .25
        self.p.amp_raman_minus = .25
        self.p.amp_raman = .25

        # self.p.t_max = 20.e-3
        # self.xvar('t_pulse',np.linspace(0.,self.p.t_max,10))

        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]

        self.p.t_mot_load = 1.
        self.p.t_tof = 500.e-6
        # self.xvar('t_tof',np.linspace(20.,500.,4)*1.e-6)
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_midpoint)
        # self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,pid_bool=True)

        self.set_imaging_detuning(self.p.frequency_detuned_imaging_midpoint)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)
        # self.dds.imaging.set_dds(amplitude=.1)
        
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_midpoint)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

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
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_lightsheet_evap1_current)

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

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_lf_tweezer_evap1_current)

        
        # # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_evap1_current,
                             i_end=self.p.i_lf_tweezer_evap2_current)
        
        # # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        delay(2.e-3)
        # tweezer evap 3 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=20.e-3,
                             i_start=self.p.i_lf_tweezer_evap2_current,
                             i_end=self.p.i_spin_mixture)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid()

        delay(40.e-3)

        self.dds.raman_minus.set_dds(amplitude=self.p.amp_raman)
        self.dds.raman_plus.set_dds(amplitude=self.p.amp_raman)

        # self.raman.pulse(t=self.p.t_raman_pi_pulse,frequency_transition=self.p.frequency_raman_transition)
        # delay(5.e-3)
        self.dds.imaging.on()
        self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.frequency_raman_transition)
        # delay(self.p.t_raman_pulse)
        self.dds.imaging.off()

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.f_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.f_raman_sweep_width)
        
        delay(1.e-3)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)
        self.dds.imaging.set_dds(amplitude=.1)

        # delay(self.p.t_tweezer_hold)
        delay(9.e-3)
        self.tweezer.off()

        delay(self.p.t_tof)
        # delay(.5e-6)
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