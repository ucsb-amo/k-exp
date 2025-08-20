from artiq.experiment import *
from artiq.experiment import delay

import numpy as np

from artiq.coredevice.sampler import Sampler
from artiq.coredevice.zotino import Zotino

class sampler_test(EnvExperiment):

    def prepare(self):
        self.core = self.get_device("core")

        self.dac = self.get_device("zotino0")
        self.dac: Zotino
        
        self.sampler = self.get_device("sampler0")
        self.sampler: Sampler
        self.data = np.zeros(8,dtype=float)

        self.v = np.array([1.]*8)

    @kernel
    def run(self):
        self.core.reset()
        self.sampler.init()
        self.dac.init()

        self.core.break_realtime()

        ch = 30
        
        for i in range(len(self.data)):
            self.sampler.set_gain_mu(i,0)
        
        self.core.break_realtime()

        for n in range(len(self.data)):

            self.core.break_realtime()
            self.dac.write_dac(ch,self.v[n])
            self.dac.load()
            self.core.break_realtime()

            delay(1000*ms)
            self.sampler.sample(self.data)
            print(self.data[0])