from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class lightsheet_from_magtrap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)

        self.tweezer.pid1_dac.set(v=0.12)
        self.dds.tweezer_pid_1.on()
        self.tweezer.pid1_int_hold_zero.pulse(1.e-6)

        delay(0.6)
        for i in range(1000):
            self.ttl.pd_scope_trig.pulse(1.e-6)

            self.dds.tweezer_pid_2.on()
            self.ttl.tweezer_pid2_enable.pulse(10.e-6)
            delay(0.1)
            self.dds.tweezer_pid_2.off()
            delay(0.9)

        self.dds.tweezer_pid_1.off()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)