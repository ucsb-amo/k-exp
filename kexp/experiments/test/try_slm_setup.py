from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint

class lightsheet_from_magtrap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,camera_select=cameras.andor,
                      setup_camera=True,
                      imaging_type=img_types.DISPERSIVE)

        self.params.N_pwa_per_shot = 3
        # self.xvar('t_pwa_image',np.linspace(0.,100.,10)*1.e-3,live_flag=True)

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False, setup_slm=False)
        self.scan()
    
    @kernel
    def scan_kernel(self):
        
        self.light_image()
        delay(100.e-3)
        self.light_image()
        delay(100.e-3)
        self.light_image()
        delay(100.e-3)
        
        # self.light_image()
        # delay(100.e-3)
        self.dark_image()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)