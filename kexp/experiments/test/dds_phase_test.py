from artiq.experiment import *
from artiq.experiment import delay, parallel
from artiq.language.core import now_mu, at_mu
from kexp import Base
import numpy as np

class ttl_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        # dt = 1.e-9
        self.xvar('dt',[1.e-9]*1)
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

        self.dds.test.dds_device.set_phase_mode(2)
        # self.dds.test.dds_device.set_phase_mode(0)
        
        t0 = now_mu()

        f = 1.e6
        # f2 = 3.14159e6
        f2 = 10.e6
        phase = 0.
        amp = 0.5
        self.dds.test.dds_device.set(frequency=f,amplitude=amp,ref_time_mu=t0)

        self.dds.test.on()
        delay(10.e-6)

        # trigger
        
        self.dds.test.dds_device.set(frequency=f2,amplitude=amp,ref_time_mu=t0)
        # delay(100.e-9)
        delay(-500.e-9)
        self.ttl.test.pulse(1.e-6)

        delay(5.e-6)

        self.dds.test.off()

        delay(0.1)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)