from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu
from kexp import Base, img_types, cameras
import numpy as np

class feedback(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.DISPERSIVE)
        
        self.finish_prepare()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    @kernel
    def scan_kernel(self):
        self.init_scan_kernel()

        self.core.break_realtime()
        self.prep_raman()

        delay(10.e-3)

        t = now_mu()
        self.raman.set_frequency_fast(120.e6)
        tf = now_mu() - t
        
        self.core.break_realtime()
        print(tf)