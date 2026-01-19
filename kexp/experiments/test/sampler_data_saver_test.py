from artiq.experiment import *
from artiq.experiment import delay
from artiq.language.core import now_mu
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class scope_data(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      setup_camera=True)
        self.xvar('test0',[0,1])
        self.p.N_repeats = 1
        # self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)
        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.scan()

    @kernel
    def init_scan_kernel(self):
        
        self.ttl.pd_scope_trig3.pulse(1.e-8)

        delay(10.e-3)
        self.sampler.sample()
        delay(10.e-3)
        

        # self.core.wait_until_mu(now_mu())
        # self.scope.read_sweep(0)
        # self.core.break_realtime()

        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.data.apd.put_data(self.sampler.data[0])
        self.core.break_realtime()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)