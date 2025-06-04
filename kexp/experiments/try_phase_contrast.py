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
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(150.,350.7,8)*1.e6)
        # self.p.frequency_detuned_imaging = 270.e6
        # self.p.frequency_detuned_imaging

        # self.xvar('beans',[0]*15)

        self.p.t_tweezer_hold = 100.e-3

        # self.xvar('t_tof',np.linspace(400.,1200.,15)*1.e-6)
        self.p.t_tof = 20.e-6

        # self.p.i_spin_mixture = 24.3
        self.p.i_spin_mixture = 20.57

        # self.xvar('f_raman_transition',43.405e6 + np.linspace(-10.e3,10.e3,20))
        self.p.f_raman_transition = 43.40e6

        # self.xvar('f_raman_sweep_center',np.linspace(43.35e6,43.48e6,10))
        # self.xvar('f_raman_sweep_center',76.4e6 + 2.e6*np.linspace(-1.,1.,60))
        self.p.f_raman_sweep_center = 43.405e6
        # self.p.f_raman_sweep_center = 41.39e6

        # self.xvar('t_raman_sweep',np.linspace(200.e-6,3.e-3,10))
        self.p.t_raman_sweep = 1.e-3

        self.p.t_raman_pulse = 500.e-6
        # self.xvar('t_raman_pulse',np.linspace(.3,100.,50)*1.e-6)
        
        # self.xvar('f_raman_sweep_width',np.linspace(3.e3,30.e3,20))
        self.p.f_raman_sweep_width = 15.e3

        # self.xvar('amp_raman',np.linspace(.02,.15,20))
        self.p.amp_raman = .25

        self.p.frequency_tweezer_list = [74.e6]
        a_list = [.75]
        self.p.amp_tweezer_list = a_list

        # self.xvar('beans',[0,1])

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        # self.p.phase_slm_mask = 3.14 / 2
        # self.xvar('phase_slm_mask', np.pi/2 * (1 + 0.1*np.linspace(-2.,1.,5)))
        self.p.phase_slm_mask = np.pi * 0.42
        self.p.dimension_slm_mask = 50.e-6
        # self.xvar('dimension_slm_mask',np.linspace(1.,100.,5)*1.e-6)
        # self.xvar('dummy',[0])

        # self.camera_params.amp_imaging = .12
        # self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        # self.p.N_pwa_per_shot = 3
        self.p.t_dispersive_image_interval = 100.e-3

        # self.xvar('dummy',[0]*2)

        # self.xvar('amp_imaging',np.linspace(.05,.2,10))

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.slm.write_phase_mask_kernel()
        # self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_evap2_current,
                                    # pid_bool=False)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_lightsheet_evap1_current)
        
        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=0.,
                        v_xshim_current=0.)
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
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tweezer_hold)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_lf_tweezer_evap1_current)

        
        # tweezer evap 1 with constant trap frequency
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
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)

        # self.outer_coil.ramp_supply(t=20.e-3,
        #                      i_start=self.p.i_lf_tweezer_load_current,
        #                      i_end=self.p.i_spin_mixture)
        
        # self.outer_coil.start_pid()

        # delay(50.e-3)

        # self.dds.raman_minus.set_dds(amplitude=self.p.amp_raman)
        # self.dds.raman_plus.set_dds(amplitude=self.p.amp_raman)

        # self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.f_raman_transition)

        # self.raman.sweep(t=self.p.t_raman_sweep,frequency_center=self.p.f_raman_sweep_center,frequency_sweep_fullwidth=self.p.f_raman_sweep_width)

        # self.light_image()
        # delay(self.p.t_dispersive_image_interval)
        # self.light_image()
        # delay(self.p.t_dispersive_image_interval)
        # self.light_image()
        # delay(self.p.t_dispersive_image_interval)

        self.tweezer.off()

        delay(self.p.t_tof)

        # delay(200.e-3)
        # self.light_image()
        
        # self.close_imaging_shutters()
        # delay(200.e-3)
        # self.dark_image()

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
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)