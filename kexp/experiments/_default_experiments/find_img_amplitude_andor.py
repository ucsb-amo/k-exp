from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class img_amp_calibration(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 2.
        self.xvar('amp_imaging',np.linspace(0.1,0.5,10))
        self.p.t_tof = 10.e-6
        self.p.N_repeats = 1
        self.p.t_mot_load = .1
        self.p.t_tweezer_1064_ramp = 0.010
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(amp=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end)
        delay(25.e-3)
        self.tweezer.off()

        delay(self.p.t_tof)
        # self.flash_repump()
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