from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint
from artiq.language.core import kernel_from_string, now_mu

RPC_DELAY = 10.e-3

import numpy as np

class dark_counts(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self, setup_camera=True, camera_select="andor")
        self.xvar('dummy',[0.]*5)
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()