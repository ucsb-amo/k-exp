from artiq.experiment import *
from kexp import Base

import numpy as np

class measure_beam_powers(EnvExperiment, Base):

    def build(self):
        Base.__init__(self, setup_camera = False)

    @kernel
    def run(self):
        
        self.init_kernel()
        delay(50*ms)

        self.load_2D_mot(10*ms)

        self.mot(10*ms)

        self.gm(10*ms)

        self.dds.optical_pumping.set_dds_gamma(delta=self.params.detune_optical_pumping_op,
                                               amplitude=self.params.amp_optical_pumping_op)

        self.dds.imaging.set_dds(frequency=self.params.frequency_ao_imaging,
                                       amplitude=self.params.amp_imaging_abs)

        self.dds.lightsheet.set_dds(frequency=self.params.frequency_ao_lightsheet,
                                          amplitude=self.params.amp_lightsheet)

        self.dds.tweezer.set_dds(frequency=self.params.frequency_ao_1227,
                                 amplitude=self.params.amp_1227)
        
        self.switch_all_dds(1)

    def analyze(self):

        print("Done!")