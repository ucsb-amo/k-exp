from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from waxx.util.artiq.async_print import aprint

class lightsheet_from_magtrap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=True)

        self.xvar('x', [0]*10000)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.ttl.test_ttl.pulse(t=1.e-8)
        self.dds.ry_405_sw.on()
        delay(1.)
        self.dds.ry_405_sw.off()

    @kernel
    def run(self):
        self.init_kernel(dds_off=False,setup_awg=False,setup_slm=False,init_lightsheet=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)