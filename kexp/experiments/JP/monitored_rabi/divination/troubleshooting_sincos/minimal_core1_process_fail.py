from artiq.experiment import *
from artiq.experiment import delay
import numpy as np

class core1_fail(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.alpha = 0.1

    @kernel
    def run(self):

        # self.test0(self.alpha)

        # self.test0(0.1)

        # self.test1(self.alpha)

        # self.test2()
        

    @kernel
    def test0(self, alpha):
        
        y = np.sin(alpha)
        z = np.cos(alpha)

        print(y)
        print(z)

    @kernel
    def test1(self, alpha):
        
        y = np.sin(alpha)
        z = np.cos(alpha)

        print(z)
        # or print(y)

    @kernel
    def test2(self):

        alpha = 0.1
        
        y = np.sin(alpha)
        z = np.cos(alpha)

        print(y)
        print(z)