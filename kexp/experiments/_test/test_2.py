from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test_2(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False)
   
        self.finish_prepare(shuffle=False)

    @kernel
    def run(self):

        self.init_kernel()

        self.tweezer.pid_int_zero_ttl.on()
        delay(1*s)
        self.tweezer.pid_int_zero_ttl.off()

        self.scan()