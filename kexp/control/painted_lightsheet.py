from waxx.control.artiq.DAC_CH import DAC_CH
from waxx.control.artiq.DDS import DDS
from waxx.control.artiq.TTL import TTL_OUT

from kexp.config.expt_params import ExptParams

from artiq.experiment import kernel, delay, TFloat

import numpy as np

dv = -102.
di = 0
dv_list = np.linspace(0.,54.,10)

DAC_PAINT_FULLSCALE = 9.99

class lightsheet():
    def __init__(self, pid_dac = DAC_CH, paint_amp_dac = DAC_CH,
                 alignment_shim_dac = DAC_CH,
                 sw_ttl = TTL_OUT, pid_int_hold_zero_ttl = TTL_OUT,
                 expt_params = ExptParams):
        """Controls the light sheet beam.

        Args:
            pid_dac (DAC_CH): A DAC channel that controls a VVA to attenuate the
            overall RF that reaches the amp (and thus the AO.) 
            paint_amp_dac (DAC_CH): DAC_CH, voltage controls the painting amplitude via
            controlling the modulation depth. -9.99 V is minimal painting, 9.99
            V is maximal painting. 
            sw_ttl (TTL): TTL channel, controls an RF
            switch between AWG and amplifier.
        """        
        self.pid_dac = pid_dac
        self.paint_amp_dac = paint_amp_dac
        self.ttl_sw = sw_ttl
        self.pid_int_zero_ttl = pid_int_hold_zero_ttl # integrator hold, not zero
        self.alignment_shim_dac = alignment_shim_dac
        self.params = expt_params

    @kernel
    def init(self):
        self.paint_amp_dac.set(v=-7.,load_dac=True)
        self.ttl_sw.off()

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
        self.pid_dac.set(v=v_lightsheet_vva,load_dac=load_dac)
    
    @kernel(flags={"fast-math"})
    def ramp(self,t,
             v_start=dv,
             v_end=dv,
             n_steps=di,
             paint=False,
             v_awg_am_max=dv,
             v_pd_max=dv,
             keep_trap_frequency_constant=True):
        
        if v_start == dv:
            v_start = self.pid_dac.v
        if v_end == dv:
            v_end = self.params.v_pd_lightsheet_rampup_end
        if n_steps == di:
            n_steps = self.params.n_lightsheet_ramp_steps
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_lightsheet_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_lightsheet_rampup_end

        dt_ramp = t / n_steps
        delta_v = (v_end - v_start)/(n_steps - 1)

        if not paint:
            self.painting_off()

        self.pid_dac.set(v=v_start,load_dac=True)
        self.on(paint=paint)
        delay(dt_ramp)

        for i in range(n_steps):
            v = v_start + i*delta_v
            self.pid_dac.set(v=v,load_dac=False)

            if paint:
                if keep_trap_frequency_constant:
                    v_awg_amp_mod = self.v_pd_to_painting_amp_voltage(v)
                else:
                    v_awg_amp_mod = v_awg_am_max
                self.paint_amp_dac.set(v_awg_amp_mod,load_dac=False)

            self.pid_dac.load()
            delay(dt_ramp)

    @kernel(flags={"fast-math"})
    def adiabatic_ramp(self,t,
                v_start=dv,
                v_end=dv,
                n_steps=di,
                paint=False,
                v_awg_am_max=dv,
                v_pd_max=dv,
                keep_trap_frequency_constant=True):
        
        if v_start == dv:
            v_start = self.pid_dac.v
        if v_end == dv:
            v_end = self.params.v_pd_lightsheet_rampup_end
        if n_steps == di:
            n_steps = self.params.n_lightsheet_ramp_steps
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_lightsheet_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_lightsheet_rampup_end

        v_offset = 0.02
        w0 = v_start - v_offset
        wf = v_end - v_offset
        if (w0 <= 0.) or (wf <= 0.):
            raise ValueError('ramp cannot go to zero')

        u = 1. / np.sqrt(w0)
        du = (1. / np.sqrt(wf) - u) / (n_steps - 1)
        dt_mu = np.int64(t / n_steps * 1e9)

        if not paint:
            self.painting_off()

        self.pid_dac.set(v=v_start,load_dac=True)
        self.on(paint=paint)
        delay_mu(dt_mu)

        t_mu = now_mu()
        for i in range(n_steps):
            at_mu(t_mu)
            v = 1. / (u * u) + v_offset

            self.pid_dac.set(v)

            if paint:
                if keep_trap_frequency_constant:
                    v_awg_amp_mod = self.v_pd_to_painting_amp_voltage(v)
                else:
                    v_awg_amp_mod = v_awg_am_max
                self.paint_amp_dac.set(v_awg_amp_mod,load_dac=False)
            
            u += du
            t_mu += dt_mu
            self.pid_dac.load()
        at_mu(t_mu)
        self.pid_dac.v = v_end

    @kernel(flags={"fast-math"})
    def exponential_ramp(self,t,
                v_start=dv,
                v_end=dv,
                tau=dv,
                n_steps=di,
                paint=False,
                v_awg_am_max=dv,
                v_pd_max=dv,
                keep_trap_frequency_constant=True):
            
            if v_start == dv:
                v_start = self.pid_dac.v
            if v_end == dv:
                v_end = self.params.v_pd_lightsheet_rampup_end
            if n_steps == di:
                n_steps = self.params.n_lightsheet_ramp_steps
            if v_awg_am_max == dv:
                v_awg_am_max = self.params.v_lightsheet_paint_amp_max
            if v_pd_max == dv:
                v_pd_max = self.params.v_pd_lightsheet_rampup_end

            if tau == dv:
                tau = - t / 3.

            e_end = np.exp(-t / tau)
            k = np.exp(-(t / (n_steps - 1)) / tau)   # per-step factor, k**(n-1) == e_end
            a = (v_start - v_end) / (1. - e_end)
    
            e = 1.
            dt_mu = np.int64(t / n_steps * 1.e9)

            if not paint:
                self.painting_off()
    
            self.pid_dac.set(v=v_start,load_dac=True)
            self.on(paint=paint)
            delay_mu(dt_mu)
    
            t_mu = now_mu()
            for i in range(n_steps):
                at_mu(t_mu)
                v = v_end + a * (e - e_end)
                self.pid_dac.set(v,load_dac=False)
                if paint:
                    if keep_trap_frequency_constant:
                        v_awg_amp_mod = self.v_pd_to_painting_amp_voltage(v)
                    else:
                        v_awg_amp_mod = v_awg_am_max
                    self.paint_amp_dac.set(v_awg_amp_mod,load_dac=False)
                self.pid_dac.load()
                e *= k
                t_mu += dt_mu
            at_mu(t_mu)
            self.pid_dac.v = v_end

    @kernel(flags={"fast-math"})
    def v_pd_to_painting_amp_voltage(self,v_pd=dv,
                                        v_pd_max=dv,
                                        v_awg_am_max=dv) -> TFloat:
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
            v_awg_am = self.params.v_hf_tweezer_paint_amp_max
        if paint:
            self.paint_amp_dac.set(v=v_awg_am)
        else:
            self.paint_amp_dac.set(v=-7.)
        self.ttl_sw.on()

    @kernel
    def off(self):
        self.ttl_sw.off()
        self.pid_dac.set(v=self.params.v_pd_lightsheet_pd_minimum)
        self.zero_pid()