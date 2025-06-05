from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_killa(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel()
        self.ttl.pd_scope_trig()
        self.ttl.imaging_shutter_x.on()
        self.dds.imaging.on()
        delay(0.7e-6)
        self.dds.imaging.off()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)