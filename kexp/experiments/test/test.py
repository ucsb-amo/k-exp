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

        self.finish_build()

    @kernel
    def run(self):

        self.init_kernel()

        self.set_shims(v_xshim_current=self.p.v_xshim_current_op,
                       v_yshim_current=self.p.v_yshim_current_op,
                       v_zshim_current=self.p.v_zshim_current_gm)
        
        # self.set_shims(v_xshim_current=self.p.v_xshim_current_op,
        #                v_yshim_current=self.p.v_yshim_current_op,
        #                v_zshim_current=0.9)