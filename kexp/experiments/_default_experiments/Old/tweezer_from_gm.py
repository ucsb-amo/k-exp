from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

class tweezer_from_gm(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=False)

        self.p.imaging_state = 1.
        # self.xvar('imaging_state',[2,1])
        # self.xvar('frequency_detuned_imaging',np.arange(400.,440.,3)*1.e6)
        # self.p.frequency_detuned_imaging = 421.e6
        # self.xvar('dummy',[1.]*2)

        self.xvar('beans',[1,2]*300)

        self.p.n_tweezers = 1
        self.p.amp_tweezer_list = [.15]

        # self.p.t_tweezer_1064_ramp = 15.e-3

        self.p.t_mot_load = .75

        self.p.t_tof = 5.e-6

        self.p.t_lightsheet_hold = 100.e-3

        # self.camera_params.amp_imaging = 0.04
        # self.camera_params.exposure_time = 10.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time

        # self.p.N_repeats = 2

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.outer_coil.discharge()

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.pump_to_F1()

        self.dds.power_down_cooling()

        # magtrap start
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.inner_coil.on()

        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end)

        # for i in self.p.magtrap_ramp_list:
        #         self.inner_coil.set_current(i_supply=i)
        #         delay(self.p.dt_magtrap_ramp)
        # self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
        #                         i_start=self.p.i_magtrap_init,
        #                         i_end=self.p.i_magtrap_ramp_end)
        # # delay(self.p.t_magtrap)
        # self.inner_coil.ramp(t=self.p.t_magtrap_rampdown,
        #                         i_start=self.p.i_magtrap_ramp_end,
        #                         i_end=0.)

        # self.inner_coil.off()
        
        delay(20.e-3)
        self.tweezer.off()
    
        delay(self.p.t_tof)

        self.abs_image()

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