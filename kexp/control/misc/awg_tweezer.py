from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from kexp.util.artiq.async_print import aprint

from artiq.experiment import kernel, delay

import numpy as np

dv = -1.
dv_list = np.linspace(0.,1.,5)

class tweezer():
    def __init__(self, sw_ttl:TTL, expt_params:ExptParams):
        """Controls the light sheet beam.

        Args:
            sw_ttl (TTL): TTL
            channel, controls the trigger input to the AWG.
        """        
        self.ttl = sw_ttl
        self.params = expt_params

    @kernel
    def on(self):
        self.ttl.on()

    @kernel
    def off(self):
        self.ttl.off()