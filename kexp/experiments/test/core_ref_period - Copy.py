from artiq.experiment import *
from artiq.experiment import delay_mu
from artiq.language.core import now_mu
import numpy as np

class core_ref(EnvExperiment):
    def build(self):
        self.core = self.get_device("core")

        self.t1 = np.int64(0)
        self.t2 = np.int64(0)

    @kernel
    def run(self):
        self.t1 = now_mu()
        delay_mu(1)
        self.t2 = now_mu()

    def analyze(self):
        print(f"t1 = {self.t1} mu")
        print(f"t2 = {self.t2} mu")

        print("")
        print(self.t1 & ~7)
        print(self.t2 & ~7)