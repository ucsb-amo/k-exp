from waxx.control.artiq.DAC_CH import DAC_CH
from waxx.control.artiq.TTL import TTL
from waxx.control.artiq.DDS import DDS
import waxx.control.tweezer.spectrum_DDS_tweezer as wax_tweezer

from artiq.language.core import now_mu
from artiq.coredevice.core import Core
from artiq.experiment import rpc, kernel, delay, parallel, TFloat, portable, TArray, TInt32

from kexp.config.expt_params import ExptParams
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

import numpy as np

# di = 666420695318008 #causes failure #lmao
di = 0
dv = -1000.

AWG_IP = 'TCPIP::192.168.1.83::inst0::INSTR'
from kexp.calibrations.tweezer import tweezer_xmesh as KEXP_TWEEZER_XMESH

class TweezerTrap(wax_tweezer.TweezerTrap):
    def __init__(self,
                 position=dv,
                 amplitude=dv,
                 cateye:bool=False,
                 frequency=dv,
                 awg_trigger_ttl=TTL,
                 expt_params=ExptParams(),
                 core=Core):
        
        super().__init__(position=position,
                         amplitude=amplitude,
                         cateye=cateye,
                         frequency=frequency,
                         tweezer_xmesh=KEXP_TWEEZER_XMESH,
                         awg_trigger_ttl=awg_trigger_ttl,
                         expt_params=expt_params,
                         core=core)
    
class tweezer(wax_tweezer.TweezerController):
    """
    Machine-specific implementation of the spectrum AWG-controlled tweezers.
    This class should be used for things which interface with an aritisinal
    implementation of the device. For move-related code that is general to the
    AWG-controlled tweezer, edit the wax class.
    """    

    def __init__(self,
                  ao1_dds=DDS, pid1_dac=DAC_CH, 
                  ao2_dds=DDS, pid2_dac=DAC_CH,
                  sw_ttl=TTL,
                  awg_trg_ttl=TTL,
                  pid1_int_hold_zero_ttl=TTL,
                  pid2_enable_ttl=TTL,
                  painting_dac=DAC_CH,
                  expt_params=ExptParams(),
                  core=Core):
        """Controls the tweezers.
        """        

        super().__init__(awg_ip=AWG_IP,
                         awg_trg_ttl=awg_trg_ttl,
                         tweezer_xmesh=KEXP_TWEEZER_XMESH,
                         expt_params=expt_params,
                         core=core)

        self.ao1_dds = ao1_dds
        self.pid1_dac = pid1_dac
        self.ao2_dds = ao2_dds
        self.pid2_dac = pid2_dac
        self.sw_ttl = sw_ttl
        self.pid1_int_hold_zero = pid1_int_hold_zero_ttl
        self.pid2_enable_ttl = pid2_enable_ttl
        self.paint_amp_dac = painting_dac

    @kernel
    def on(self,paint=False,v_awg_am=dv):
        """Turns on the tweezer (awg rf sw on, pid1 and pid2 dds on, pid2
        feedback set to disabled, and pid1 feedback engaged at 0 V) at the
        given painting amplitude.

        Args:
            paint (bool, optional): Whether or not to paint the tweezers.
            Defaults to False.
            v_awg_am (float, optional): If painting is enabled, sets the
            painting amplitude. Full scale is +6V, off is -6V. We use -7V for
            fully off, since there is a small voltage divider in the system.
        """        
        if v_awg_am == dv:
            v_awg_am = self.params.v_hf_tweezer_paint_amp_max

        self.pid1_dac.set(v=.0)
        delay(300.e-6)
        self.ao2_dds.on()

        if paint:
            self.paint_amp_dac.set(v=v_awg_am)
        else:
            self.paint_amp_dac.set(v=-7.)
        with parallel:
            self.ao1_dds.on()
            self.sw_ttl.on()
            self.pid1_int_hold_zero.pulse(1.e-6)

    @kernel
    def off(self):
        """Turns the tweezer off, disables both PIDs, and zeros the integrator
        for PID1.
        """        
        self.ao1_dds.off()
        self.ao2_dds.off()
        self.pid1_int_hold_zero.on()
        self.pid1_dac.set(v=0.)
        self.pid2_enable_ttl.off()
        self.sw_ttl.off()

    @kernel
    def set_power(self,v_pd=dv,load_dac=True):
        if v_pd == dv:
            v_pd = self.params.v_pd_tweezer_1064
        self.pid1_dac.set(v=v_pd,load_dac=load_dac)

    @kernel(flags={"fast-math"})
    def ramp(self,t,
             v_start=dv,
             v_end=dv,
             n_steps=di,
             paint=False,
             v_awg_am_max=dv,
             v_pd_max=dv,
             keep_trap_frequency_constant=True,
             low_power=False):
        """Ramps the voltage that controls the tweezer power according to v_ramp_list.
        
        If painting is enabled, paints the tweezer by controlling the amplitude
        of the FM source waveform, which in turn controls the FM modulation
        depth.

        Args:
            t (float): The ramp time.

            v_ramp_list (nd.nparray(float), optional): The list of voltages to
            be ramped. This should be the voltage that controls the tweezer
            power. Defaults to ExptParams.v_pd_tweezer_1064_ramp_list.

            v_awg_am_max (float, optional): The voltage that corresponds to the
            maximum desired painting amplitude. Defaults to
            ExptParams.v_tweezer_paint_amp_max.

            v_pd_max (float, optional): The voltage corresponding to the maximum
            tweezer power used during the ramp. The trap frequency at this power
            and at maximum painting amplitude is the one which is kept constant
            if keep_trap_frequency_constant == True. Defaults to
            ExptParams.v_pd_tweezer_1064_ramp_end (the endpoint of the ramp up).

            paint (bool, optional): If True, enables painting. If False, sets
            the paint amplitude control voltage to -7., which should disable
            painting entirely. Defaults to False.

            keep_trap_frequency_constant (bool, optional): If True, the painting
            amplitude will be adjusted along with the tweezer power in order to
            keep the trap frequency constant, and equal to the trap frequency at
            maximum power (v_pd_max) and maximum painting amplitude
            (v_awg_am_max). Defaults to True.
        """        

        if v_start == dv:
            v_start = 0.
        if v_end == dv:
            v_end = self.params.v_pd_hf_tweezer_1064_ramp_end
        if n_steps == di:
            n_steps = self.params.n_tweezer_ramp_steps
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_hf_tweezer_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_hf_tweezer_1064_ramp_end

        dt_ramp = t / n_steps
        delta_v = (v_end - v_start)/(n_steps - 1)

        if low_power:
            pid_dac = self.pid2_dac
            v_pd_max = tweezer_vpd1_to_vpd2(v_pd_max)
        else:
            pid_dac = self.pid1_dac

        if not paint:
            self.painting_off()

        pid_dac.set(v=v_start)
        if low_power:
            self.pid2_enable_ttl.on()
        else:
            self.pid2_enable_ttl.off()
        for i in range(n_steps):
            v = v_start + i * delta_v
            if paint:
                if keep_trap_frequency_constant:
                    v_awg_amp_mod = self.v_pd_to_painting_amp_voltage(v,
                                                                      v_pd_max,
                                                                      v_awg_am_max)
                else:
                    v_awg_amp_mod = v_awg_am_max
                self.paint_amp_dac.set(v_awg_amp_mod,load_dac=True)
            pid_dac.set(v=v,load_dac=True)
            delay(dt_ramp)

    @portable
    def v_pd_to_painting_amp_voltage(self,v_pd=dv,
                                        v_pd_max=dv,
                                        v_awg_am_max=dv) -> TFloat:
        """For a given v_pd, computes the fraction of tweezer power used if the
        maximum power is v_pd_max, then uses that to figure out what fraction
        of the maximum painting amplitude (of v_awg_am_max) to use in order
        to keep the trap freuqency the same as with v_pd_max and
        v_awg_am_max.

        Args:
            v_pd (_type_, optional): _description_. Defaults to dv.
            v_pd_max (_type_, optional): Tweezer power used to determine the
            intial trap frequency (to be held constant). Defaults to
            ExptParams.v_pd_tweezer_1064_ramp_end.
            v_awg_am_max (_type_, optional): Painting amplitude used to
            determine the initial trap frequency (to be held constant). Defaults
            to ExptParams.v_tweezer_paint_amp_max.

        Returns:
            TFloat: the paint amplitude voltage that gives the same trap
            frequency with v_pd as with (v_pd_max,v_awg_am_max).
        """        
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_hf_tweezer_paint_amp_max

        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_hf_tweezer_1064_ramp_end

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