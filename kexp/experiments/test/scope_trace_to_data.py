from artiq.experiment import *
from artiq.experiment import delay
from artiq.language.core import now_mu
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.control.misc.tektronix_tbs1104 import TektronixScope_TBS1104

class scope_data(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.scope = TektronixScope_TBS1104("USB0::0x0699::0x03B4::C021673::INSTR")
        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)