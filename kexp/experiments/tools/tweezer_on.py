from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.base.base import Base
import numpy as np

class TweezerOn(EnvExperiment, Base):
    def build(self):
        Base.__init__(self,setup_camera=False)
        self.p.v_pd_tweezer_1064 = 0.3
        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.tweezer.on()
        delay(1.)
        self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()