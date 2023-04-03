from artiq.experiment import *
from kexp.base.base import Base
import numpy as np

class TestDDS_setGamma(EnvExperiment, Base):
    def build(self):
        Base.__init__(self)
        self.params.gamma = 3
        self.testgammas = np.linspace(0,10,5)
    
    # @kernel
    # def test(self,v) -> TList(TFloat):
    #     for idx in range(len(v)):
    #         v[idx] = v[idx] ** 2
    #     return v

    @kernel
    def run(self):
        self.init_kernel()
        for v in self.testgammas:
            print(self.dds.d1_3d_c.detuning_to_frequency(v))
        self.core.reset()
        self.dds.d1_3d_c.set_dds_gamma(2.)