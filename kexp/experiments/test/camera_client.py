from artiq.experiment import *
from artiq.language.core import now_mu, delay
from kexp import Base, cameras, img_types
import numpy as np

from kexp.util.artiq.async_print import aprint

class camera_client_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      camera_select=cameras.xy_basler,
                      save_data=False)
        
        self.xvar('xvar0',np.arange(500))
        # self.xvar('xvar1',np.arange(9))

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        delay(100.e-3)

        self.abs_image()


    @kernel
    def run(self):
        self.init_kernel()

        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        