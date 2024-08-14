from artiq.experiment import *
from artiq.experiment import delay
# from kexp import Base
import numpy as np

from artiq.coredevice.sampler import Sampler
from artiq.coredevice.zotino import Zotino

class sampler_test(EnvExperiment):

    def prepare(self):
        # Base.__init__(self,save_data=False,
        #               setup_camera=False,
        #               camera_select='xy_basler')

        self.core = self.get_device("core")

        self.dac = self.get_device("zotino0")
        self.dac: Zotino
        
        self.sampler = self.get_device("sampler0")
        self.sampler: Sampler
        self.data = np.zeros(8)
        # self.finish_prepare(shuffle=False)

    @kernel
    def run(self):
        self.core.reset()
        self.sampler.init()
        self.dac.init()

        self.core.break_realtime()

        ch = 0

        v = [0.,1.,2.,3.,4.,5.,6.,7.]
        # self.dac.write_dac(ch,v[0])
        # self.dac.write_dac(ch,1.5)
        # self.dac.load()

        n_ch = 8
        for i in range(n_ch):
            self.sampler.set_gain_mu(i,0)
        
        self.core.break_realtime()
        n_samples = 8
        sample = [0.]*n_ch

        for n in range(n_samples):

            # self.core.break_realtime()
            # self.dac.write_dac(ch,v[n])
            # self.dac.load()
            # self.core.break_realtime()

            delay(1000*ms)
            self.sampler.sample(sample)
            print(sample[0])

