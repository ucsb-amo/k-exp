from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=True)
        
        self.xvar('dummy',[0.]*3)

        self.p.frequency_tweezer_list = [70.15e6,79.7e6]
        a_list = [0.,.24]
        self.p.amp_tweezer_list = a_list

        self.finish_prepare(shuffle=True)

        print(self.tweezer.traps[0].frequency)

    @kernel
    def scan_kernel(self):

        print(self.tweezer.traps[0].position,
              self.tweezer.traps[0].frequency,
              self.tweezer.traps[0].amplitude)
        
        self.tweezer.cubic_move(0,1.e-3,10.e-6)
        self.tweezer.linear_amplitude_ramp(0,1.e-3,0.6)

        print(self.tweezer.traps[0].position,
              self.tweezer.traps[0].frequency,
              self.tweezer.traps[0].amplitude)

    @kernel
    def run(self):
        self.init_kernel(init_dds=False,
                         init_dac=False,
                         init_lightsheet=False,
                         init_shuttler=False,
                         dds_set=False,
                         dds_off=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)