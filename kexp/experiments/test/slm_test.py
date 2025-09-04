from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      imaging_type=img_types.ABSORPTION,
                      setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.slm.write_phase_mask_kernel()
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel(dds_off=False,dds_set=False,init_dac=False,init_lightsheet=False,setup_awg=False,init_shuttler=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)