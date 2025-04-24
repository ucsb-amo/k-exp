from artiq.experiment import *
from artiq.experiment import delay
from artiq.language.core import now_mu
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)
        self.finish_prepare(shuffle=True)

    def test_rpc(self):
        self.slm.write_phase_spot()

    @kernel
    def scan_kernel(self):
        self.ttl.camera.pulse(1.e-6)
        delay(5.)
        self.slm.write_phase_spot()
        self.ttl.camera.pulse(1.e-6)
       
    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)