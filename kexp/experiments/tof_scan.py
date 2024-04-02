from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='z_basler',save_data=True)

        self.p.imaging_state = 2.

        self.p.t_tof = 10.e-6

        # self.xvar('t_lightsheet_hold',np.linspace(10.,100.,10)*1.e-3)
        # self.xvar('t_lightsheet_rampup',np.linspace(2.,15.,10)*1.e-3)
        
        self.xvar('t_tweezer_hold',np.linspace(1.,20.,10)*1.e-3)

        # self.xvar('t_cooler_flash_imaging',np.linspace(0,10,8)*1.e-6)

        # self.xvar('t_mot_load',np.linspace(1.,200.,10)*1.e-3)

        # self.xvar('imaging_state',[1.,2.])

        # self.xvar('t_d1cmot',np.linspace(2.,8.,10)*1.e-3)

        # self.xvar('do_optical_pumping',[0.,1.])

        # self.xvar('t_tof',np.linspace(5.,14.,10)*1.e-3) #gm
        # self.xvar('t_tof',np.linspace(20.,500.,6)*1.e-6) #lightsheet

        # self.xvar('t_optical_pumping',np.linspace(1.,300.,15)*1.e-6)
        
        # self.xvar('amp_optical_pumping_op',np.linspace(0.075,0.15,3))
        # self.xvar('amp_optical_pumping_r_op',np.linspace(0.2,0.3,3))

        # self.xvar('reload_2d',[0,1]*10)

        self.p.t_lightsheet_hold = 20.e-3

        self.p.t_tweezer_1064_ramp = 10.e-3

        self.p.t_mot_load = 1.
        # self.p.t_tof = 12.e-3
        # self.p.N_repeats = [1,2]

        # self.camera_params.em_gain = 100
        # self.camera_params.exposure_time = 5.e-6
        # self.p.t_imaging_pulse = 5.e-6
        # self.p.t_dark_image_delay = 50.e-3

        # self.p.amp_imaging_abs = 0.5

        # self.p.t_bias_off_wait = 20.e-3

        # self.p.t_optical_pumping = 100.e-6

        # self.p.do_optical_pumping = 1.

        self.finish_build()

    @kernel
    def scan_kernel(self):

        self.dds.init_cooling()

        if self.p.imaging_state == 1:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        else:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm, v_yshim_current=self.p.v_yshim_current_gm, v_xshim_current=self.p.v_xshim_current_gm)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        # if not self.p.do_optical_pumping:
        # self.flash_repump(8.e-6)
        # delay(22.e-3)

        # self.dds.power_down_cooling()

        # if self.p.do_optical_pumping:
        # self.optical_pumping(self.p.t_optical_pumping)

        # self.tweezer.on()
        
        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # self.set_zshim_magnet_current(3.)
        # delay(self.p.t_lightsheet_hold)

        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # self.lightsheet.off()
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # delay(20.e-3)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # self.lightsheet.off()
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        # self.set_zshim_magnet_current()
        # delay(self.p.t_bias_off_wait)

        # self.set_zshim_magnet_current(self.p.v_zshim_current_gm)

        delay(self.p.t_tof)
        # if self.p.do_optical_pumping:
        #     self.optical_pumping(t=self.p.t_optical_pumping)
        # else:
        #     self.flash_repump(t=self.p.t_optical_pumping)
        # self.flash_cooler()
        self.flash_repump()
        self.abs_image()

        # self.tweezer.off()

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


