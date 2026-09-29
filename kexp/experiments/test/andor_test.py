from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.xvar('dimension_slm_mask',np.linspace(5.,50.,15)*1.e-6)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.slm.write_phase_mask_kernel()
            
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()

        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)