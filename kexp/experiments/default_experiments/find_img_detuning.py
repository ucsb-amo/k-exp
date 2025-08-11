from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class img_detuning_calibration(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('frequency_detuned_imaging',np.arange(10.,30.,3)*1.e6)
        self.xvar('frequency_detuned_imaging',np.linspace(19.,28.,15)*1.e6)
        # self.xvar('frequency_detuned_imaging_F1',np.arange(400.,480.,2)*1.e6)
        self.p.t_tof = 15.e-3
        self.p.N_repeats = 3
        self.p.t_mot_load = .25
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.gm(self.p.t_gm * s)
        self.ttl.pd_scope_trig.on()
        self.gm_ramp(self.p.t_gmramp)
        self.ttl.pd_scope_trig.off()

        self.release()

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