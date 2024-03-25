from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 2.

        self.p.t_tof = 40.e-6

        # self.xvar('detune_push',np.linspace(-4.,4.,5))
        # self.xvar('amp_push',np.linspace(.05,.188,5))

        # self.xvar('detune_d2_c_mot',np.linspace(-3.,0.,5))
        # self.xvar('detune_d2_r_mot',np.linspace(-5.,-3.,5))
        # self.xvar('i_mot',np.linspace(22.,25.,5))
        # self.xvar('v_zshim_current',np.linspace(.0,1.,5))
        # self.xvar('v_xshim_current',np.linspace(.0,2.,5))
        # self.xvar('v_yshim_current',np.linspace(.0,2.,5))

        # self.xvar('v_zshim_current_gm',np.linspace(.7,1.,10))
        # self.xvar('v_xshim_current_gm',np.linspace(.0,2.,5))
        # self.xvar('pfrac_c_gmramp_end',np.linspace(.2,.7,5))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,.4,5))
        # self.xvar('pfrac_d1_c_gm',np.linspace(.4,.9,5))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.3,.5,5))
        # self.xvar('t_gm',np.linspace(1.,8.,5)*1.e-3)
        # self.xvar('t_gmramp',np.linspace(3.,9.,5)*1.e-3)

        # self.xvar('t_tweezer_1064_ramp',np.linspace(3.,7.,3)*1.e-3)
        
        # self.xvar('imaging_state',[1,2])
        self.xvar('t_tof',np.linspace(20,500,12)*1.e-6)
        # self.xvar('frequency_detuned_imaging_F1_offset',np.linspace(-10,15.,15)*1.e6)
        # self.xvar('frequency_detuned_imaging_offset',np.linspace(-3,3.,15)*1.e6)
        # self.xvar('t_tweezer_hold',np.linspace(.100,20.,2)*1.e-3)
        # self.xvar('t_lightsheet_hold',np.linspace(5000,40000,5)*1.e-6)

        # self.xvar('t_cooler_flash_imaging',np.linspace(0,10,8)*1.e-6)

        # self.xvar('t_mot_load',np.linspace(50.,100.,2)*1.e-3)

        # self.xvar('imaging_state',[1.,2.])

        self.p.t_mot_load = 1.
        # self.p.t_tof = 20.e-6
        self.p.N_repeats = 1

        self.p.frequency_detuned_imaging_F1_offset = 0.
        self.p.frequency_detuned_imaging_offset = 0.
        
        # self.camera_params.em_gain = 100
        # self.camera_params.exposure_time = 5.e-6
        # self.p.t_imaging_pulse = 5.e-6
        # self.p.t_dark_image_delay = 50.e-3

        # self.p.amp_imaging_abs = 0.5

        self.p.t_bias_off_wait = 20.e-3

        self.finish_build()

    @kernel
    def scan_kernel(self):

        if self.p.imaging_state == 1:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1 + self.p.frequency_detuned_imaging_F1_offset)
        else:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging+self.p.frequency_detuned_imaging_offset)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm, v_yshim_current=self.p.v_yshim_current_gm, v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        # self.tweezer.on()
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # self.set_zshim_magnet_current(9.99)
        delay(self.p.t_lightsheet_hold)

        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # delay(20.e-3)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # self.lightsheet.off()
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        # self.set_zshim_magnet_current()
        # delay(self.p.t_bias_off_wait)

        self.lightsheet.off()

        delay(self.p.t_tof)
        # self.flash_repump()
        # self.flash_cooler()
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


