from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('i_lf_tweezer_load_current',np.linspace(12.,17.,15))

        # self.xvar('v_pd_lf_tweezer_1064_ramp_end',np.linspace(5.,9.5,15))
        # self.p.v_pd_lf_tweezer_1064_ramp_end = 9.5

        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-5.,.0,8))
        self.p.v_lf_tweezer_paint_amp_max = -.71
        
        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.08,.23,8))
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = .2

        self.xvar('beans',[0,1]*50)

        # self.xvar('t_tof',np.linspace(100.,1800.,10)*1.e-6)
        self.p.t_tof = 10.e-6

        # self.xvar('fraction_power_raman_nf',np.linspace(.1,.8,self.p.f_rf_sweep_width))
        self.p.fraction_power_raman_nf = 1.

        # self.p.frequency_raman_transition_nf = 447.325e6
        self.p.frequency_raman_transition_nf = 460.61e6

        # self.xvar('t_raman_pulse',np.linspace(0.e-6,30.e-6,15))
        self.p.t_raman_pulse = 11.e-6
        # self.p.t_raman_pulse = 200.e-6

        # self.xvar('t_ramp_off',np.linspace(2.e-3,50.e-3,10))
        self.p.t_ramp_off = 5.e-3

        # self.xvar('v_x_shim_pol_contrast',np.linspace(.5,9.,20))
        self.p.v_x_shim_pol_contrast = 1.5

        # self.xvar('t_tweezer_hold',np.logspace(np.log10(3.e-3), np.log10(200.e-3), 30))
        # self.xvar('t_tweezer_hold',np.linspace(0.e-3,20.e-3,20))
        
        self.p.t_tweezer_hold = 10.e-3

        self.p.amp_imaging = .1
        # self.xvar('amp_imaging',np.linspace(0.15,.5,15))

        self.camera_params.exposure_time = 20.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.p.t_mot_load = 1.

        self.p.imaging_state = 2
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        # self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.imaging.set_power(amp=self.camera_params.amp_imaging)

        self.prepare_lf_tweezers()

        # self.ttl.pd_scope_trig.pulse(1.e-6)

        self.dac.xshim_current_control.linear_ramp(t=20.e-3,v_start=0.,v_end=9.99,n=500)

        delay(5.e-3)
        
        self.outer_coil.snap_off()

        self.dac.xshim_current_control.linear_ramp(t=20.e-3,
                                                   v_start=9.99,
                                                   v_end=self.p.v_x_shim_pol_contrast,
                                                   n=500)
        
        delay(5.e-3)

        self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_ramp_down_painting_amp,
                                               v_start=self.dac.tweezer_paint_amp.v,
                                               v_end=self.p.v_paint_amp_end,
                                               n=1000)

        self.init_raman_beams_nf()

        self.raman_nf.pulse(t=self.p.t_raman_pulse)

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