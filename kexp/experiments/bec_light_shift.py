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

        self.p.frequency_tweezer_list = [80.e6]
        self.p.amp_tweezer_list = [.1525]
        self.p.amp_tweezer_auto_compute = False

        self.p.t_tof = 35.e-6
        # self.xvar('t_tof',np.linspace(10.,200.,10)*1.e-6)
        self.p.N_repeats = 1

        self.p.t_mot_load = .75

        # f0 = high_field_imaging_detuning(self.p.i_evap3_current)
        f0 = self.p.frequency_detuned_imaging_F1
        self.xvar('frequency_detuned_imaging', f0 + np.arange(-60.,60.,3)*1.e6)
        # self.p.frequency_detuned_imaging = f0

        # self.camera_params.amp_imaging = 0.10
        self.camera_params.exposure_time = 25.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def in_tweezer_abs_img(self):
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)
        delay(self.camera_params.exposure_time - self.params.t_imaging_pulse)

        self.tweezer.off()

        delay(self.camera_params.t_light_only_image_delay * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)
        delay(self.camera_params.exposure_time - self.params.t_imaging_pulse)

        delay(self.camera_params.t_dark_image_delay * s)
        self.dds.imaging.off()
        self.dds.imaging.set_dds(amplitude=0.)
        self.trigger_camera()
        delay(self.camera_params.exposure_time)
        self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)

        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def scan_kernel(self):

        # self.set_high_field_imaging(i_outer=self.p.i_evap3_current)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging)

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
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap1_current,
                             i_end=self.p.i_evap2_current)
        
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # tweezer evap 1 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
        #                   v_start=self.p.v_pd_tweezer_1064_ramp_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=True,keep_trap_frequency_constant=True)

        # feshbach field ramp to field 3
        # self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_evap2_current,
        #                      i_end=self.p.i_evap3_current)
        
        # tweezer evap 2 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
        #                   paint=True,keep_trap_frequency_constant=True)
        
        # tweezer evap 3 with constant trap frequency
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        # vf = self.tweezer.v_pd_to_painting_amp_voltage(self.p.v_pd_tweezer_1064_rampdown3_end,
        #                                               v_pd_max=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end))
        # delay(30.e-3)
        
        # ramp back up
        # self.dac.tweezer_paint_amp.linear_ramp(100.e-3,
        #                                        v_start=vf,
        #                                        v_end=-7.,
        #                                        n=1000)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3*2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown3_end,
        #                   v_end=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
        #                   paint=False,keep_trap_frequency_constant=True,low_power=True)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2*2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown2_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=False,keep_trap_frequency_constant=True)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown*2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_tweezer_1064_ramp_end,
        #                   paint=False,keep_trap_frequency_constant=True)
        
        self.outer_coil.off()
        delay(25.e-3)
        self.lightsheet.off()
        self.tweezer.off()

        delay(self.p.t_tof)
        # self.in_tweezer_abs_img()
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