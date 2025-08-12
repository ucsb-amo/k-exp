from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class testcrate_base(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel()
        self.ttl.test.pulse(3.e-3)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)