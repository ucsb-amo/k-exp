from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from waxx.util.artiq.async_print import aprint

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-5.,.0,15))
        self.p.v_lf_tweezer_paint_amp_max = -2.86
        
        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.08,.23,8))
        # self.p.v_pd_lf_tweezer_1064_rampdown2_end = .2

        # self.xvar('beans',[0,1]*50)
        
        # self.xvar('t_xshim_rampdown',np.linspace(1.e-3,20.e-3,10))

        self.p.t_xshim_rampdown = 20.e-3

        self.xvar('t_tof',np.linspace(100.,1800.,10)*1.e-6)
        self.p.t_tof = 100.e-6

        self.p.t_raman_sweep = 1.e-3
        self.p.f_raman_sweep_width = 200.e3
        self.p.f_raman_sweep_center = 458.5e6

        # self.xvar('v_x_shim_pol_contrast',np.linspace(1.0,2.,4))

        self.p.v_xcancel = 5.
        self.p.v_ycancel = 0.
        self.p.v_zcancel = 2.5
        # self.xvar('v_zcancel',np.linspace(0.,4.,5))

        # self.xvar('f_raman_sweep_center',458.5e6 + np.arange(-1000.e3,5000.e3,self.p.f_raman_sweep_width))
        # self.xvar('f_raman_sweep_center',np.arange(458.0e6,458.8e6+self.p.f_raman_sweep_width,self.p.f_raman_sweep_width))

        # self.xvar('fraction_power_raman_nf',np.linspace(.0,.15,10))
        self.p.fraction_power_raman_nf = .1

        # self.p.frequency_raman_transition_nf = 447.325e6

        self.p.frequency_raman_transition_nf = 458.5e6

        # self.xvar('t_raman_pulse',np.linspace(0.e-6,100.e-6,10))
        # self.p.t_raman_pulse = 15.5e-6
        # self.p.t_raman_pulse = 200.e-6

        # self.xvar('t_ramp_off',np.linspace(2.e-3,50.e-3,10))
        self.p.t_ramp_off = 5.e-3
        
        self.p.v_x_shim_pol_contrast = 5. # .5 to 3. 

        # self.xvar('t_tweezer_hold',np.linspace(0.e-3,100.e-3,10))
        
        self.p.t_tweezer_hold = 0.e-3

        self.p.amp_imaging = .321
        # self.xvar('amp_imaging',np.linspace(0.15,.5,15))

        # self.camera_params.exposure_time = 20.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.p.t_mot_load = 1.

        self.p.imaging_state = 2
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging)
        
        # self.imaging.set_power(power_control_parameter=self.camera_params.amp_imaging)

        self.prepare_lf_tweezers()

        # self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.set_shims(v_xshim_current = self.p.v_xcancel,
                       v_yshim_current= self.p.v_ycancel,
                       v_zshim_current= self.p.v_zcancel)

        self.dac.xshim_current_control.linear_ramp(t=20.e-3,v_start=0.,v_end=9.99,n=500)

        delay(5.e-3)
        
        self.outer_coil.snap_off()

        self.dac.xshim_current_control.linear_ramp(t=self.p.t_xshim_rampdown,
                                                   v_start=9.99,
                                                   v_end=self.p.v_x_shim_pol_contrast,
                                                   n=100)
        
        delay(2.e-3)

        self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_ramp_down_painting_amp,
                                               v_start=self.dac.tweezer_paint_amp.v,
                                               v_end=self.p.v_paint_amp_end,
                                               n=1000)

        # self.init_raman_beams_nf(frequency_transition=self.p.f_raman_sweep_center,fraction_power=self.p.fraction_power_raman_nf)

        # self.raman_nf.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.f_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.f_raman_sweep_width,
        #                  n_steps=100)

        # self.raman_nf.pulse(t=self.p.t_raman_pulse)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)