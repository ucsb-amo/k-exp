from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint
from artiq.language.core import kernel_from_string, now_mu

RPC_DELAY = 10.e-3

import numpy as np

class test2(EnvExperiment,Base):

    def prepare(self):
        Base.setup(self,setup_camera=False,save_data=False)

        f1 = np.linspace(62.e6,72.e6,2)
        f2 = np.linspace(78.e6,88.e6,2)
        self.params.frequency_tweezer_list = np.concatenate((f1,f2))

        self.finish_prepare()

    @kernel
    def run(self):
        self.core.reset()
        self.ttl.pd_scope_trig.pulse(1.e-6)