from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from kexp.calibrations.magnets import compute_pid_overhead

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True)

        self.xvar('dummy',[0]*15)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)