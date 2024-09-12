from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class grabber(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=False)
        self.out = [0]
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        n = [0]
        
        self.core.break_realtime()
        self.ttl.camera.pulse(1.e-6)
        self.grabber.gate_roi(0b1)
        # self.grabber.gate_roi(0b01)
        # delay(self.camera_params.exposure_time)
        # self.grabber.gate_roi(0b00)
        # self.grabber.input_mu(self.out)
        delay(10.*ms)
        self.grabber.input_mu(n,100000000)
        delay(10.*ms)
        self.grabber.gate_roi(0b0)
        delay(100.*ms)

        self.ttl.camera.pulse(1.e-6)
        delay(100.*ms)
        self.ttl.camera.pulse(1.e-6)

        print(n)

    @kernel
    def run(self):
        self.init_kernel()
        self.grabber.setup_roi(0,1,1,5,5)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)