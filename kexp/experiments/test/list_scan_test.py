from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.p.frequency_tweezer_auto_compute = False
        self.p.n_tweezers = 2
        # self.p.frequency_tweezer_list = [1.,2.,3.]
        self.xvar('frequency_tweezer_list',[np.array([1.,2.]),np.array([3.,4.])])
        # self.xvar('frequency_tweezer_spacing',np.linspace(0.1,1.,3))
        # self.xvar('frequency_aod_center',np.linspace(0.1,1.,3))
        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.core.break_realtime()
        # aprint(self.p.x)
        aprint(self.p.frequency_tweezer_list)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()