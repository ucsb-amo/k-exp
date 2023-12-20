from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from kexp.util.artiq.async_print import aprint

from artiq.experiment import kernel, delay

import numpy as np

dv = -1.
dv_list = np.linspace(0.,1.,5)

class lightsheet():
    def __init__(self, vva_dac:DAC_CH, paint_amp_dac:DAC_CH, sw_ttl:TTL, expt_params:ExptParams):
        """Controls the light sheet beam.

        Args:
            dac_ch (DAC_CH): A DAC channel that controls a VVA to attenuate the
            overall RF that reaches the amp (and thus the AO.) 
            paint_dds (DDS):
            DDS channel, amplitude controls the painting amplitude, frequency
            controls the modulation freuqency of the RF. 
            sw_ttl (TTL): TTL
            channel, controls an RF switch between AWG and amplifier.
        """        
        self.vva_dac = vva_dac
        self.paint_amp_dac = paint_amp_dac
        self.ttl = sw_ttl
        self.params = expt_params

    @kernel
    def set_paint_amp(self,v_paint_amp=dv,load_dac=True):
        if v_paint_amp == dv:
            v_paint_amp = 0.0
        self.vva_dac.set(v=v_paint_amp,load_dac=load_dac)

    @kernel
    def set_power(self,v_lightsheet_vva=dv,load_dac=True):
        if v_lightsheet_vva == dv:
            v_lightsheet_vva = self.params.v_pd_lightsheet
        self.vva_dac.set(v=v_lightsheet_vva,load_dac=load_dac)
    
    @kernel
    def ramp(self,t,v_ramp_list=dv_list):
        if v_ramp_list == dv_list:
            v_ramp_list = self.params.v_pd_lightsheet_ramp_list

        n_ramp = len(v_ramp_list)
        dt_ramp = t / n_ramp

        self.vva_dac.set(v=v_ramp_list[0])
        self.on()
        delay(dt_ramp)
        for v in v_ramp_list[1:]:
            self.vva_dac.set(v=v)
            delay(dt_ramp)
    
    @kernel
    def ramp_down(self,t,v_ramp_list=dv_list):
        if v_ramp_list == dv_list:
            v_ramp_list = self.params.v_pd_lightsheet_ramp_down_list

        n_ramp = len(v_ramp_list)
        dt_ramp = t / n_ramp

        self.vva_dac.set(v=v_ramp_list[0])
        self.on()
        delay(dt_ramp)
        for v in v_ramp_list[1:]:
            self.vva_dac.set(v=v)
            delay(dt_ramp)

    @kernel
    def on(self):
        self.ttl.on()

    @kernel
    def off(self):
        self.ttl.off()