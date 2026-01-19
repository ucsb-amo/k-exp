from artiq.experiment import *
from artiq.language.core import now_mu
from kexp import Base
import numpy as np

class capture_data(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      setup_camera=True)
        
        self.xvar('test0',[0,1])
        self.p.N_repeats = 1

        self.data.test = self.data.add_data_container(1,np.float64)
        self.data.all = self.data.add_data_container(per_shot_data_shape=self.sampler.data.shape,
                                                     dtype=self.sampler.data.dtype)
        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.scan()

    @kernel
    def init_scan_kernel(self):

        delay(10.e-3)
        self.sampler.sample()
        delay(10.e-3)

        self.abs_image()

        self.data.apd.put_data(self.sampler.data[0])
        self.data.test.put_data(self.sampler.data[1])
        self.data.all.put_data(self.sampler.data)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)