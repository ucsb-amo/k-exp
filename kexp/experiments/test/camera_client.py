from artiq.experiment import *
from artiq.language.core import now_mu, delay
from kexp import Base, cameras, img_types
import numpy as np

from kexp.util.artiq.async_print import aprint

class camera_client_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      camera_select=cameras.xy_basler)
        
        self.xvar('dummy',[0,1,2,3])

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        delay(100.e-3)

        self.abs_image()

        aprint('hi')


    @kernel
    def run(self):
        self.init_kernel()

        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        self.live_od_client.send_run_complete()