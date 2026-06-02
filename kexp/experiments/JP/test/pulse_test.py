from artiq.experiment import *
from artiq.language import delay, now_mu, at_mu
import numpy as np

class integrator_test(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.ttl = self.get_device('ttl16')

    @kernel
    def run(self):
        self.core.reset()

        t0 = now_mu()

        at_mu(t0 + 1000)
        self.ttl.off()

        at_mu(t0)
        self.ttl.on()
