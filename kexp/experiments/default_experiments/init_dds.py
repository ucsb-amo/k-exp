from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class init_dds(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION,
                      suppress_live_od=True)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        pass
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         dds_set=True,
                         dds_off=False,
                    init_dds = True, 
                    init_sampler = False,
                    init_imaging = False,
                    init_shuttler = False, 
                    init_lightsheet = False,
                    setup_slm = False,
                    init_magnets = False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
        
        