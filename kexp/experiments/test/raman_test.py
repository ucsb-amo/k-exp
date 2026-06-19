from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_killa(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      save_data=False,
                      suppress_live_od=True)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.prep_raman(phase_mode=0)
        self.dds.dds_lo.set_dds(frequency=self.raman.frequency_transition/2)
        self.dds.dds_lo.on()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)