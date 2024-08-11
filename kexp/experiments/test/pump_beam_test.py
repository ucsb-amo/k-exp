from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class pumping_flash_calibration(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False,camera_select='xy_basler',save_data=False)

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.optical_pumping.set_dds(set_stored=True)
        self.dds.optical_pumping.on()

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