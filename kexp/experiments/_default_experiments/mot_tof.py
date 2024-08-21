from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        self.p.t_tof = 800.e-6
        #self.xvar('t_tof',np.linspace(230.,700.,10)*1.e-6)
        self.xvar('dummy',[0]*3)

        self.p.N_repeats = 10


        self.p.t_mot_load = .05

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.dds.init_cooling()

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)

        self.release()

        delay(self.p.t_tof)
        self.flash_repump()
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