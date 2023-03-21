from artiq.experiment import *
from artiq.experiment import delay, parallel
from kexp.base.base import Base
import numpy as np

class ChangeDDS(EnvExperiment,Base):
    def build(self):
        Base.__init__(self)
        
        self.dds.get_dds_devices(self)

        self.params.f0 = 136.3
        self.params.f1 = self.dds.d1_3d_r.detuning_to_frequency(3.5)
        print(self.params.f1)

    @kernel
    def run(self):
        self.init_kernel()

        self.dds.d1_3d_r.set_dds(freq_MHz=self.params.f0)
        self.dds.d1_3d_r.on()

        delay(1*s)

        self.dds.d1_3d_r.set_dds(freq_MHz=self.params.f1)
        
        delay(1*s)
        
        self.dds.d1_3d_r.off()
        
        