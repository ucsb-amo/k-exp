from artiq.experiment import *
from kexp import Base
from kexp.config.dds_calibration import power_fraction_to_dds_amplitude
import numpy as np

class ddsamptest(EnvExperiment,Base,):
    def build(self):
        Base.__init__(self,setup_camera=False)
        self.mydds = self.dds.imaging
        self.amp = power_fraction_to_dds_amplitude(np.linspace(0.1,0.001,10))

    @kernel
    def run(self):
        self.init_kernel()

        self.mydds.set_dds(amplitude=self.amp[0])
        self.mydds.on()
        delay(0.5*s)

        for i in range(1,len(self.amp)-1):
            self.mydds.set_dds(amplitude=self.amp[i])
            delay(0.5*s)

        self.mydds.off()
        