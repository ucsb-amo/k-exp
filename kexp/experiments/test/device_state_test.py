from kexp.util.device_state.update_device_states import update_state_from_base
from kexp import Base

from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.finish_prepare()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,setup_slm=False,init_dds=False,
                         init_dac=False,init_shuttler=False,
                         init_lightsheet=False)
        self.ttl.pd_scope_trig_2.on()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
        update_state_from_base(self)