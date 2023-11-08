from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)
        self.params.amp_paint = np.linspace(0.,0.5,5)
        self.params.xv_frequency_painting = np.linspace(10.,752.5,4) * 1.e3
        self.t1 = 100.e-3
        self.t2 = 20.e-3

    @kernel
    def run(self):
        self.init_kernel()
        idx = 0
        # for amp in self.params.amp_paint:
        #     for freq in self.params.xv_frequency_painting:
        #         self.lightsheet.set_paint_params(amplitude=amp,frequency=freq)
        #         self.ttl.spectrum_trig.on()
        #         delay(self.t2*s)
        #         self.ttl.spectrum_trig.off()
        #         delay(self.t1*s)
        #         print(idx)
        #         idx += 1
        self.lightsheet.set_paint_params(amplitude=1.0,frequency=153.452e3)
        self.ttl.spectrum_trig.on()
        delay(1*s)
        self.ttl.spectrum_trig.off()
        self.lightsheet.dds.off()