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
        self.params.frequency_mirny_carrier = 500.e6
        self.params.t_rf_state_xfer_sweep = 4.
        self.params.dt_rf_state_xfer_sweep = 0.05
        self.p.frequency_rf_state_xfer_sweep_start = 450.e6
        self.p.frequency_rf_state_xfer_sweep_end = 470.e6
        self.finish_build()

    @kernel
    def run(self):
        self.init_kernel()
        # self.rf.off()
        # self.rf.set_rf(460.e6)
        # self.rf.dds.set_dds(amplitude=)
        # self.rf.on()
        # delay(4*s)
        # self.rf.off()
        self.rf.mirny.mirny_device.set_output_power_mu(0)
        self.rf.mirny.set_att(5.)
        self.rf.dds.set_dds(amplitude=0.1)

        # delay(2*s)
        self.rf.sweep()
        # self.rf.dds.off()
        # self.rf.off()