from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      imaging_type=img_types.ABSORPTION,
                      setup_camera=True,
                      camera_select='andor',
                      save_data=False)
        
        self.xvar('dummy',[1]*2)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel()
        # self.load_2D_mot(self.p.t_2D_mot_load_delay)f
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)