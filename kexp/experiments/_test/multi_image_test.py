from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class multi_image_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select='andor',
                      absorption_image=False)

        self.xvar('p1',[0,1])
        self.xvar('p2',[0,1,2])
        self.p.N_pwa_per_shot = 5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        for _ in range(self.p.N_pwa_per_shot):
            self.light_image()
            delay(100.e-3)
        if self.run_info.absorption_image:
            self.light_image()
            delay(100.e-3)
            self.dark_image()
            delay(100.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)