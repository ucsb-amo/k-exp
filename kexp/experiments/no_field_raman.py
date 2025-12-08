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

        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-3.5,.5,8))
        self.p.v_lf_tweezer_paint_amp_max = -1.21
        
        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.1,.23,15))
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = .164

        self.xvar('beans',[0,1]*50)
        
        # self.xvar('t_xshim_rampdown',np.linspace(1.e-3,20.e-3,10))

        self.p.t_xshim_rampdown = 10.e-3

        # self.xvar('t_tof',np.linspace(100.,1000.,10)*1.e-6)
        self.p.t_tof = 10.e-6
        # self.xvar('t_raman_sweep',np.linspace(.15e-3,1.e-3,50))
        self.p.t_raman_sweep = 1.e-3
        # self.xvar('f_raman_sweep_width',np.linspace(10.e3,400.e3,50))
        self.p.f_raman_sweep_width = 20.e3
        self.p.f_raman_sweep_center = 461.7e6

        # self.xvar('v_x_shim_pol_contrast',np.linspace(0.0,3.,3))
        self.p.v_x_shim_pol_contrast = 2. # .5 to 3. 

        self.p.v_xcancel = 0.
        self.p.v_ycancel = 2.
        self.p.v_zcancel = .86
        # self.xvar('v_zcancel',np.linspace(0.,2.,8))

        # self.xvar('f_raman_sweep_center',461.35e6 + np.arange(-100.e3,100.e3,self.p.f_raman_sweep_width))

        # self.xvar('fraction_power_raman_nf',np.linspace(.1,.3,3))
        self.p.fraction_power_raman_nf = .15

        # self.p.frequency_raman_transition_nf = 447.325e6

        self.p.frequency_raman_transition_nf = 461.33e6

        # self.xvar('t_raman_pulse',np.linspace(0.e-6,12.e-6,12))
        # self.p.t_raman_pulse = 15.5e-6
        # self.p.t_raman_pulse = 200.e-6

        # self.xvar('t_ramp_off',np.linspace(2.e-3,50.e-3,10))
        self.p.t_ramp_off = 5.e-3        

        # self.xvar('t_tweezer_hold',np.linspace(0.e-3,100.e-3,10))
        
        self.p.t_tweezer_hold = 10.e-3

        self.p.amp_imaging = .321
        # self.xvar('amp_imaging',np.linspace(0.15,.5,15))

        # self.camera_params.exposure_time = 20.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.p.t_mot_load = 1.

        self.p.imaging_state = 1
        
        self.p.N_repeats = 10

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
        
        delay(1.e-3)

        self.dac.xshim_current_control.linear_ramp(t=10.e-3,v_start=0.,v_end=9.99,n=500)
        
        self.outer_coil.snap_off()

        self.dac.xshim_current_control.linear_ramp(t=self.p.t_xshim_rampdown,
                                                   v_start=9.99,
                                                   v_end=self.p.v_x_shim_pol_contrast,
                                                   n=90)
        
        delay(10.e-3)

        self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_ramp_down_painting_amp,
                                               v_start=self.dac.tweezer_paint_amp.v,
                                               v_end=self.p.v_paint_amp_end,
                                               n=1000)

        # self.init_raman_beams_nf(frequency_transition=self.p.frequency_raman_transition_nf,fraction_power=self.p.fraction_power_raman_nf)

        # self.raman_nf.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.f_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.f_raman_sweep_width,
        #                  n_steps=100)

        # self.raman_nf.pulse(t=self.p.t_raman_pulse)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()
        if self.p.beans:
            delay(self.p.t_tof)
        else:
            delay(10.e-3)
        # self.flash_repump()
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