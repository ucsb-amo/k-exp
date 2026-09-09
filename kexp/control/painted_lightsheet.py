from waxx.control.artiq.DAC_CH import DAC_CH
from waxx.control.artiq.DDS import DDS
from waxx.control.artiq.TTL import TTL_OUT
from waxx.control.painted_beam import PaintedBeam, DAC_PRIMARY

from kexp.config.expt_params import ExptParams

from artiq.coredevice.core import Core
from artiq.experiment import kernel, TFloat
from artiq.language.core import delay_mu

dv = -102.
di = 0

# painting-amplitude control voltage for zero painting. Set per beam because
# the RF chain in front of each FM source has its own attenuation.
V_LIGHTSHEET_PAINT_MIN = -5.95

class lightsheet(PaintedBeam):
    def __init__(self, pid_dac = DAC_CH, paint_amp_dac = DAC_CH,
                 alignment_shim_dac = DAC_CH,
                 sw_ttl = TTL_OUT, pid_int_hold_zero_ttl = TTL_OUT,
                 v_paint_min = V_LIGHTSHEET_PAINT_MIN,
                 expt_params = ExptParams,
                 core = Core):
        """Controls the light sheet beam.

        Args:
            pid_dac (DAC_CH): A DAC channel that controls a VVA to attenuate the
            overall RF that reaches the amp (and thus the AO.)
            paint_amp_dac (DAC_CH): DAC_CH, voltage controls the painting amplitude via
            controlling the modulation depth. v_paint_min is minimal painting,
            +6 V is maximal painting.
            sw_ttl (TTL): TTL channel, controls an RF
            switch between AWG and amplifier.
            v_paint_min (float): painting control voltage corresponding to zero
            painting, for this beam's RF chain.
        """
        self.pid_dac = pid_dac
        self.ttl_sw = sw_ttl
        self.pid_int_zero_ttl = pid_int_hold_zero_ttl # integrator hold, not zero
        self.alignment_shim_dac = alignment_shim_dac
        self.params = expt_params

        self._init_painting(paint_amp_dac=paint_amp_dac,
                            v_paint_min=v_paint_min,
                            core=core)

    @kernel
    def init(self):
        self.painting_off()
        self.ttl_sw.off()

    @kernel
    def set_power(self,v_lightsheet_vva=dv,load_dac=True):
        if v_lightsheet_vva == dv:
            v_lightsheet_vva = self.params.v_pd_lightsheet
        self.pid_dac.set(v=v_lightsheet_vva,load_dac=load_dac)

    # -------------------------------------------------------------------------
    # PaintedBeam hooks
    # -------------------------------------------------------------------------

    @kernel
    def _ramp_begin(self,v_start,paint,dac_select,dt_mu):
        self.pid_dac.set(v=v_start,load_dac=True)
        self.on(paint=paint)
        delay_mu(dt_mu)

    @kernel
    def _set_pd(self,v,dac_select):
        self.pid_dac.set(v=v,load_dac=False)

    @kernel
    def _load_pd(self,dac_select):
        self.pid_dac.load()

    @kernel
    def _ramp_end(self,v_end,dac_select):
        self.pid_dac.v = v_end

    # -------------------------------------------------------------------------
    # ramps -- these resolve the lightsheet's ExptParams defaults and hand off
    # to the shared co-ramp cores in PaintedBeam
    # -------------------------------------------------------------------------

    @kernel(flags={"fast-math"})
    def ramp(self,t,
             v_start=dv,
             v_end=dv,
             n_steps=di,
             paint=False,
             v_awg_am_max=dv,
             v_pd_max=dv,
             keep_trap_frequency_constant=True):
        """Ramps the lightsheet power linearly, co-ramping the painting
        amplitude if paint is True.

        Args:
            t (float): the ramp time.
            v_start (float, optional): PID setpoint to start from. Defaults to
            wherever the PID DAC currently sits.
            v_end (float, optional): PID setpoint to end on. Defaults to
            ExptParams.v_pd_lightsheet_rampup_end.
            n_steps (int, optional): number of ramp steps. Defaults to
            ExptParams.n_lightsheet_ramp_steps.
            paint (bool, optional): if True, paints. If False, sets the painting
            control voltage to zero-painting for the whole ramp. Defaults to
            False.
            v_awg_am_max (float, optional): the voltage corresponding to the
            maximum desired painting amplitude. Defaults to
            ExptParams.v_lightsheet_paint_amp_max.
            v_pd_max (float, optional): the power at which the trap frequency to
            be held constant is defined. Defaults to
            ExptParams.v_pd_lightsheet_rampup_end.
            keep_trap_frequency_constant (bool, optional): if True, the painting
            amplitude tracks the power so the trap frequency stays equal to its
            value at (v_pd_max, v_awg_am_max). If False, the painting amplitude
            is held at v_awg_am_max. Defaults to True.
        """
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

        self._ramp_linear(t,v_start,v_end,n_steps,paint,
                          v_awg_am_max,v_pd_max,keep_trap_frequency_constant,
                          DAC_PRIMARY)

    @kernel(flags={"fast-math"})
    def cubic_ramp(self,t,
                   v_start=dv,
                   v_end=dv,
                   n_steps=di,
                   paint=False,
                   v_awg_am_max=dv,
                   v_pd_max=dv,
                   keep_trap_frequency_constant=True):
        """Smoothstep (zero slope at both ends) power ramp. Arguments as for
        ramp()."""
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

        self._ramp_cubic(t,v_start,v_end,n_steps,paint,
                         v_awg_am_max,v_pd_max,keep_trap_frequency_constant,
                         DAC_PRIMARY)

    @kernel(flags={"fast-math"})
    def adiabatic_ramp(self,t,
                v_start=dv,
                v_end=dv,
                n_steps=di,
                paint=False,
                v_awg_am_max=dv,
                v_pd_max=dv,
                keep_trap_frequency_constant=True,
                v_offset=0.02):
        """Constant-adiabaticity power ramp. Arguments as for ramp(), plus:

        Args:
            v_offset (float, optional): PID setpoint at zero optical power;
            power is taken proportional to (v - v_offset). Defaults to 0.02.
        """
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

        self._ramp_adiabatic(t,v_start,v_end,n_steps,v_offset,paint,
                             v_awg_am_max,v_pd_max,keep_trap_frequency_constant,
                             DAC_PRIMARY)

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
        """Exponential power ramp. Arguments as for ramp(), plus:

        Args:
            tau (float, optional): time constant (s). Defaults to t/3, which is
            the slow-start / fast-finish curvature; negative tau flips it.
        """
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
            tau = t / 3.

        self._ramp_exponential(t,v_start,v_end,n_steps,tau,paint,
                               v_awg_am_max,v_pd_max,
                               keep_trap_frequency_constant,
                               DAC_PRIMARY)

    @kernel
    def v_pd_to_painting_amp_voltage(self,v_pd=dv,
                                        v_pd_max=dv,
                                        v_awg_am_max=dv) -> TFloat:
        """The painting amplitude voltage that gives the same trap frequency
        with v_pd as with (v_pd_max, v_awg_am_max). See
        PaintedBeam._paint_amp_v."""
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_lightsheet_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_lightsheet_rampup_end
        return self._paint_amp_v(v_pd,v_pd_max,v_awg_am_max)

    @kernel
    def zero_pid(self):
        self.pid_int_zero_ttl.pulse(10.e-9)

    @kernel
    def on(self, paint=False, v_awg_am=dv):
        if v_awg_am == dv:
            v_awg_am = self.params.v_lightsheet_paint_amp_max
        if paint:
            self.paint_amp_dac.set(v=v_awg_am)
        else:
            self.painting_off()
        self.ttl_sw.on()

    @kernel
    def off(self):
        self.ttl_sw.off()
        self.pid_dac.set(v=self.params.v_pd_lightsheet_pd_minimum)
        self.zero_pid()
