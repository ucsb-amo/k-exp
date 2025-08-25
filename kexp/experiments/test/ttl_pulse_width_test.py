from artiq.experiment import *
from artiq.experiment import delay, parallel
from artiq.language.core import now_mu, at_mu
from kexp import Base
import numpy as np

class ttl_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        # dt = 1.e-9
        # self.xvar('dt',[0.,1.e-9]*50)
        self.p.dt = 0.e-9

        self.p.N_repeats = 32

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

        f = 1.e6
        phase = 0.
        amp = 0.5

        t_start = now_mu()
        delay(-10.e-6)
        
        self.dds.test.dds_device.set(frequency=f,phase=phase,amplitude=amp,ref_time_mu=t_start)
        # self.dds.test_2.dds_device.set(frequency=f,phase=phase,amplitude=amp,ref_time_mu=t_start)

        at_mu(t_start)
        self.dds.test.on()
        # self.dds.test_2.on()
        delay(20/f)

        # trigger
        self.ttl.test.pulse(1.e-6)
        delay(-1.e-6)
        delay(-20.e-9)

        # self.dds.test_2.off()
        delay(self.p.dt)
        self.dds.test.off()
        # delay(self.p.dt)
        # self.dds.test_2.off()
        

        delay(1.e-3)

    @kernel
    def run(self):
        self.init_kernel()

        self.dds.test.dds_device.set_phase_mode(2)
        self.dds.test_2.dds_device.set_phase_mode(2)

        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)