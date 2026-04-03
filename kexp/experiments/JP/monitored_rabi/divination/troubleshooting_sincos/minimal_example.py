from artiq.experiment import *
import numpy as np

class fail(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.x = 0.1
        self.y = 0.

    @kernel
    def run(self):

        # x = 0.1 # no error
        x = self.x # LoadError

        a = np.sin(x)
        b = np.cos(x)
        # a = np.sin(x)
        # b = np.sin(np.pi/2 - x)

        self.y = a + b