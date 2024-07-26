from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from kexp.util.artiq.async_print import aprint

from artiq.experiment import kernel, delay

import numpy as np

dv = -102.
dv_list = np.linspace(0.,54.,10)

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
        self.paint_amp_dac.set(v=-7.,load_dac=True)
        self.ttl.off()

    # @kernel
    # def set_paint_amp(self,paint_fraction=dv,load_dac=True):
    #     if paint_fraction == dv:
    #         paint_fraction = 0.
    #     v_dac = DAC_PAINT_FULLSCALE * (2 * paint_fraction - 1)
    #     self.paint_amp_dac.set(v=v_dac,load_dac=load_dac)

    @kernel
    def set_power(self,v_lightsheet_vva=dv,load_dac=True):
        if v_lightsheet_vva == dv:
            v_lightsheet_vva = self.params.v_pd_lightsheet
        self.vva_dac.set(v=v_lightsheet_vva,load_dac=load_dac)
    
    @kernel
    def ramp(self,t,v_list=dv_list,
             paint=False,
             v_awg_am_max=dv,
             v_pd_max=dv,
             keep_trap_frequency_constant=True):

        if v_list == dv_list:
            v_list = self.params.v_pd_lightsheet_ramp_list
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_lightsheet_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_lightsheet_rampup_end

        n_ramp = len(v_list)
        dt_ramp = t / n_ramp

        # initialize an array of the same length, but just ones. 
        # can't initialize a new array, since np functions return a value into
        # kernel without type hinting output class
        v_awg_amp_mod_list = v_list / v_list

        if not paint:
            self.painting_off()
        else:
            if not keep_trap_frequency_constant:
                # set the mod amp list to all the same value
                # it was just ones before, multiply by the value
                v_awg_amp_mod_list = v_awg_amp_mod_list * v_awg_am_max
            else:
                p_frac = v_list / v_pd_max
                paint_amp_frac = p_frac**(1/3)
                v_awg_amp_mod_list = (paint_amp_frac - 0.5)*(v_awg_am_max - (-6)) \
                            + (v_awg_am_max + (-6))/2
        # add a delay to add slack after doing all this math
        delay(500.e-6)

        self.vva_dac.set(v=v_list[0],load_dac=True)
        # self.paint_amp_dac.set(v=v_awg_amp_mod_list[0],load_dac=True)
        self.vva_dac.load()
        self.on()
        delay(dt_ramp)

        for i in range(len(v_list)):
            self.vva_dac.set(v=v_list[i],load_dac=False)
            if paint:
                self.paint_amp_dac.set(v=v_awg_amp_mod_list[i],load_dac=False)
            self.vva_dac.load()
            delay(dt_ramp)

    @kernel(flags={"fast-math"})
    def v_pd_to_painting_amp_voltage(self,v_pd=dv_list,
                                        v_awg_am_max=dv,
                                        v_pd_max=dv):
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_lightsheet_paint_amp_max

        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_lightsheet_rampup_end

        p_frac = v_pd / v_pd_max
        # trap frequency propto sqrt( P / h^3 ), where P is power and h is painting
        # amplitude. To keep constant frequency, h should decrease by a factor equal
        # to the cube root of the fraction by which P changes
        paint_amp_frac = p_frac**(1/3)
        # rescale to between -6V (fraction painting = 0) and the maximum
        # painting amplitude specified (fraction painting = 1) for the
        # AWG input
        v_awg_amp_mod = (paint_amp_frac - 0.5)*(v_awg_am_max - (-6)) \
                            + (v_awg_am_max + (-6))/2
        return v_awg_amp_mod
    
    @kernel
    def painting_off(self):
        self.paint_amp_dac.set(v=-7.)
    
    @kernel
    def zero_pid(self):
        self.pid_int_zero_ttl.pulse(10.e-9)

    @kernel
    def on(self, paint=False, v_awg_am=dv):
        if v_awg_am == dv:
            v_awg_am = self.params.v_tweezer_paint_amp_max
        if paint:
            self.paint_amp_dac.set(v=v_awg_am)
        else:
            self.paint_amp_dac.set(v=-7.)
        self.ttl.on()

    @kernel
    def off(self):
        self.ttl.off()
        self.vva_dac.set(v=self.params.v_pd_lightsheet_pd_minimum)
        self.zero_pid()