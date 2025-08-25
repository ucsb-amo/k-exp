from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu
from kexp.control.artiq import DDS

class testcrate_base(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.dds_dummy = self.dds.test_2
        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel()

        for _ in range(50):
            self.core.wait_until_mu(now_mu())
            self.monitor.sync_change_list()
            self.core.break_realtime()
            self.monitor.apply_updates()
            delay(0.5*s)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)