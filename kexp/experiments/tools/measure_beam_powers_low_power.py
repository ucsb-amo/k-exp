from artiq.experiment import *
from kexp import Base
import os

import numpy as np

class measure_beam_powers(EnvExperiment, Base):

    def build(self):
        Base.__init__(self, setup_camera = False)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.dds.d2_2d_c.set_dds_gamma(delta=self.params.detune_d2_c_2dmot,amplitude=0.04)
        self.dds.d2_2d_r.set_dds_gamma(delta=self.params.detune_d2_r_2dmot,amplitude=0.04)
        self.dds.d2_3d_c.set_dds_gamma(delta=self.params.detune_d2_c_mot,amplitude=0.05)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.params.detune_d2_r_mot,amplitude=0.1)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.params.detune_d1_c_gm,amplitude=0.3,v_pd=1.0)
        self.dds.d1_3d_r.set_dds_gamma(delta=self.params.detune_d1_r_gm,amplitude=0.3,v_pd=1.0)
        self.dds.push.set_dds_gamma(delta=self.params.detune_push,amplitude=0.188)
        self.dds.optical_pumping.set_dds_gamma(delta=self.params.detune_optical_pumping_op,amplitude=0.08)
        self.dds.op_r.set_dds_gamma(delta=self.params.detune_optical_pumping_r_op,amplitude=0.1)
        self.dds.imaging.set_dds(frequency=self.params.frequency_ao_imaging,amplitude=0.5)

        self.dds.d2_2d_c.on()
        self.dds.d2_2d_r.on()
        self.dds.d2_3d_c.on()
        self.dds.d2_3d_r.on()
        # self.dds.d1_3d_c.on()
        # self.dds.d1_3d_r.on()
        # self.dds.push.on()
        # self.dds.optical_pumping.on()
        # self.dds.op_r.on()
        self.dds.imaging.on()

    def analyze(self):

        print("Done!")