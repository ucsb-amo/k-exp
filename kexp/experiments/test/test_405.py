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

        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-4.,.5,8))
        self.p.v_lf_tweezer_paint_amp_max = -2.71
        
        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.11,.23,8))
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = .15

        self.p.t_xshim_rampdown = 10.e-3

        self.xvar('t_tof',np.linspace(100.,1000.,10)*1.e-6)
        self.p.t_tof = 1200.e-6

        # self.xvar('v_x_shim_pol_contrast',np.linspace(0.0,3.,3))
        self.p.v_x_shim_pol_contrast = 9. # .5 to 3. 

        self.p.v_xcancel = 0.
        self.p.v_ycancel = 2.
        self.p.v_zcancel = .86

        # self.xvar('t_tweezer_hold',np.linspace(0.e-3,100.e-3,10))
        
        self.p.t_tweezer_hold = 10.e-3

        self.p.amp_imaging = .1
        # self.xvar('amp_imaging',np.linspace(0.15,.5,15))

        # self.xvar('frequency_detuned_imaging',np.linspace(0.e6,440.e6,50))
        # self.p.frequency_detuned_imaging = 36.e6
        
        # self.camera_params.exposure_time = 20.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        # self.xvar('phase_slm_mask',np.linspace(0.,2*np.pi,15))
        # self.xvar('dimension_slm_mask',np.linspace(10.e-6, 300.e-6,15))
        self.p.dimension_slm_mask = 30.e-6
        self.p.phase_slm_mask = 0.35*np.pi
        self.p.t_mot_load = 1.

        self.p.imaging_state = 2
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.prepare_lf_tweezers()

        self.set_shims(v_xshim_current = self.p.v_xcancel,
                       v_yshim_current= self.p.v_ycancel,
                       v_zshim_current= self.p.v_zcancel)
        
        delay(1.e-3)

        self.dac.xshim_current_control.linear_ramp(t=10.e-3,v_start=0.,v_end=9.99,n=200)
        
        self.outer_coil.snap_off()

        self.dac.xshim_current_control.linear_ramp(t=self.p.t_xshim_rampdown,
                                                   v_start=9.99,
                                                   v_end=self.p.v_x_shim_pol_contrast,
                                                   n=90)
        
        # delay(10.e-3)

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