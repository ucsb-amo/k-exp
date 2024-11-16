from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.xvar('dummy',[0]*5)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(self.p.t_feshbach_field_rampup,i_end=self.p.i_evap1_current)
        delay(30.e-3)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid()
        delay(0.5)
        self.outer_coil.off()
        self.outer_coil.stop_pid()
        delay(0.25)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)