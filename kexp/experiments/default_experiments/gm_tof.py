from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.xvar('t_tof',np.linspace(2.,10.,5)*1.e-3)
        
        self.p.imaging_state = 2.
        self.p.t_tof = 10.e-3
        self.p.t_mot_load = .1

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.gm(self.p.t_gm * s)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        delay(self.p.t_tof)

        self.flash_repump()
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel()
        self.tweezer.on()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)