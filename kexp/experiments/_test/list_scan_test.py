from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.xvar('hi',[[1.,2.],[3.,4.]])
        self.xvar('b',[1,2])
        # print(self.p.hi)
        print(self.scan_xvars[0].values.shape)
        self.finish_prepare()

    # @kernel
    # def scan_kernel(self):
    #     self.core.break_realtime()
    #     aprint(self.p.hi)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()