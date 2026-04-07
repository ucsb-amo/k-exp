from artiq.experiment import *
from artiq.language import now_mu, at_mu
import numpy as np

x = np.zeros(1000000)

class timing_test(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        
    @kernel
    def run(self):
        pass