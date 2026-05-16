from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class init_dds(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        pass
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
        
        