from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.p.imaging_state = 2.

        # self.xvar('frequency_detuned_imaging',np.arange(240.,550.,6)*1.e6)
        
        # self.p.frequency_detuned_imaging = 294.e6 # i-18.3

        # self.xvar('t_tof',np.linspace(10.,200.,10)*1.e-6)
        self.p.t_tof = 20.e-6

        # self.xvar('t_tweezer_hold',np.linspace(1.,800.,10)*1.e-3)
        self.p.t_tweezer_hold = 15.e-3

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-6.5,0.,10))
        self.p.v_tweezer_paint_amp_max = -4.

        self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(2.,9.2,10))
        self.p.v_pd_tweezer_1064_ramp_end = 7.5
        # self.p.v_pd_tweezer_1064_ramp_end = 9.9

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,800.,20)*1.e-3)
        # self.p.t_tweezer_1064_ramp = .17

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.4,1.5,15))
        self.p.v_pd_tweezer_1064_rampdown_end = .95

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(20.,120.,20)*1.e-3) 
        self.p.t_tweezer_1064_rampdown = 62.e-3  

        # self.p.frequency_tweezer_list = [73.7e6,76.e6]
        self.p.frequency_tweezer_list = np.linspace(76.e6,78.e6,5)
        # self.p.frequency_tweezer_list = [74.e6]
        # self.p.frequency_tweezer_list = np.linspace(76.e6,78.e6,6)

        # a_list = [.45,.55]
        a_list = [0.1,.12,.14,.17,.24]
        # a_list = [.145]
        self.p.amp_tweezer_list = a_list

        # self.xvar('beans',[0,1])

        self.p.t_mot_load = 1.

        self.p.N_repeats = 1

        # self.xvar('turn_off_pid_before_imaging_bool',[0,1])

        # self.camera_params.amp_imaging = .12
        # self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()
        
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

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