from artiq.experiment import *
from artiq.language import now_mu, at_mu
import numpy as np

class timing_test(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        
    @kernel
    def run(self):
        N = 100
        self.core.reset()
        t0 = now_mu()
        self.core.wait_until_mu(t0)
        for i in range(N):
            2.0*i
        slack = t0 - self.core.get_rtio_counter_mu()
        
        delay(10.e-3)
        print(slack/N)