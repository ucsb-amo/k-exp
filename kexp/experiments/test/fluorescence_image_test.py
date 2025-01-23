from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np

class flimage_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      imaging_type=img_types.FLUORESCENCE,
                      setup_camera=True,
                      camera_select='andor',
                      save_data=False)
        
        self.xvar('dummy',[1])

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.release()

        delay(self.p.t_tof)
        self.flimage_single()

        delay(self.camera_params.t_light_only_image_delay)
        self.flimage_single()

        delay(self.camera_params.t_dark_image_delay)
        self.flimage_single(with_light=False)
       
    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)