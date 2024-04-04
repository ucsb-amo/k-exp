from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

from artiq.coredevice.sampler import Sampler

class samp(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,save_data=False,
                      setup_camera=False,
                      camera_select='xy_basler')
        
        self.sampler = self.get_device("sampler0")
        self.sampler: Sampler
        self.data = np.zeros(8)
        self.finish_build(shuffle=False)

    # @kernel
    # def scan_kernel(self):
    #     self.data

    @kernel
    def run(self):
        data1 = [0.,0.,0.,0.,0.,0.,0.,0.]
        data2 = [0.,0.,0.,0.,0.,0.,0.,0.]
        self.init_kernel()
        self.sampler.init()

        self.core.break_realtime()

        v = [1.,0.,7.,3.,5.]
        self.dac.set(28,v[0])

        n_ch = 8
        for i in range(n_ch):
            self.sampler.set_gain_mu(i,0)
        
        self.core.break_realtime()
        n_samples = 4
        sample = [0.]*n_ch

        for n in range(n_samples):
            delay(100*us)
            self.sampler.sample(sample)
            print(sample[0])

            self.core.break_realtime()
            self.dac.set(28,v[n+1])
            self.core.break_realtime()
            # delay(1*s)

    def analyze(self):

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


