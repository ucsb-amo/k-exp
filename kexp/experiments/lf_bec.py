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
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.08,.2,8))
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = .17

        # self.xvar('frequency_detuned_imaging',np.arange(280.,300.,1)*1.e6)
        # self.xvar('beans',[0]*50)

        # self.xvar('hf_imaging_detuning', [340.e6,420.e6]*1)

        # self.xvar('i_lf_tweezer_load_current',np.linspace(12.5,16.,15))
        # self.p.i_lf_tweezer_load_current = 15.

        # self.xvar('t_tweezer_soak',np.linspace(0.,500.,15)*1.e-3)
        # self.p.t_tweezer_soak = 35.e-3

        self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-4.,0.,8))
        self.p.v_lf_tweezer_paint_amp_max = -2.29

        # self.xvar('i_lf_tweezer_evap1_current',np.linspace(11.5,14.8,8))
        self.p.i_lf_tweezer_evap1_current = 12.44

        # self.xvar('v_pd_lf_tweezer_1064_rampdown_end',np.linspace(.9,3.,15)) 
        # self.p.v_pd_lf_tweezer_1064_rampdown_end = 1.25

        # self.xvar('t_lf_tweezer_1064_rampdown',np.linspace(0.02,.4,20))
        # self.p.t_lf_tweezer_1064_rampdown = .14

        # self.xvar('i_lf_tweezer_evap2_current',np.linspace(12.4,14.,8))
        self.p.i_lf_tweezer_evap2_current = 12.63

        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.08,.2,20))
        # self.p.v_pd_lf_tweezer_1064_rampdown2_end = .18

        # self.xvar('t_lf_tweezer_1064_rampdown2',np.linspace(0.1,.7,20))
        # self.p.t_lf_tweezer_1064_rampdown2 =360.6e-3

        # self.xvar('t_tof',np.linspace(100.,1500.,10)*1.e-6)
        self.p.t_tof = 800.e-6

        # self.xvar('v_paint_amp_end',np.linspace(-6.,-5.,10))

        # self.xvar('f_rf_sweep_center',461.7e6 + np.arange(-2.e6,2.e6,self.p.f_rf_sweep_width))

        # self.xvar('t_ramp_off',np.linspace(2.e-3,50.e-3,10))
        self.p.t_ramp_off = 5.e-3

        # self.xvar('v_x_shim_pol_contrast',np.linspace(.5,9.,20))
        self.p.v_x_shim_pol_contrast = 1.5

        # self.xvar('t_tweezer_hold',np.linspace(2.e-3,100.e-3,20))
        
        self.p.t_tweezer_hold = 10.e-3

        self.p.amp_imaging = .12
        # self.xvar('amp_imaging',np.linspace(0.15,.5,15))

        self.camera_params.exposure_time = 20.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.p.t_mot_load = 1.

        self.p.imaging_state = 2
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_m1)
        # self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_evap2_current,
        #                             pid_bool=False)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.imaging.set_power(power_control_parameter=)

        self.prepare_lf_tweezers()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)