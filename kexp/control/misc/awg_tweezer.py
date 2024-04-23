from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from kexp.util.artiq.async_print import aprint

from artiq.experiment import kernel, delay

import numpy as np

dv = -1.
dv_list = np.linspace(0.,1.,5)

class tweezer():
    def __init__(self, vva_dac:DAC_CH, sw_ttl:TTL, expt_params:ExptParams):
        """Controls the light sheet beam.

        Args:
            sw_ttl (TTL): TTL
            channel, controls the trigger input to the AWG.
        """        
        self.vva_dac = vva_dac
        self.ttl = sw_ttl
        self.params = expt_params

    @kernel
    def on(self):
        self.ttl.on()
        # self.vva_dac.set(v=0.)
        # self.vva_dac.set(v=5.)

    @kernel
    def off(self):
        self.ttl.off()
        # self.vva_dac.set(v=0.)

    @kernel
    def set_power(self,v_tweezer_vva=dv,load_dac=True):
        if v_tweezer_vva == dv:
            v_tweezer_vva = self.params.v_pd_tweezer_1064
        self.vva_dac.set(v=v_tweezer_vva,load_dac=load_dac)

    @kernel
    def ramp(self,t,v_ramp_list=dv_list):
        if v_ramp_list == dv_list:
            v_ramp_list = self.params.v_pd_tweezer_1064_ramp_list

        n_ramp = len(v_ramp_list)
        dt_ramp = t / n_ramp

        self.vva_dac.set(v=v_ramp_list[0])
        self.on()
        delay(dt_ramp)
        for v in v_ramp_list[1:]:
            self.vva_dac.set(v=v)
            delay(dt_ramp)