from artiq.experiment import *
from artiq.experiment import delay

import numpy as np

from artiq.coredevice.sampler import Sampler
from artiq.coredevice.zotino import Zotino

from kexp import Base

class sampler_test(EnvExperiment,Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(init_dds=False,
                         dds_set=False,
                         dds_off=False,
                         beat_ref_on=False,
                         init_shuttler=False,
                         init_lightsheet=False,
                         setup_awg=False)

        self.sampler.init()

        ch = 30

        v = [0.,1.,2.,3.,4.,5.,6.,7.]
        
        self.core.break_realtime()

        self.dac.dac_device.write_dac(ch,v[7])
        self.dac.load()
        self.core.break_realtime()

        for n in range(8):

            # self.core.break_realtime()
            # self.dac.dac_device.write_dac(ch,v[n])
            # self.dac.load()
            # self.core.break_realtime()

            delay(1000*ms)
            # self.sampler.sample(self.data)
            # print(self.data[0])
            # print(self.sampler.test.sample())
            self.sampler.sample()
            print(self.sampler.samples)