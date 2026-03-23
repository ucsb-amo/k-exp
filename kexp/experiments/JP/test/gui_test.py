from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

from kexp.util.artiq.async_print import aprint

class gui_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.xvar('amp_imaging',[0.1,0.2,0.3]*2)

        self.finish_prepare(shuffle=True)
    @kernel
    def scan_kernel(self):
        self.imaging.set_power(self.p.amp_imaging)
        delay(200.e-3)
        self.abs_image()

        # self.data.images._put_shot_data()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # print('hji')

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)