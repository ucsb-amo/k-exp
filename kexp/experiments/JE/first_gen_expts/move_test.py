from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=False)

        self.xvar('dummy',[1])
        self.p.frequency_tweezer_list = [73.3e6,77.e6]

        self.p.t_move = 5.
        self.p.x_move = 5.e-6

        self.p.amp_tweezer_list = [.1,.0]

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.tweezer.traps[0].cubic_move(t_move=self.p.t_move,
                                         x_move=self.p.x_move,
                                         dt=1.e-3,
                                         trigger=False)

        self.tweezer.on()
        self.tweezer.trigger()
        delay(self.p.t_move)
        self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)