from artiq.experiment import *
import numpy as np

@subkernel(destination=0)
def test(x) -> TFloat:

    y = np.sin(x)
    z = np.cos(x)

    return y + z

class core1_fail(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.x = 0.1

        self.w = np.array([0.,0.])

    @kernel
    def run(self):
        self.w[0] = test(self.x)