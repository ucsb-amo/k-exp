from artiq.experiment import *
from artiq.language import now_mu, at_mu
import numpy as np

@kernel
def f(x: float):
    x**2

@kernel
def g(x: float):
    x**3

L = [f, g]

class timing_test(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.x = 50.
        
    @kernel
    def run(self):
        for i in range(2):
            func = L[i]
            # func(self.x)
