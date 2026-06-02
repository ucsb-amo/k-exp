from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_killa(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,suppress_live_od=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel()
        self.prep_raman()
        self.raman.on()
        self.ttl.raman_shutter.on()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)