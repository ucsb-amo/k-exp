from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION)

        self.camera_params = cameras.andor
        self.ttl.camera = self.ttl.andor

        self.xvar('beans',[1]*1000)

        # self.p.amp_imaging = .25
        self.p.amp_imaging = .2

        self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time
        self.p.t_imaging_pulse = 10.e-6
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_m1,
                                  amp=self.p.amp_imaging)
        delay(0.25)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        # self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)