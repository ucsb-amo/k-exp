from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False,camera_select='xy_basler',save_data=False)

        self.p.frequency_rf_state_xfer_sweep_center = 400.e6
        self.p.frequency_rf_state_xfer_sweep_fullwidth = 50.e6
        self.p.t_rf_state_xfer_sweep = 5.
        self.p.n_rf_state_xfer_sweep_steps = 1000
        
        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.rf.sweep()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


