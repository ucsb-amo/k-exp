from artiq.experiment import *
from artiq.language.core import now_mu, delay
from kexp import Base, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint

class scope_data(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor)
        self.xvar('test',range(2))
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        delay(0.1)

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.abs_image()

        delay(0.1)

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         init_dac=False,
                         beat_ref_on=False,
                         setup_slm=False,
                         init_ry=False,
                         init_lightsheet=False,
                         init_shuttler=False)
        
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)