from artiq.experiment import *
from artiq.experiment import delay, parallel
from kexp import Base
import numpy as np

class ttl_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        # dt = 1.e-9
        self.xvar('dt',np.linspace(0.,1.e-9,2))
        self.p.dt = 1.e-9

        self.finish_prepare(shuffle=False)

    # @kernel
    # def scan_kernel(self):
    #     t = 10.e-6

    #     self.ttl.test.on()
    #     self.ttl.test_2.on()

    #     delay(t)
    #     self.ttl.test.off()
    #     delay(self.p.dt)
    #     self.ttl.test_2.off()

    #     delay(1.)

    @kernel
    def scan_kernel(self):
        t = 10.e-6

        self.dds.test.set_dds(80.e6,0.5)
        self.dds.test_2.set_dds(80.e6,0.5)

        
        self.dds.test.on()
        self.dds.test_2.on()
        delay(t)
        self.ttl.test.pulse(1.e-6)
        self.dds.test.off()
        delay(self.p.dt)
        self.dds.test_2.off()

        delay(1.)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)