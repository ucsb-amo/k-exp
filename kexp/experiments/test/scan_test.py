from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.xvar('dummy',[np.int64(1)])
        self.params.dummy = 1.

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        delay(1.)
       
    @kernel
    def run(self):
        self.init_kernel(init_dds=False,
                         init_dac=False,
                         dds_set=False,
                         dds_off=False,
                         init_imaging=False,
                         beat_ref_on=False,
                         init_shuttler=False,
                         init_ry=False,
                         setup_slm=False,
                         init_lightsheet=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)