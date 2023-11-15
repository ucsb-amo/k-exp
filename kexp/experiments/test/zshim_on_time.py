from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class zshim(EnvExperiment, Base):
    def build(self):
        Base.__init__(self)
        self.p = self.params

    @kernel
    def run(self):
        self.init_kernel()

        self.dac.zshim_current_control.set(v=self.p.v_zshim_current)
        delay(1*s)
        
        with parallel:
            self.ttl.machine_table_trig.on()
            self.dac.zshim_current_control.set(v=9.99)

        delay(1*s)
        self.dac.zshim_current_control.set(v=self.p.v_zshim_current)
        self.ttl.machine_table_trig.off()

        self.mot_observe()