from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(250.,320.,3)*1.e6)
        self.p.frequency_detuned_imaging = 289.e6
        self.xvar('beans',[0]*3)

        # self.xvar('hf_imaging_detuning', [340.e6,420.e6]*1)
        
        # self.xvar('t_tof',np.linspace(100.,1000.,10)*1.e-6)
        self.p.t_tof = 300.e-6

        self.p.frequency_tweezer_list = [75.3e6]
        a_list = [.15]
        self.p.amp_tweezer_list = a_list

        # self.xvar('f_raman_sweep_width',np.linspace(10.e3,60.e3,6))
        self.p.f_raman_sweep_width = 15.e3

        df = self.p.f_raman_sweep_width/1.5
        # self.xvar('f_raman_sweep_center',np.arange(40.e6, 44.e6, self.p.f_raman_sweep_width))
        # self.xvar('f_raman_sweep_center',np.arange(41.0e6, 41.15e6 + df, df))
        # self.xvar('f_raman_sweep_center',np.arange(41.1e6, 41.5e6 + df, df))
        # self.p.f_raman_sweep_center = 41.11e6
        # self.p.f_raman_sweep_center = self.p.frequency_raman_transition

        # self.xvar('t_raman_sweep',np.linspace(200.e-6,3.e-3,10))
        self.p.t_raman_sweep = 500.e-6

        # self.xvar('frequency_raman_transition',42.27*1e6 + np.linspace(-1.e5,1.e5,15))
        # self.xvar('frequency_raman_transition',np.linspace(41.,43.5,25)*1e6)
        # self.p.frequency_raman_transition = 41.236e6
        # self.p.frequency_raman_transition = 41.3e6
        self.p.frequency_raman_transition = 41.10e6
        # self.p.frequency_raman_transition = 42.e6

        # self.xvar('t_delay_until_raman_pulse',np.linspace(0.,75.,5)*1.e-3)
        self.p.t_delay_until_raman_pulse = 75.e-3

        # self.xvar('amp_raman',np.linspace(0.06,.23,15))
        self.p.amp_raman = .12
        # self.p.amp_raman = 0.35

        # self.p.t_raman_pi_pulse = 2.507e-06
        # self.xvar('t_raman_pulse',np.linspace(0.,500.,5)*1.e-6)
        # self.xvar('t_raman_pulse',np.linspace(0.,200.,100)*1.e-6)
        self.p.t_raman_pulse = 50.e-6
        # self.p.t_raman_pulse = 0.

        # self.xvar('t_tweezer_hold',np.linspace(0.,1.5,10)*1.e-3)
        self.p.t_tweezer_hold = .1e-3

        # self.xvar('beans',[0,1])

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        # self.camera_params.amp_imaging = .12
        # self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        # self.xvar('amp_imaging',np.linspace(.05,.2,10))
        # self.p.amp_imaging = .15

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.slm.write_phase_mask_kernel()
        # self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,
        #                             pid_bool=False)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_lightsheet_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lf_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_lightsheet_evap1_current,
                             i_end=self.p.i_lf_tweezer_load_current)
        
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_lf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lf_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown3_end)
        
        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_lf_tweezer_evap1_current)
        
        # # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_lf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_lf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_evap1_current,
                             i_end=self.p.i_lf_tweezer_evap2_current)
        
        # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_lf_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_lf_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=20.e-3,
                             i_start=self.p.i_lf_tweezer_evap2_current,
                             i_end=self.p.i_spin_mixture)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid()

        delay(self.p.t_delay_until_raman_pulse)

        self.init_raman_beams()

        # self.ttl.line_trigger.wait_for_line_trigger()

        delay(1.e-3)

        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.dds.raman_minus.set_dds(frequency=self.p.frequency_raman_minus,amplitude=self.p.amp_raman)
        # self.dds.raman_plus.set_dds(frequency=self.p.frequency_raman_plus,amplitude=self.p.amp_raman)
        # self.dds.raman_minus.on()
        # self.dds.raman_plus.on()
        # delay(self.p.t_raman_pulse)

        # self.dds.raman_minus.off()
        # self.dds.raman_plus.off()

        self.raman.pulse(t=self.p.t_raman_pulse, frequency_transition=self.p.frequency_raman_transition)

        
        # delay(self.p.t_raman_pulse)
        # self.dds.raman_minus.off()
        # # self.dds.raman_plus.off()
        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.f_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.f_raman_sweep_width)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        # delay(50.e-3)

        self.abs_image()

        # self.ttl.d2_mot_shutter.off()

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