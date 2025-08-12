from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu

class testcrate_base(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel()

        while True:
            self.core.wait_until_mu(now_mu())
            delay(0.5)
            self.check_and_update_devices(verbose=True)
            delay(0.25)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)