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

        # self.xvar('beans', [0,1]*2)
        self.p.beans = 1
        
        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-4.,.5,8))
        self.p.v_lf_tweezer_paint_amp_max = -2.71
        
        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.11,.23,8))
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = .15

        # self.xvar('t_tof',np.linspace(100.,1000.,10)*1.e-6)
        self.p.t_tof = 200.e-6

        # self.xvar('t_tweezer_hold',np.linspace(0.e-3,100.e-3,10))
        self.p.t_tweezer_hold = 10.e-3

        # self.xvar('t_ry_pulse',np.linspace(.1e-6,10.e-6,10))
        self.p.t_ry_pulse = 7.e-6

        # self.xvar('frequency_ry_405_detuning',np.linspace(-3.e6,3.e6,9))
        self.p.frequency_ry_405_detuning = 0.

        self.p.t_mot_load = 1.

        self.p.imaging_state = 2
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.ry_405.set_detuning(self.p.frequency_ry_405_detuning)
        
        self.ttl.d2_mot_shutter.off()

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

        self.ttl.d2_mot_shutter.on()

        delay(10.e-3)

        if self.p.beans:
            self.ry_405.on()
            delay(self.p.t_ry_pulse)
            self.ry_405.off()
        else:
            delay(self.p.t_ry_pulse)

        self.ttl.d2_mot_shutter.off()

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