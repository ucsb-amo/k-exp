from artiq.experiment import *
from artiq.language import now_mu, delay
import numpy as np

N = 10

class array_test(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.ttl = self.get_device('ttl4')

        self.m = 10

        self.P0 = np.ones(N)

    @kernel
    def boop(self):
        x = self.P0

        x[0] = 0.

    @kernel
    def run(self):
        self.core.reset()

        print(self.P0)

        self.boop()

        print(self.P0)

        