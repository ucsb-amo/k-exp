from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class multi_image_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select='andor',
                      absorption_image=True)

        self.xvar('p1',[0,1])
        # self.xvar('p2',[0,1,2])
        # self.xvar('dum')
        self.p.N_pwa_per_shot = 3

        self.p.N_repeats = 2

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
        self.init_kernel(setup_awg=False,dds_off=False,init_dds=True,dds_set=False,init_dac=False,init_lightsheet=False,init_shuttler=False)
        # self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)