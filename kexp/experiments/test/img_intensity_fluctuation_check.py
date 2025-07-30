from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class mot_kill_405(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      imaging_type=img_types.DISPERSIVE,
                      camera_select=cameras.andor)
        
        self.xvar('dummy',[1]*8)
        self.p.N_pwa_per_shot = 10

        self.p.amp_imaging = cameras.andor.__amp_absorption__

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        delay(75.e-3)

        for _ in range(self.p.N_pwa_per_shot):
            self.light_image()
            delay(75.e-3)
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         init_lightsheet=False,
                         init_shuttler=False,
                         setup_slm=False)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)