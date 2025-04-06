from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class lightsheet_from_magtrap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='xy_basler',save_data=False)

        self.xvar('dummy',[0]*10)
        self.p.t_ramp = 100.e-3
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.lightsheet.on()
        self.lightsheet.ramp(self.p.t_ramp,
                             v_start=0.,v_end=9.0)
        self.lightsheet.off()
        delay(1.)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)