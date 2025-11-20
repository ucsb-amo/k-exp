from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

from kexp.calibrations.magnets import compute_pid_overhead

class coil_set(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(dds_off=False,dds_set=False,init_dds=False,
                         init_shuttler=False,init_lightsheet=False,
                         init_dac=False,setup_awg=False,
                         setup_slm=False)
        
        self.outer_coil.on()
        self.outer_coil.set_voltage()

        I = 19.48
        i = compute_pid_overhead(I)
        self.outer_coil.set_supply( i_supply = I + i )
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)