from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.base.base import Base
import numpy as np

class ZotinoSet(EnvExperiment, Base):
    def build(self):
        Base.__init__(self,setup_camera=False)

    @kernel
    def run(self):
        self.init_kernel()
        self.zotino.write_dac(self.dac_ch_zshim_current_control,3.0)
        self.zotino.load()