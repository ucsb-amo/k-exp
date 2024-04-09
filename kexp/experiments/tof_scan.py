from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=False)

        self.p.imaging_state = 2.

        self.xvar('beans',[2]*300)

        # self.p.t_lightsheet_hold = 5.e-3

        # self.xvar('t_lightsheet_hold',np.linspace(5.,40.,20)*1.e-3)
        # self.xvar('t_lightsheet_rampup',np.linspace(2.,15.,10)*1.e-3)
        
        # self.xvar('t_tweezer_hold',np.linspace(10.,10.,1000)*1.e-3)
        # self.xvar('t_tweezer_1064_ramp',np.linspace(2.,50.,20)*1.e-3)

        # self.xvar('t_tof',np.linspace(10.,10.,1000)*1.e-3) #gm
        # self.xvar('t_tof',np.linspace(20.,1000.,20)*1.e-6) #lightsheet
        self.p.t_tof = 50.e-6
        self.p.t_tweezer_1064_ramp = 20.e-3
        # self.p.t_tweezer_hold = 10.e-3

        self.p.t_mot_load = .5
        
        self.p.t_lightsheet_rampup = 10.e-3
        self.p.t_lightsheet_hold = 40.e-3

        # self.camera_params.amp_imaging = 0.55
        # self.camera_params.t_light_only_image_delay = 

        # self.p.t_tof = 1.e-6

        self.finish_build(shuffle=True)

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
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        # self.dds.mot_killer.on()

        # self.dds.power_down_cooling()

        # self.optical_pumping(self.p.t_optical_pumping)

        # if self.p.beans == 0:
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        # if self.p.beans == 1:
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        # if self.p.beans == 2:
        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # delay(self.p.t_lightsheet_hold)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # # self.lightsheet.off()
        # self.lightsheet.ramp_down(t=self.p.t_tweezer_1064_ramp)
        # delay(10.e-3)
        # self.tweezer.off()

        # if self.p.beans == 1:
        #     self.dds.mot_killer.on()

        # delay(10.e-6)

        # if self.p.beans == 1:
        #     self.dds.mot_killer.off()
        
        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # delay(self.p.t_lightsheet_hold)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp*5)
        # self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampup*5)
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # delay(40.e-3)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # self.lightsheet.off()
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        # delay(self.p.t_bias_off_wait)

        # self.set_zshim_magnet_current(self.p.v_zshim_current_gm)

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()
        # self.ttl.awg.off()

        # self.dds.mot_killer.off()
       

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


