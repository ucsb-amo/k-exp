from artiq.experiment import *
from artiq.experiment import delay, TArray, TFloat
from artiq.language.core import now_mu
from kexp import Base
import numpy as np

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=False)
        self.xvar('test',[0])

        self.vec = np.linspace(0.,0.,1000)

        self.finish_prepare(shuffle=True)

    def test(self) -> TArray(TFloat):

        N = 100
        self.vec[0:N] = np.linspace(0.,10.,N)
        return self.vec

    @kernel
    def scan_kernel(self):
        self.core.reset()

        print(self.params.v_pd_c_gmramp_list[0])
        self.vec = self.test()
        print(self.params.v_pd_c_gmramp_list[0])

    @kernel
    def run(self):
        self.init_kernel(init_dds=False,init_dac=False,init_shuttler=False,
                         init_lightsheet=False,dds_set=False,dds_off=False)
        self.scan()