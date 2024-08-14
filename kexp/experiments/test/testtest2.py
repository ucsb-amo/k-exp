from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint
from artiq.language.core import kernel_from_string, now_mu

RPC_DELAY = 10.e-3

import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False)

        self.xvar('dummy',[1]*2)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        pass

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
        self.mot_observe()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)