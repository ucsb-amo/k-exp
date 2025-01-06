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

        # self.xvar('amp_final',np.linspace(.41,.43,20))

        self.p.amp_initial = .3
        self.p.amp_final = .425

        self.p.t_tweezer_amp_ramp = 100.e-3

        a_list = [.0,.51]

        self.p.amp_tweezer_list = a_list

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.tweezer.traps[0].set_amp(self.p.amp_initial,
                                      trigger=False)

        delay(100.e-3)
        
        self.tweezer.traps[0].linear_amplitude_ramp(t_ramp=self.p.t_tweezer_amp_ramp,
                                         amp_f=self.p.amp_final,trigger=False)
        
        delay(300.e-3)

        self.tweezer.trigger()

        delay(.5)

        self.tweezer.trigger()
        
        delay(self.p.t_tweezer_amp_ramp)

        self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)