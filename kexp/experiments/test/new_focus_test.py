from artiq.experiment import *
from kexp import Base
import numpy as np

class new_focus_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(dds_off=False,dds_set=False,init_dds=False,
                         init_shuttler=False,init_lightsheet=False,
                         init_dac=False,setup_awg=False,
                         setup_slm=False)
        
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)