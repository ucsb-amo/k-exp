from waxx.control.artiq.DAC_CH import DAC_CH
from waxx.control.artiq.TTL import TTL_OUT
from waxx.control.artiq.DDS import DDS
from waxx.control.painted_beam import PaintedBeam, DAC_PRIMARY, DAC_SECONDARY
import waxx.control.tweezer.spectrum_DDS_tweezer as wax_tweezer

from artiq.language.core import now_mu
from artiq.coredevice.core import Core
from artiq.experiment import rpc, kernel, delay, parallel, TFloat, portable, TArray, TInt32

from kexp.config.expt_params import ExptParams
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.util.artiq.async_print import aprint

import numpy as np

# di = 666420695318008 #causes failure #lmao
di = 0
dv = -1000.

# painting-amplitude control voltage for zero painting. Set per beam because
# the RF chain in front of each FM source has its own attenuation.
V_TWEEZER_PAINT_MIN = -4.985

AWG_IP = 'TCPIP::192.168.1.83::inst0::INSTR'
from kexp.calibrations.tweezer import tweezer_xmesh as KEXP_TWEEZER_XMESH

class TweezerTrap(wax_tweezer.TweezerTrap):
    def __init__(self,
                 position=dv,
                 amplitude=dv,
                 cateye:bool=False,
                 frequency=dv,
                 awg_trigger_ttl=TTL_OUT,
                 tweezer_xmesh=KEXP_TWEEZER_XMESH,
                 expt_params=ExptParams(),
                 core=Core):
        
        super().__init__(position=position,
                         amplitude=amplitude,
                         cateye=cateye,
                         frequency=frequency,
                         tweezer_xmesh=tweezer_xmesh,
                         awg_trigger_ttl=awg_trigger_ttl,
                         expt_params=expt_params,
                         core=core)
    
class tweezer(wax_tweezer.TweezerController, PaintedBeam):
    """
    Machine-specific implementation of the spectrum AWG-controlled tweezers.
    This class should be used for things which interface with an aritisinal
    implementation of the device. For move-related code that is general to the
    AWG-controlled tweezer, edit the wax class. For the power/painting co-ramps,
    which are shared with the painted lightsheet, edit PaintedBeam.
    """    

    def __init__(self,
                  ao1_dds=DDS, pid1_dac=DAC_CH, 
                  ao2_dds=DDS, pid2_dac=DAC_CH,
                  sw_ttl=TTL_OUT,
                  awg_trg_ttl=TTL_OUT,
                  pid1_int_hold_zero_ttl=TTL_OUT,
                  pid2_enable_ttl=TTL_OUT,
                  painting_dac=DAC_CH,
                  v_paint_min=V_TWEEZER_PAINT_MIN,
                  expt_params=ExptParams(),
                  core=Core):
        """Controls the tweezers.
        """        

        super().__init__(awg_ip=AWG_IP,
                         awg_trg_ttl=awg_trg_ttl,
                         tweezer_xmesh=KEXP_TWEEZER_XMESH,
                         expt_params=expt_params,
                         core=core)
        
        self.params = expt_params # assigned in super init, but just for vscode

        self.ao1_dds = ao1_dds
        self.pid1_dac = pid1_dac
        self.ao2_dds = ao2_dds
        self.pid2_dac = pid2_dac
        self.sw_ttl = sw_ttl
        self.pid1_int_hold_zero = pid1_int_hold_zero_ttl
        self.pid2_enable_ttl = pid2_enable_ttl

        self._init_painting(paint_amp_dac=painting_dac,
                            v_paint_min=v_paint_min,
                            core=core)

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
            self.painting_off()
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


    # -------------------------------------------------------------------------
    # PaintedBeam hooks
    # -------------------------------------------------------------------------
    #
    # dac_select picks which power servo the ramp drives: DAC_PRIMARY is pid1,
    # DAC_SECONDARY is the low-power pid2 (which also has to be enabled).

    @kernel
    def _ramp_begin(self,v_start,paint,dac_select,dt_mu):
        if dac_select == DAC_SECONDARY:
            self.pid2_dac.set(v=v_start)
            self.pid2_enable_ttl.on()
        else:
            self.pid1_dac.set(v=v_start)
            self.pid2_enable_ttl.off()

    @kernel
    def _set_pd(self,v,dac_select):
        if dac_select == DAC_SECONDARY:
            self.pid2_dac.set(v=v,load_dac=False)
        else:
            self.pid1_dac.set(v=v,load_dac=False)

    @kernel
    def _load_pd(self,dac_select):
        if dac_select == DAC_SECONDARY:
            self.pid2_dac.load()
        else:
            self.pid1_dac.load()

    @kernel
    def _ramp_end(self,v_end,dac_select):
        if dac_select == DAC_SECONDARY:
            self.pid2_dac.v = v_end
        else:
            self.pid1_dac.v = v_end

    # -------------------------------------------------------------------------
    # ramps -- these resolve the tweezer's ExptParams defaults and hand off to
    # the shared co-ramp cores in PaintedBeam
    # -------------------------------------------------------------------------

    @kernel(flags={"fast-math"})
    def ramp(self,t,
             v_start=dv,
             v_end=dv,
             n_steps=di,
             paint=False,
             v_awg_am_max=dv,
             v_pd_max=dv,
             keep_trap_frequency_constant=True,
             low_power=False,
             cubic_ramp=False):
        """Ramps the voltage that controls the tweezer power, linearly by
        default or on a smoothstep if cubic_ramp is True.

        If painting is enabled, paints the tweezer by controlling the amplitude
        of the FM source waveform, which in turn controls the FM modulation
        depth.

        Args:
            t (float): The ramp time.

            v_start (float, optional): PID setpoint to start from. Defaults to
            wherever the pid1 DAC currently sits.

            v_end (float, optional): PID setpoint to end on. Defaults to
            ExptParams.v_pd_hf_tweezer_1064_ramp_end.

            n_steps (int, optional): Number of ramp steps. Defaults to
            ExptParams.n_tweezer_ramp_steps.

            v_awg_am_max (float, optional): The voltage that corresponds to the
            maximum desired painting amplitude. Defaults to
            ExptParams.v_hf_tweezer_paint_amp_max.

            v_pd_max (float, optional): The voltage corresponding to the maximum
            tweezer power used during the ramp. The trap frequency at this power
            and at maximum painting amplitude is the one which is kept constant
            if keep_trap_frequency_constant == True. Defaults to
            ExptParams.v_pd_hf_tweezer_1064_ramp_end (the endpoint of the ramp
            up).

            paint (bool, optional): If True, enables painting. If False, sets
            the paint amplitude control voltage to zero painting for the whole
            ramp. Defaults to False.

            keep_trap_frequency_constant (bool, optional): If True, the painting
            amplitude will be adjusted along with the tweezer power in order to
            keep the trap frequency constant, and equal to the trap frequency at
            maximum power (v_pd_max) and maximum painting amplitude
            (v_awg_am_max). Defaults to True.

            low_power (bool, optional): If True, ramps the low-power pid2 servo
            instead of pid1, and rescales v_pd_max into pid2 units. Defaults to
            False.

            cubic_ramp (bool, optional): If True, uses a smoothstep instead of a
            linear ramp. Defaults to False.
        """

        if v_start == dv:
            v_start = self.pid1_dac.v
        if v_end == dv:
            v_end = self.params.v_pd_hf_tweezer_1064_ramp_end
        if n_steps == di:
            n_steps = self.params.n_tweezer_ramp_steps
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_hf_tweezer_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_hf_tweezer_1064_ramp_end

        if low_power:
            dac_select = DAC_SECONDARY
            v_pd_max = tweezer_vpd1_to_vpd2(v_pd_max)
        else:
            dac_select = DAC_PRIMARY

        if cubic_ramp:
            self._ramp_cubic(t,v_start,v_end,n_steps,paint,
                             v_awg_am_max,v_pd_max,
                             keep_trap_frequency_constant,dac_select)
        else:
            self._ramp_linear(t,v_start,v_end,n_steps,paint,
                              v_awg_am_max,v_pd_max,
                              keep_trap_frequency_constant,dac_select)

    @kernel(flags={"fast-math"})
    def adiabatic_ramp(self,t,
                v_start=dv,
                v_end=dv,
                n_steps=di,
                paint=False,
                v_awg_am_max=dv,
                v_pd_max=dv,
                keep_trap_frequency_constant=True,
                low_power=False,
                v_offset=0.02):
        """Constant-adiabaticity power ramp. Arguments as for ramp(), plus:

        Args:
            v_offset (float, optional): PID setpoint at zero optical power;
            power is taken proportional to (v - v_offset). Defaults to 0.02.
        """
        if v_start == dv:
            v_start = self.pid1_dac.v
        if v_end == dv:
            v_end = self.params.v_pd_hf_tweezer_1064_ramp_end
        if n_steps == di:
            n_steps = self.params.n_tweezer_ramp_steps
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_hf_tweezer_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_hf_tweezer_1064_ramp_end

        if low_power:
            dac_select = DAC_SECONDARY
            v_pd_max = tweezer_vpd1_to_vpd2(v_pd_max)
        else:
            dac_select = DAC_PRIMARY

        self._ramp_adiabatic(t,v_start,v_end,n_steps,v_offset,paint,
                             v_awg_am_max,v_pd_max,
                             keep_trap_frequency_constant,dac_select)

    @kernel(flags={"fast-math"})
    def exponential_ramp(self,t,
                v_start=dv,
                v_end=dv,
                tau=dv,
                n_steps=di,
                paint=False,
                v_awg_am_max=dv,
                v_pd_max=dv,
                keep_trap_frequency_constant=True,
                low_power=False):
        """Exponential power ramp. Arguments as for ramp(), plus:

        Args:
            tau (float, optional): time constant (s). Defaults to t/3, which is
            the slow-start / fast-finish curvature; negative tau flips it.
        """
        if v_start == dv:
            v_start = self.pid1_dac.v
        if v_end == dv:
            v_end = self.params.v_pd_hf_tweezer_1064_ramp_end
        if n_steps == di:
            n_steps = self.params.n_tweezer_ramp_steps
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_hf_tweezer_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_hf_tweezer_1064_ramp_end
        if tau == dv:
            tau = t / 3.

        if low_power:
            dac_select = DAC_SECONDARY
            v_pd_max = tweezer_vpd1_to_vpd2(v_pd_max)
        else:
            dac_select = DAC_PRIMARY

        self._ramp_exponential(t,v_start,v_end,n_steps,tau,paint,
                               v_awg_am_max,v_pd_max,
                               keep_trap_frequency_constant,dac_select)

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
            v_pd (float, optional): Tweezer power to compute the painting
            amplitude for.
            v_pd_max (float, optional): Tweezer power used to determine the
            intial trap frequency (to be held constant). Defaults to
            ExptParams.v_pd_hf_tweezer_1064_ramp_end.
            v_awg_am_max (float, optional): Painting amplitude used to
            determine the initial trap frequency (to be held constant). Defaults
            to ExptParams.v_hf_tweezer_paint_amp_max.

        Returns:
            TFloat: the paint amplitude voltage that gives the same trap
            frequency with v_pd as with (v_pd_max,v_awg_am_max).
        """
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_hf_tweezer_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_hf_tweezer_1064_ramp_end
        return self._paint_amp_v(v_pd,v_pd_max,v_awg_am_max)
