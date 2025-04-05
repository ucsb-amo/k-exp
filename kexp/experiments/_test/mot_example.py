from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.slm.write_phase_spot(diameter = 200, phase = np.pi / 2, x_center
        = 100, y_center = 300)

        self.p.imaging_state = 2.
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = 2.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        
        self.switch_d2_2d(1)
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.release()

        delay(self.p.t_tof)

        self.flash_repump()
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel()
        
        self.scan()

        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)