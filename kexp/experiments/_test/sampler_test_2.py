from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

from artiq.coredevice.sampler import Sampler

from kexp.util.artiq.async_print import aprint

class samp(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,save_data=False,setup_camera=False)

        self.sampl = self.get_device('sampler0')
        from artiq.coredevice.sampler import Sampler
        self.sampl: Sampler

        self.samples = np.zeros(8,dtype=float)

        self.finish_prepare(shuffle=False)

    @kernel
    def run(self):
        self.init_kernel()

        # self.dds.tweezer_pid_1.on()
        # self.dds.tweezer_pid_1.set_dds(set_stored=True)
        # self.dds.tweezer_pid_2.on()
        # self.dds.tweezer_pid_2.set_dds(set_stored=True)

        self.sampl.init()
        self.sampl.set_gain_mu(0,0)
        self.core.break_realtime()
        self.dac.test_dac.set(1.)
        self.core.break_realtime()
        self.sampl.sample(self.samples)
        self.core.break_realtime()
        
    def analyze(self):

        print(self.samples)

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


