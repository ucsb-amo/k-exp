from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_kill_405(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        # self.xvar('d',[0]*1)

        self.finish_prepare(shuffle=False)

    # @kernel
    # def scan_kernel(self):
    #     self.ttl.pd_scope_trig.pulse(1.e-6)

    #     self.ttl.line_trigger.wait_for_line_trigger()
    #     # for _ in range(1):
    #     #     self.ttl.test_trig.pulse(1.e-3)
    #     #     delay(1.e-3)
       
    @kernel
    def run(self):
        self.init_kernel()
        # self.scan()
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.ttl.line_trigger.wait_for_line_trigger()
        for _ in range(1):
            self.ttl.test_trig.pulse(1.e-3)
            delay(1.e-3)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)