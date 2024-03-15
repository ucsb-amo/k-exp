from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)
        # self.params.frequency_mirny_carrier = 460.e6
        self.params.t_rf_state_xfer_sweep = 1.
        self.finish_build()

    @kernel
    def run(self):
        self.init_kernel()
        self.rf.off()
        # self.rf.off()
        # self.rf.set_rf(460.e6)
        # # self.rf.sweep()
        # self.rf.on()
        # # self.rf.mirny.off()
        # # self.dds.rf_sideband.off()
        # self.rf.dds.set_dds(amplitude=0.35)
        # delay(5*s)