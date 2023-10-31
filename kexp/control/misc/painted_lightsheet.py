from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams

from artiq.experiment import kernel, delay

import numpy as np

dv = -1.
dv_list = np.linspace(0.,1.,5)

class lightsheet():
    def __init__(self, dac_ch:DAC_CH, paint_dds:DDS, sw_ttl:TTL, expt_params:ExptParams):
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
        self.dac_ch = dac_ch
        self.dds = paint_dds
        self.ttl = sw_ttl
        self.params = expt_params

    @kernel
    def set_paint_params(self,amplitude=dv,frequency=dv):
        if frequency == dv:
            frequency = self.params.frequency_painting
        if amplitude == dv:
            amplitude = self.params.amp_painting
        self.dds.set_dds(frequency=frequency,amplitude=amplitude)
        self.dds.on()

    @kernel
    def set_power(self,v_lightsheet_vva=dv,load_dac=True):
        if v_lightsheet_vva == dv:
            v_lightsheet_vva = self.params.v_pd_lightsheet
        self.dac_ch.set(v=v_lightsheet_vva,load_dac=load_dac)
    
    @kernel
    def ramp(self,t_ramp,v_ramp_list=dv_list):
        if v_ramp_list == dv_list:
            v_ramp_list = self.params.v_pd_lightsheet_ramp_list

        n_ramp = len(v_ramp_list)
        dt_ramp = t_ramp / n_ramp

        self.dac_ch.set(v=v_ramp_list[0])
        self.on()
        delay(dt_ramp)
        for v in v_ramp_list[1:]:
            self.dac_ch.set(v=v)
            delay(dt_ramp)

    @kernel
    def on(self):
        self.ttl.on()

    @kernel
    def off(self):
        self.ttl.off()

    @kernel
    def set(self,amplitude=dv,frequency=dv,v_lightsheet_vva=dv):
        self.set_paint_params(amplitude=amplitude,frequency=frequency)
        self.set_power(v_lightsheet_vva=v_lightsheet_vva)