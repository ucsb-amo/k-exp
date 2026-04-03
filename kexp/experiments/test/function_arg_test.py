from artiq.experiment import *
from artiq.language import now_mu, at_mu
import numpy as np

@kernel
def f(x):
    x0 = x[0]

@kernel
def g(x):
    x0, x1 = x[0], x[1]

class func_test(EnvExperiment):
    def prepare(self):
        self.core = self.get_device("core")
        self.x = np.array([0.])
        self.y = np.array([0.,1.])

        self.z = np.ones((10,10))
        
        self.N = np.arange(300,3000,1).astype(int)
        self.ts = np.zeros(len(self.N),dtype=np.int64)

        self.fs = [f,g]

    @kernel
    def test(self,n):
        pass

    @kernel
    def run(self):
        N = 1000

        self.core.reset()

        for i in range(len(self.N)):
            n = self.N[i]
            x = range(n)

            t = now_mu()
            self.core.wait_until_mu(t)
            for _ in x:
                pass
            t_func = t - self.core.get_rtio_counter_mu()

            self.ts[i] = t_func

    def analyze(self):
        import matplotlib.pyplot as plt

        plt.figure()
        # plt.plot(self.N, -self.ts)
        plt.plot(self.N, -self.ts)
        plt.xlabel('number of floating point multiplications')
        # plt.ylabel('time per multiplication (ns)')
        plt.ylabel('total time (ns)')
        plt.show()

        