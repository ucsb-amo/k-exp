from artiq.experiment import *
from artiq.experiment import delay, TArray, TFloat
import numpy as np
from kexp.config import ExptParams

class tweezer_load(EnvExperiment):

    def prepare(self):
        self.core = self.get_device("core")
        
        self.vec = np.linspace(0.,0.,1000)

        self.params = ExptParams()
        self.params.v_pd_c_gmramp_list = np.ones(1000)

    def test(self) -> TArray(TFloat):

        N = 100
        self.vec[0:N] = np.linspace(0.,10.,N)
        return self.vec
    
    @kernel
    def run(self):
        self.core.reset()

        print(self.params.v_pd_c_gmramp_list[0])
        self.vec = self.test()
        print(self.params.v_pd_c_gmramp_list[0])