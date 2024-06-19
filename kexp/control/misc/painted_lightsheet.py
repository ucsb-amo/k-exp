from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from kexp.util.artiq.async_print import aprint

from artiq.experiment import kernel, delay

import numpy as np

dv = -100.
dv_list = np.linspace(0.,1.,5)

DAC_PAINT_FULLSCALE = 9.99

class lightsheet():
    def __init__(self, vva_dac:DAC_CH, paint_amp_dac:DAC_CH,
                  sw_ttl:TTL, pid_int_hold_zero_ttl:TTL,
                  expt_params:ExptParams):
        """Controls the light sheet beam.

        Args:
            vva_dac (DAC_CH): A DAC channel that controls a VVA to attenuate the
            overall RF that reaches the amp (and thus the AO.) 
            paint_amp_dac (DAC_CH): DAC_CH, voltage controls the painting amplitude via
            controlling the modulation depth. -9.99 V is minimal painting, 9.99
            V is maximal painting. 
            sw_ttl (TTL): TTL channel, controls an RF
            switch between AWG and amplifier.
        """        
        self.vva_dac = vva_dac
        self.paint_amp_dac = paint_amp_dac
        self.ttl = sw_ttl
        self.pid_int_zero_ttl = pid_int_hold_zero_ttl
        self.params = expt_params

    @kernel
    def init(self):
        self.paint_amp_dac.set(v=-9.99,load_dac=True)
        self.ttl.off()

    @kernel
    def set_paint_amp(self,paint_fraction=dv,load_dac=True):
        if paint_fraction == dv:
            paint_fraction = 0.
        v_dac = DAC_PAINT_FULLSCALE * (2 * paint_fraction - 1)
        self.paint_amp_dac.set(v=v_dac,load_dac=load_dac)

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
    def ramp_down2(self,t,v_ramp_list=dv_list):
        if v_ramp_list == dv_list:
            v_ramp_list = self.params.v_pd_lightsheet_ramp_down2_list

        n_ramp = len(v_ramp_list)
        dt_ramp = t / n_ramp

        self.vva_dac.set(v=v_ramp_list[0])
        self.on()
        delay(dt_ramp)
        self.zero_pid()
        for v in v_ramp_list[1:]:
            self.vva_dac.set(v=v)
            delay(dt_ramp)
    
    @kernel
    def zero_pid(self):
        self.pid_int_zero_ttl.pulse(10.e-9)

    @kernel
    def on(self):
        self.ttl.on()

    @kernel
    def off(self):
        self.ttl.off()
        self.vva_dac.set(v=self.params.v_pd_lightsheet_pd_minimum)
        self.zero_pid()