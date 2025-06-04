from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint

class multi_image_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.DISPERSIVE)

        # self.xvar('p1',[0,1])
        # self.xvar('p2',[0,1,2])
        # self.xvar('dum')
        self.p.N_pwa_per_shot = 3

        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.reset_imaging_beam_settings()

        self.set_imaging_shutters()
        for _ in range(self.p.N_pwa_per_shot):
            self.light_image()
            delay(100.e-3)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         dds_off=False,
                         init_dds=True,
                         dds_set=False,
                         init_dac=False,
                         init_lightsheet=False,
                         init_shuttler=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)