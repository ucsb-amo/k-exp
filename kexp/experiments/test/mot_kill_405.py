from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_kill_405(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=False)

        self.p.imaging_state = 2.

        # self.xvar('t_tof',np.linspace(230.,700.,10)*1.e-6)
        self.p.t_tof = 400.e-6

        self.p.N_repeats = 1

        self.xvar('dummy',[1,0]*1000000)

        self.p.t_mot_load = .25

        self.camera_params.amp_imaging = 0.35

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        t = 100.e-6
        if self.p.dummy == 1:
            self.dds.ry_405.on()

        self.dds.init_cooling()

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.release()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        self.dds.ry_405.off()
       
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