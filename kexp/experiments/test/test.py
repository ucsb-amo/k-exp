from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION)

        self.camera_params = cameras.andor
        self.ttl.camera = self.ttl.test

        self.xvar('beans',[1]*1)

        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = 10.e-6
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        delay(0.25)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)