"""K-machine composite devices for the Device Control GUI's Composite tab.

Each entry is a :class:`waxx.util.device_state.composite.CompositeDevice`: the
fields an operator sets, the ops the monitor experiment runs on ``expt`` (the
monitor's ``Base`` instance), and the lamps and readbacks the GUI computes
from the device-state JSON.  Read that module's docstring before adding a
device; the short version:

* op code is ARTIQ kernel code, compiled into the monitor by
  ``kernel_from_string`` -- only ``expt``, the ``{field}`` placeholders and
  the ARTIQ builtins are in scope, so constants are formatted in as literals;
* hard limits (``minimum``/``maximum``) are refused by the GUI *and* re-checked
  by the monitor; soft limits and ``check`` findings are confirmed in the GUI;
* readbacks read the channel states, so a card shows the hardware whoever set
  it (this tab, the DDS/DAC/TTL tabs, or the last experiment).

Changing an op's code changes its signature: a GUI and a monitor built from
different versions refuse that op until the monitor is restarted.

Nothing here runs at import except building the definitions; the GUI-side
helpers (readbacks, checks) build host copies of the lab's classes lazily
from the frames the GUI passes in.

Not here, on purpose: the Precilaser (lightsheet) and ALS (tweezer) lasers --
too dangerous to drive from a card -- and the Rydberg siglents.  The cards
only switch and servo the AOs downstream of them.

Hardware notes that shaped the ops (2026-09-26):

* Coils "Off" ramps the supply down over ``t_ramp`` and then does what
  ``igbt_magnet.off()`` does after its ramps (IGBT open, PID off, discharge).
  It deliberately does *not* call ``off()`` after the ramp: ``off()`` first
  ramps the supply to ``i_pid``, which after a manual ramp to zero would
  drive the coil back up to the last PID setpoint.  Every coil op first
  re-derives the coil's cached currents from its DAC channels, so an edit
  made on the DAC tab is where a ramp starts from.
* When the device state is untrusted (a run ended without reporting its end
  state), coil ramps start from the Keysight's measured current (``i_meas``)
  instead of the state file, and are refused if there is no fresh reading.
* ``TTL_OUT.pulse`` does not update the channel's cached level; every op that
  pulses a TTL sets it low explicitly afterwards, so what the monitor writes
  back to the state file is what the line is at.
* The imaging PID's clear/override TTLs (ttl 86/87) are not offered: per
  ``kexp.config.ttl_id`` they "no longer do anything" since the NewFocus PID
  was removed.
* The tweezer AWG is a host-side device (spcm).  Its ops run a host step in
  the monitor process, which then holds the card: an experiment submitted
  while the monitor holds it gets it back when the monitor exits (the
  experiment's ``awg_init`` retries "in use" for ~6 s).  Disconnect first
  to be safe.

Judgement calls (no measurement behind them; change freely):
``I_OUTER_WARN``/``I_INNER_WARN``, ``RAMAN_AO_WINDOW``, ``I_MOT_MAX``/``I_MOT_WARN``,
``V_SHIM_WARN``, the D1 detuning window, ``COIL_MAX_ON_S`` and the measured-current
tolerances.  See each constant.
"""

from __future__ import annotations

import contextlib
import io
import math
from dataclasses import replace

from waxx.util.device_state.composite import (
    Arg, Buttons, ChannelToggle, Check, CompositeDevice, FieldRow, Hold, Info, KIND_CHOICE,
    Lamp, Measured, Menu, Op, Readout, Scene, Status, Step, Table, TableRow,
)
from waxx.control.beat_lock import FREQUENCY_GS_HFS

from kexp.calibrations.magnets import (
    offset_i_transducer_per_v_setpoint_pid_outer,
    offset_i_transducer_per_v_setpoint_supply_outer,
    offset_overhead_per_i_transducer,
    slope_i_per_v_setpoint_supply_inner,
    slope_i_transducer_per_v_setpoint_pid_outer,
    slope_i_transducer_per_v_setpoint_supply_outer,
    slope_overhead_per_i_transducer,
)
from kexp.calibrations.tweezer import (
    F_CE_MAX, F_CE_MIN, F_NCE_MAX, F_NCE_MIN, tweezer_vpd2_to_vpd1, tweezer_xmesh,
)
from kexp.control.painted_lightsheet import V_LIGHTSHEET_PAINT_MIN
from kexp.control.awg_tweezer import V_TWEEZER_PAINT_MIN

# --- shared numbers ---------------------------------------------------------------

#: Shutter settle times, taken from the sequences that open these shutters:
#: Control.prep_raman (raman shutter -> 3 ms), Base.reset_devices
#: (set_imaging_shutters -> 10 ms), RydbergDDSSwitchBeam.reboot (405 -> 3 ms).
T_RAMAN_SHUTTER = 3.e-3
T_IMAGING_SHUTTER = 10.e-3
T_RY_405_SHUTTER = 3.e-3

#: DAC channels refuse (write 0 V instead) above their max_v: 9.99 V unless
#: dac_id says otherwise.  Setpoint fields stop just below.
V_DAC_MAX = 9.99
#: Painting-amplitude DACs: +6 V is full painting (painted_lightsheet).
V_PAINT_MAX = 6.0

#: igbt_magnet.set_voltage maps v_supply / max_voltage (80 V) onto 10 V of
#: DAC, and 80 V would be 10 V -- above the DAC's 9.99 V.
V_COIL_SUPPLY_MAX = 79.

# Coil current limits.  Hard: the supply-current DAC's max_v converted with
# the same calibration the coil uses (outer_coil_supply_current max_v = 7 V
# -> 356 A; inner 9.99 V -> 170 A), rounded down -- above that DAC_CH.set
# writes 0 V, i.e. the ramp would snap to zero mid-way.  Soft (JUDGEMENT): a
# little above the largest current the standard sequences use (outer: i_hf_*
# evap currents ~194 A; inner: i_magtrap_init 106.5 A).
I_OUTER_MAX = 350.
I_OUTER_WARN = 200.
I_INNER_MAX = 165.
I_INNER_WARN = 110.
#: Supply-current DAC max_v per coil (kexp.config.dac_id), for the PID
#: overhead check when the GUI has no frames to read it from.
V_OUTER_SUPPLY_DAC_MAX = 7.
V_INNER_SUPPLY_DAC_MAX = 9.99

#: A coil is "on" (hazard strip, pre-run warning) above this current.
I_COIL_ON = 1.
#: JUDGEMENT: GUIs warn after a coil has been on this long, and an armed
#: watchdog then ramps it down.
COIL_MAX_ON_S = 30 * 60.
#: JUDGEMENT: Keysight-measured vs commanded current before the measured chip
#: turns orange (calibration offset + supply-vs-transducer mismatch).
I_OUTER_MEASURED_TOL = 5.
I_INNER_MEASURED_TOL = 2.
#: A measured current is used only if it is younger than this.
T_MEASURED_FRESH_S = 5.

#: Raman AO window for the transition-frequency warning: |deviation of the
#: 150 MHz AO from its centre|.  JUDGEMENT, NOT a measured AOM bandwidth -- the
#: span of transitions actually used with this pair (119-147 MHz, AO deviation
#: up to 6.7 MHz) plus margin.  Replace with the AOM's specified bandwidth.
RAMAN_AO_WINDOW = 10.e6

#: MOT coil current (inner coil).  Hard limit below 100 A on purpose: Cooling's
#: "use the default" sentinel is dv = 100., so exactly 100 would silently
#: become i_mot.  JUDGEMENT: warn above twice i_mot.
I_MOT_MAX = 70.
I_MOT_WARN = 40.

#: JUDGEMENT: shim control voltages above this ask first (the standard MOT/GM/OP
#: values are <= 2.9 V; some experiments go to 9 V briefly, the monitor would
#: hold it indefinitely).
V_SHIM_WARN = 3.5

#: JUDGEMENT: D1 gray-molasses detunings (Γ) outside this window ask first; the
#: hard limit is a typo guard.
DETUNE_D1_WARN = (0., 15.)
DETUNE_D1_MAX = 30.


def _float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _checks(*fns):
    """One op check running several."""
    def run(args, ctx):
        found = []
        for fn in fns:
            result = fn(args, ctx)
            if result is None:
                continue
            found.extend([result] if isinstance(result, Check) else list(result))
        return found
    return run


def _frame_attr(ctx, frame, name, attr, default=None):
    obj = getattr(getattr(getattr(ctx, "frames", None), frame, None), name, None)
    value = getattr(obj, attr, None)
    return default if value is None else value


# --- lazily built host copies of the lab's classes (GUI side only) -----------------

def _host_object(ctx, attr, build):
    """Build (once per frames object) a host copy of a lab class for its
    conversions, so the GUI's numbers come from the same code the kernel
    runs.  None when the GUI has no frames."""
    frames = getattr(ctx, "frames", None)
    dds = getattr(frames, "dds", None)
    if dds is None:
        return None
    cache = getattr(frames, "_composite_cache", None)
    if cache is None:
        cache = {}
        try:
            frames._composite_cache = cache
        except Exception:
            pass
    if attr not in cache:
        try:
            # The classes print a harmless note about the missing core device.
            with contextlib.redirect_stdout(io.StringIO()):
                cache[attr] = build(dds, ctx.params)
        except Exception:
            cache[attr] = None
    return cache[attr]


def _raman_pair(ctx):
    def build(dds, params):
        from waxx.control.raman_beams import RamanBeamPair
        return RamanBeamPair(dds0=dds.raman_150_plus, dds1=dds.raman_80_plus,
                             dds_sw=dds.raman_switch)
    return _host_object(ctx, "raman", build)


def raman_ao_frequencies(ctx, f_transition):
    """(f_150+, f_80+) for a transition, from RamanBeamPair's own split."""
    pair = _raman_pair(ctx)
    if pair is None or f_transition is None:
        return None
    f0, f1 = pair.ao_frequencies(float(f_transition))
    return float(f0), float(f1)


def raman_transition_from_ao(ctx, f0):
    """Inverse of the split for the 150+ AO frequency.  The split is affine
    in the transition frequency, so two evaluations of the real code pin it."""
    pair = _raman_pair(ctx)
    if pair is None or f0 is None:
        return None
    a, _ = pair.ao_frequencies(100.e6)
    b, _ = pair.ao_frequencies(200.e6)
    if b == a:
        return None
    return 100.e6 + (float(f0) - a) * (100.e6 / (b - a))


def imaging_beat(ctx, f_detuning):
    """(reference, offset) of the beat lock for an imaging detuning, from the
    AO frequencies in the state file -- the formula of
    BeatLockImaging.imaging_detuning_to_beat_ref (tested against it)."""
    p = ctx.params
    ao = _imaging_ao_shift(ctx)
    if p is None or ao is None or f_detuning is None:
        return None
    sign = float(p.beatlock_sign)
    n = float(p.N_offset_lock_reference_multiplier)
    f_offset = (float(f_detuning) - ao - FREQUENCY_GS_HFS / 2) / sign
    return f_offset / n, f_offset


def _imaging_ao_shift(ctx):
    """(f_switch * order + f_pid * order) * 2, the double-passed AO shift of
    BeatLockImagingPID.get_ao_shift, from the state file."""
    sw, pid = ctx.dds("imaging_x_switch"), ctx.dds("imaging")
    if sw is None or pid is None:
        return None
    try:
        return (float(sw["frequency"]) * float(sw.get("aom_order", 1))
                + float(pid["frequency"]) * float(pid.get("aom_order", 1))) * 2
    except (KeyError, TypeError, ValueError):
        return None


# --- imaging -------------------------------------------------------------------------

AXIS_X, AXIS_XY = 0, 1
IMG_ABS, IMG_FLUOR, IMG_DISP = 0, 2, 1   # waxa img_types values


def _imaging_axis_readback(ctx):
    x, xy = ctx.is_on("ttl", "imaging_shutter_x"), ctx.is_on("ttl", "imaging_shutter_xy")
    if x and not xy:
        return AXIS_X
    if xy and not x:
        return AXIS_XY
    return None


def _imaging_detuning_readback(ctx):
    p = ctx.params
    f_ref, ao = ctx.dds_frequency("beatlock_ref"), _imaging_ao_shift(ctx)
    if p is None or f_ref is None or ao is None:
        return None
    return (float(p.beatlock_sign) * f_ref * float(p.N_offset_lock_reference_multiplier)
            + ao + FREQUENCY_GS_HFS / 2)


def _imaging_detuning_default(ctx):
    p = ctx.params
    if p is None:
        return None
    return p.frequency_detuned_imaging_F1 if float(p.imaging_state) == 1. \
        else p.frequency_detuned_imaging


def _imaging_detuning_check(value, ctx):
    beat = imaging_beat(ctx, value)
    if beat is None:
        return Check.warn("cannot check the beat lock (no AO frequencies or params)")
    f_ref, f_offset = beat
    p = ctx.params
    if f_offset < p.frequency_minimum_offset_beatlock:
        return Check.error(f"beat offset {f_offset / 1e6:.1f} MHz is below the lock's "
                           f"minimum {p.frequency_minimum_offset_beatlock / 1e6:.0f} MHz "
                           f"(set_imaging_detuning refuses it)")
    if f_ref <= 0.:
        return Check.error("needs a negative beat reference frequency (flip the beat lock sign)")
    if f_ref > 400.e6:
        return Check.error(f"beat reference {f_ref / 1e6:.1f} MHz is above the DDS's 400 MHz")
    return None


def _imaging_power_default(ctx):
    from kexp.config.camera_id import cameras
    axis = ctx.field("axis", AXIS_XY)
    img = int(ctx.field("img_type", IMG_ABS))
    camera = cameras.andor if int(axis) == AXIS_X else cameras.xy_basler
    key = {IMG_ABS: "__amp_absorption__", IMG_FLUOR: "__amp_fluorescence__",
           IMG_DISP: "__amp_dispersive__"}.get(img, "__amp_absorption__")
    return getattr(camera, key, None)


def _imaging_info(ctx):
    beat = imaging_beat(ctx, ctx.field("detuning"))
    if beat is None:
        return None
    f_ref, f_offset = beat
    cam = "Andor" if int(ctx.field("axis", AXIS_XY)) == AXIS_X else "xy Basler"
    return (f"beat ref {f_ref / 1e6:.3f} MHz (offset {f_offset / 1e6:.1f} MHz) · "
            f"power default: {cam}, chosen imaging type")


def _imaging_state(ctx):
    sw = ctx.is_on("dds", "imaging_x_switch")
    x, xy = ctx.is_on("ttl", "imaging_shutter_x"), ctx.is_on("ttl", "imaging_shutter_xy")
    if sw is None:
        return Status("unknown", "")
    if sw and (x or xy):
        return Status("on", "ON " + ("x" if x else "xy"),
                      f"switch AO on, {'x' if x else 'xy'} shutter open")
    if sw:
        return Status("partial", "RF only", "switch AO on, both shutters closed")
    return Status("off", "off")


IMAGING_SHUTTERS = """
if {axis} == 0:
    expt.ttl.imaging_shutter_xy.off()
    expt.ttl.imaging_shutter_x.on()
else:
    expt.ttl.imaging_shutter_x.off()
    expt.ttl.imaging_shutter_xy.on()
"""

#: The DDS check set_imaging_detuning does not make (it only prints).
IMAGING_BEAT_CHECK = """
if expt.imaging.imaging_detuning_to_beat_ref({detuning}) > 400.e6:
    raise ValueError("beat reference above the DDS's 400 MHz")
"""

IMAGING = CompositeDevice(
    key="imaging",
    title="Imaging beam",
    group="Probe light",
    doc=("Beat-locked imaging light (BeatLockImagingPID): beatlock_ref sets the "
         "offset lock, 'imaging' is the PID-controlled AO (v_pd on DAC imaging_pid), "
         "imaging_x_switch is the switch AO.  The axis picks which fiber shutter "
         "opens: x (Andor / APD path) or xy (xy Basler)."),
    fields=(
        Arg("axis", "Axis", kind=KIND_CHOICE,
            choices=(("x — Andor / APD", AXIS_X), ("xy — xy Basler", AXIS_XY)),
            readback=_imaging_axis_readback, default=AXIS_XY,
            tooltip="Which imaging shutter opens (the other closes)."),
        Arg("img_type", "Defaults for", kind=KIND_CHOICE,
            choices=(("absorption", IMG_ABS), ("fluorescence", IMG_FLUOR),
                     ("dispersive", IMG_DISP)),
            tooltip="Only picks which camera default ↺ fills into Power "
                    "(not sent to the monitor)."),
        Arg("detuning", "Detuning", unit="MHz", scale=1e-6, decimals=3, step=0.5,
            default=_imaging_detuning_default, readback=_imaging_detuning_readback,
            check=_imaging_detuning_check,
            tooltip="Imaging detuning (set_imaging_detuning); ↺ = ExptParams "
                    "frequency_detuned_imaging (F1 value if imaging_state == 1)."),
        Arg("power", "Power (v_pd)", unit="V", decimals=3, step=0.01,
            minimum=0., maximum=V_DAC_MAX, warn_above=1.0,
            default=_imaging_power_default,
            readback=lambda ctx: ctx.dds_v_pd("imaging"),
            tooltip="PID setpoint of the imaging AO (imaging.set_power). ↺ = the "
                    "selected axis's camera amp_imaging for the chosen imaging type."),
    ),
    ops=(
        Op("on", "On", args=("axis", "detuning", "power"),
           tooltip="Beat ref on, detuning + power set, PID AO on, axis shutter open, "
                   f"{T_IMAGING_SHUTTER * 1e3:g} ms, switch AO on.",
           code=f"""
{IMAGING_BEAT_CHECK}
expt.dds.beatlock_ref.on()
expt.imaging.set_imaging_detuning({{detuning}})
expt.imaging.set_power({{power}})
expt.imaging.dds_pid.on()
{IMAGING_SHUTTERS}
delay({T_IMAGING_SHUTTER!r})
expt.imaging.on()
"""),
        Op("off", "Off", tooltip="Switch AO off, both imaging shutters closed "
                                 "(the PID AO and beat ref stay as they are).",
           code="""
expt.imaging.off()
expt.ttl.imaging_shutter_x.off()
expt.ttl.imaging_shutter_xy.off()
"""),
        Op("set_detuning", "Set", args=("detuning",),
           code=IMAGING_BEAT_CHECK + "\nexpt.imaging.set_imaging_detuning({detuning})",
           tooltip="imaging.set_imaging_detuning"),
        Op("set_power", "Set", args=("power",),
           code="expt.imaging.set_power({power})", tooltip="imaging.set_power"),
        Op("set_axis", "Set", args=("axis",), code=IMAGING_SHUTTERS,
           tooltip="Open this axis's shutter, close the other; RF untouched."),
        Op("rf_on", "Switch AO on (shutters unchanged)", code="expt.imaging.on()"),
        Op("rf_off", "Switch AO off (shutters unchanged)", code="expt.imaging.off()"),
        Op("close_shutters", "Close both shutters", code="""
expt.ttl.imaging_shutter_x.off()
expt.ttl.imaging_shutter_xy.off()
"""),
        Op("pid_ao_off", "PID AO off (full off)",
           code="expt.imaging.off()\nexpt.imaging.dds_pid.off()",
           tooltip="Switch AO and the PID-controlled AO off; the next On turns the "
                   "PID AO back on."),
    ),
    lamps=(
        Lamp("switch", "dds", "imaging_x_switch"),
        Lamp("PID AO", "dds", "imaging"),
        Lamp("beat ref", "dds", "beatlock_ref"),
        Lamp("shutter x", "ttl", "imaging_shutter_x", "open", "closed"),
        Lamp("shutter xy", "ttl", "imaging_shutter_xy", "open", "closed"),
    ),
    state=_imaging_state,
    layout=(
        Buttons(("on", "off"), main=True),
        FieldRow(("axis",), ("set_axis",)),
        FieldRow(("detuning",), ("set_detuning",)),
        FieldRow(("img_type",)),
        FieldRow(("power",), ("set_power",)),
        Info(_imaging_info),
        Menu(("rf_on", "rf_off", "close_shutters", "pid_ao_off")),
    ),
)


# --- raman ---------------------------------------------------------------------------

def _raman_f_readback(ctx):
    return raman_transition_from_ao(ctx, ctx.dds_frequency("raman_150_plus"))


def _raman_p_readback(ctx):
    a = ctx.dds_amplitude("raman_150_plus")
    a0 = _frame_attr(ctx, "dds", "raman_150_plus", "amplitude")
    if a is None or not a0:
        return None
    return (a / a0) ** 2


def _raman_f_check(value, ctx):
    ao = raman_ao_frequencies(ctx, value)
    if ao is None:
        return Check.warn("cannot compute the AO frequencies (no frames)")
    f0, f1 = ao
    found = []
    if not (1.e6 < f0 < 400.e6) or not (1.e6 < f1 < 400.e6):
        found.append(Check.error(f"AO frequencies {f0 / 1e6:.3f} / {f1 / 1e6:.3f} MHz "
                                 f"are outside the DDS range"))
    pair = _raman_pair(ctx)
    dev = f0 - pair._frequency_center_0
    if abs(dev) > RAMAN_AO_WINDOW:
        found.append(Check.warn(
            f"150+ AO at {f0 / 1e6:.3f} MHz is {dev / 1e6:+.2f} MHz from its centre -- outside "
            f"the ±{RAMAN_AO_WINDOW / 1e6:.0f} MHz used so far (RAMAN_AO_WINDOW is not a "
            f"measured bandwidth); diffraction efficiency may be low"))
    return found


def _raman_info(ctx):
    ao = raman_ao_frequencies(ctx, ctx.field("f"))
    if ao is None:
        return None
    return f"AOs for this transition: 150+ {ao[0] / 1e6:.4f} MHz · 80+ {ao[1] / 1e6:.4f} MHz"


def _raman_state(ctx):
    sw = ctx.is_on("dds", "raman_switch")
    sh = ctx.is_on("ttl", "raman_shutter")
    a0, a1 = ctx.is_on("dds", "raman_150_plus"), ctx.is_on("dds", "raman_80_plus")
    opx = ctx.is_on("ttl", "quantum_machines_raman_rf_handoff_ttl")
    if sw is None or sh is None:
        return Status("unknown", "")
    if sw and sh and a0 and a1 and not opx:
        return Status("on", "ON", "both AOs on, shutter open, switch AO on")
    if not sw and not sh:
        return Status("off", "off")
    parts = [f"switch {'on' if sw else 'off'}", f"shutter {'open' if sh else 'closed'}"]
    if not (a0 and a1):
        parts.append("AO(s) off")
    if opx:
        parts.append("AOs on OPX")
    return Status("partial", "partial", ", ".join(parts))


#: The DDS range check the kernel makes before touching either AO.
RAMAN_AO_CHECK = """
f0, f1 = expt.raman.state_splitting_to_ao_frequency({f})
if f0 < 1.e6 or f0 > 400.e6 or f1 < 1.e6 or f1 > 400.e6:
    raise ValueError("Raman AO frequency outside the DDS range")
"""

RAMAN = CompositeDevice(
    key="raman",
    title="Raman beams",
    group="Probe light",
    doc=("expt.raman (RamanBeamPair): raman_150_plus + raman_80_plus set the "
         "two-photon frequency, raman_switch is the switch AO, raman_shutter the "
         "shutter.  quantum_machines_raman_rf_handoff_ttl high means the OPX drives "
         "the two AOs; On takes them back for ARTIQ."),
    fields=(
        Arg("f", "Transition", unit="MHz", scale=1e-6, decimals=4, step=0.001,
            minimum=1.e6, maximum=400.e6,
            default=lambda ctx: ctx.params.frequency_raman_transition,
            readback=_raman_f_readback, check=_raman_f_check,
            param="frequency_raman_transition",
            tooltip="Two-photon transition frequency. ↺ = ExptParams "
                    "frequency_raman_transition."),
        Arg("p", "Power fraction", decimals=3, step=0.01, minimum=0., maximum=1.,
            default=lambda ctx: ctx.params.fraction_power_raman,
            readback=_raman_p_readback, param="fraction_power_raman",
            tooltip="fraction_power: each AO at sqrt(p) x its default amplitude. "
                    "↺ = ExptParams fraction_power_raman."),
    ),
    ops=(
        Op("on", "On", args=("f", "p"),
           tooltip="AOs to ARTIQ, raman.init(f, p) (both AOs set + on), shutter open, "
                   f"{T_RAMAN_SHUTTER * 1e3:g} ms, switch AO on.",
           code=f"""
{RAMAN_AO_CHECK}
expt.ttl.quantum_machines_raman_rf_handoff_ttl.off()
expt.raman.init({{f}}, {{p}})
expt.ttl.raman_shutter.on()
delay({T_RAMAN_SHUTTER!r})
expt.raman.on()
"""),
        Op("off", "Off", tooltip="Switch AO off, shutter closed, both AOs off.",
           code="""
expt.raman.off()
expt.ttl.raman_shutter.off()
expt.raman.dds0.off()
expt.raman.dds1.off()
"""),
        Op("set", "Set", args=("f", "p"),
           tooltip="raman.set(f, p, init=True): both AOs rewritten; their on/off "
                   "state is kept as it was.",
           code=RAMAN_AO_CHECK + """
s0 = expt.raman.dds0.sw_state
s1 = expt.raman.dds1.sw_state
expt.raman.set(frequency_transition={f}, fraction_power_raman={p}, init=True)
if s0 == 0:
    expt.raman.dds0.off()
if s1 == 0:
    expt.raman.dds1.off()
"""),
        Op("switch_on", "Switch AO on (only)", code="expt.raman.on()"),
        Op("switch_off", "Switch AO off (only)", code="expt.raman.off()"),
        Op("shutter_open", "Shutter open (only)", code="expt.ttl.raman_shutter.on()"),
        Op("shutter_close", "Shutter close (only)", code="expt.ttl.raman_shutter.off()"),
    ),
    lamps=(
        Lamp("switch", "dds", "raman_switch"),
        Lamp("shutter", "ttl", "raman_shutter", "open", "closed"),
        Lamp("150+", "dds", "raman_150_plus"),
        Lamp("80+", "dds", "raman_80_plus"),
        Lamp("AOs", "ttl", "quantum_machines_raman_rf_handoff_ttl", "OPX", "ARTIQ", "warn",
             tooltip="quantum_machines_raman_rf_handoff_ttl: high = the OPX drives the AOs"),
    ),
    state=_raman_state,
    layout=(
        Buttons(("on", "off"), main=True),
        FieldRow(("f",), ("set",)),
        FieldRow(("p",), ("set",)),
        Info(_raman_info),
        Menu(("switch_on", "switch_off", "shutter_open", "shutter_close")),
    ),
)


# --- rydberg AOs ---------------------------------------------------------------------

RY_PID_CLEAR_NOTE = ("The intensity-PID clear line (ry_intensity_pid_clear, ttl 56) is "
                     "shared by the 405 and 980 PIDs: clearing one clears both.")


def _ry_405_state(ctx):
    sw, sh = ctx.is_on("dds", "ry_405_sw"), ctx.is_on("ttl", "ry_405_shutter")
    if sw is None or sh is None:
        return Status("unknown", "")
    if sw and sh:
        return Status("on", "ON", "switch AO on, shutter open")
    if sw or sh:
        return Status("partial", "partial",
                      f"switch AO {'on' if sw else 'off'}, shutter {'open' if sh else 'closed'}")
    return Status("off", "off")


RY_405 = CompositeDevice(
    key="ry_405",
    title="Rydberg 405",
    group="Rydberg",
    doc=("expt.ry_405 (RydbergDDSSwitchBeam): ry_405_sw is the double-pass switch AO, "
         "ry_405_shutter the shutter, DAC ry_405_intensity_control the intensity-PID "
         "setpoint.  The laser and its siglent are not driven from here."),
    fields=(
        Arg("v_pd", "PID setpoint", unit="V", decimals=3, step=0.05, minimum=0.,
            maximum=V_DAC_MAX,
            default=lambda ctx: _frame_attr(ctx, "dac", "ry_405_intensity_control", "v"),
            readback=lambda ctx: ctx.dac_voltage("ry_405_intensity_control"),
            tooltip="Intensity-PID setpoint (ry_405.set_power: DAC, then a PID clear "
                    "pulse). ↺ = the dac_id default."),
        Arg("amp", "Switch AO amp", decimals=3, step=0.005, minimum=0., maximum=1.,
            default=lambda ctx: _frame_attr(ctx, "dds", "ry_405_sw", "amplitude"),
            readback=lambda ctx: ctx.dds_amplitude("ry_405_sw"),
            tooltip="Amplitude of the ry_405_sw DDS. ↺ = the dds_id default."),
    ),
    ops=(
        Op("on", "On",
           tooltip=f"Shutter open, {T_RY_405_SHUTTER * 1e3:g} ms, switch AO on.",
           code=f"""
expt.ry_405.ttl_shutter.on()
delay({T_RY_405_SHUTTER!r})
expt.ry_405.on()
"""),
        Op("off", "Off", tooltip="Switch AO off, shutter closed.",
           code="expt.ry_405.off()\nexpt.ry_405.ttl_shutter.off()"),
        Op("set_power", "Set", args=("v_pd",),
           tooltip="ry_405.set_power: setpoint DAC, then a 10 us PID clear pulse "
                   "(clears the 980 PID too).",
           code="expt.ry_405.set_power({v_pd})\nexpt.ry_405.ttl_pid_clear.off()"),
        Op("set_amp", "Set", args=("amp",),
           code="expt.ry_405.dds_sw.set_dds(amplitude={amp})",
           tooltip="ry_405_sw amplitude; its switch state is kept."),
        Op("pid_clear", "Clear PID integrators",
           code="expt.ry_405.ttl_pid_clear.pulse(10.e-6)\nexpt.ry_405.ttl_pid_clear.off()",
           tooltip="10 us pulse on ry_intensity_pid_clear. " + RY_PID_CLEAR_NOTE),
        Op("shutter_open", "Shutter open (only)", code="expt.ry_405.ttl_shutter.on()"),
        Op("shutter_close", "Shutter close (only)", code="expt.ry_405.ttl_shutter.off()"),
        Op("switch_on", "Switch AO on (only)", code="expt.ry_405.on()"),
        Op("switch_off", "Switch AO off (only)", code="expt.ry_405.off()"),
    ),
    lamps=(
        Lamp("switch", "dds", "ry_405_sw"),
        Lamp("shutter", "ttl", "ry_405_shutter", "open", "closed"),
    ),
    state=_ry_405_state,
    layout=(
        Buttons(("on", "off"), main=True),
        FieldRow(("v_pd",), ("set_power",)),
        FieldRow(("amp",), ("set_amp",)),
        Buttons(("pid_clear",)),
        Info(lambda ctx: RY_PID_CLEAR_NOTE),
        Menu(("shutter_open", "shutter_close", "switch_on", "switch_off")),
    ),
)


def _ry_980_state(ctx):
    sw = ctx.is_on("ttl", "ry_980_sw")
    if sw is None:
        return Status("unknown", "")
    return Status("on", "ON", "switch AO on") if sw else Status("off", "off")


RY_980 = CompositeDevice(
    key="ry_980",
    title="Rydberg 980",
    group="Rydberg",
    doc=("expt.ry_980 (RydbergTTLSwitchBeam): ry_980_sw (TTL) switches the AO, DAC "
         "ry_980_intensity_control is the intensity-PID setpoint.  The laser and its "
         "siglent are not driven from here."),
    fields=(
        Arg("v_pd", "PID setpoint", unit="V", decimals=3, step=0.05, minimum=0.,
            maximum=V_DAC_MAX,
            default=lambda ctx: _frame_attr(ctx, "dac", "ry_980_intensity_control", "v"),
            readback=lambda ctx: ctx.dac_voltage("ry_980_intensity_control"),
            tooltip="Intensity-PID setpoint (ry_980.set_power: DAC, then a PID clear "
                    "pulse). ↺ = the dac_id default."),
    ),
    ops=(
        Op("on", "On", code="expt.ry_980.on()", tooltip="Switch AO on (ry_980_sw)."),
        Op("off", "Off", code="expt.ry_980.off()", tooltip="Switch AO off."),
        Op("set_power", "Set", args=("v_pd",),
           tooltip="ry_980.set_power: setpoint DAC, then a 10 us PID clear pulse "
                   "(clears the 405 PID too).",
           code="expt.ry_980.set_power({v_pd})\nexpt.ry_980.ttl_pid_clear.off()"),
        Op("pid_clear", "Clear PID integrators",
           code="expt.ry_980.ttl_pid_clear.pulse(10.e-6)\nexpt.ry_980.ttl_pid_clear.off()",
           tooltip="10 us pulse on ry_intensity_pid_clear. " + RY_PID_CLEAR_NOTE),
    ),
    lamps=(Lamp("switch", "ttl", "ry_980_sw"),),
    state=_ry_980_state,
    layout=(
        Buttons(("on", "off"), main=True),
        FieldRow(("v_pd",), ("set_power",)),
        Buttons(("pid_clear",)),
        Info(lambda ctx: RY_PID_CLEAR_NOTE),
    ),
)


# --- lightsheet ----------------------------------------------------------------------

def _paint_text(v, v_min):
    if v is None:
        return "--"
    return "off" if v <= v_min + 1.e-3 else f"{v:.2f} V"


def _lightsheet_state(ctx):
    on = ctx.is_on("ttl", "lightsheet_sw")
    if on is None:
        return Status("unknown", "")
    v = ctx.dac_voltage("vva_lightsheet")
    if on:
        return Status("on", f"ON {v:.2f} V" if v is not None else "ON",
                      "RF switch on" + (f", setpoint {v:.3f} V" if v is not None else ""))
    return Status("off", "off")


T_RAMP = Arg("t_ramp", "Ramp time", unit="ms", scale=1e3, decimals=1, step=10.,
             minimum=1.e-3, maximum=10., default=100.e-3,
             tooltip="Duration of Ramp (100 steps).")

LIGHTSHEET = CompositeDevice(
    key="lightsheet",
    title="Lightsheet",
    group="Traps",
    doc=("expt.lightsheet: lightsheet_sw (TTL) switches the RF to the amplifier, "
         "vva_lightsheet is the PID setpoint, lightsheet_paint_amp the painting "
         "amplitude, lightsheet_pid_int_hold_zero holds the PID integrator.  The "
         "Precilaser that feeds it is not driven from here."),
    fields=(
        Arg("v_pd", "Setpoint", unit="V", decimals=3, step=0.05, minimum=0., maximum=V_DAC_MAX,
            default=lambda ctx: ctx.params.v_pd_lightsheet,
            readback=lambda ctx: ctx.dac_voltage("vva_lightsheet"),
            check=lambda v, ctx: (Check.warn(
                f"above the loading setpoint v_pd_lightsheet_rampup_end "
                f"({ctx.params.v_pd_lightsheet_rampup_end:.2f} V)")
                if ctx.params is not None and v > ctx.params.v_pd_lightsheet_rampup_end
                else None),
            param="v_pd_lightsheet",
            tooltip="PID setpoint (DAC vva_lightsheet). ↺ = ExptParams v_pd_lightsheet."),
        Arg("paint", "Painting", unit="V", decimals=3, step=0.1,
            minimum=-V_DAC_MAX, maximum=V_PAINT_MAX, default=V_LIGHTSHEET_PAINT_MIN,
            readback=lambda ctx: ctx.dac_voltage("lightsheet_paint_amp"),
            tooltip=f"Painting amplitude DAC: {V_LIGHTSHEET_PAINT_MIN} V = none, "
                    f"+{V_PAINT_MAX:g} V = full.  ↺ = none."),
        T_RAMP,
    ),
    ops=(
        Op("on", "On", args=("v_pd",),
           tooltip="Setpoint to v_pd, RF switch on, integrator hold released "
                   "(lightsheet.on_and_end_hold with a setpoint).  Painting unchanged.",
           code="""
expt.lightsheet.set_power({v_pd})
expt.lightsheet.ttl_sw.on()
delay(1.e-6)
expt.lightsheet.pid_int_zero_ttl.off()
"""),
        Op("off", "Off", code="expt.lightsheet.off()\nexpt.lightsheet.pid_int_zero_ttl.off()",
           tooltip="lightsheet.off(): RF switch off, setpoint to v_pd_lightsheet_pd_minimum, "
                   "integrator cleared (hold line left low)."),
        Op("set_power", "Set", args=("v_pd",), code="expt.lightsheet.set_power({v_pd})"),
        Op("ramp", "Ramp", args=("v_pd", "t_ramp"),
           tooltip="Linear setpoint ramp from where it is to v_pd over t_ramp; the "
                   "switch and painting are not touched.",
           code="expt.lightsheet.pid_dac.linear_ramp({t_ramp}, "
                "expt.lightsheet.pid_dac.v, {v_pd}, 100)"),
        Op("set_paint", "Set", args=("paint",),
           code="expt.lightsheet.paint_amp_dac.set(v={paint})"),
        Op("paint_off", "Painting off", code="expt.lightsheet.painting_off()"),
        Op("zero_pid", "Clear PID integrator",
           code="expt.lightsheet.zero_pid()\nexpt.lightsheet.pid_int_zero_ttl.off()",
           tooltip="lightsheet.zero_pid(): 10 ns pulse on lightsheet_pid_int_hold_zero "
                   "(the line is left low: integrating)."),
        Op("off_and_hold", "Off, hold integrator", code="expt.lightsheet.off_and_hold_pid()",
           tooltip="lightsheet.off_and_hold_pid(): integrator held, then RF off."),
    ),
    lamps=(Lamp("RF switch", "ttl", "lightsheet_sw"),),
    readouts=(
        Readout("setpoint", lambda ctx: None if ctx.dac_voltage("vva_lightsheet") is None
                else f"{ctx.dac_voltage('vva_lightsheet'):.3f} V"),
        Readout("paint", lambda ctx: _paint_text(ctx.dac_voltage("lightsheet_paint_amp"),
                                                 V_LIGHTSHEET_PAINT_MIN)),
    ),
    state=_lightsheet_state,
    layout=(
        Buttons(("on", "off"), main=True),
        FieldRow(("v_pd",), ("set_power", "ramp")),
        FieldRow(("t_ramp",)),
        FieldRow(("paint",), ("set_paint", "paint_off")),
        ChannelToggle("lightsheet_pid_int_hold_zero", "PID integrator (ttl 12)",
                      on_text="HELD at zero", off_text="running",
                      tooltip="lightsheet_pid_int_hold_zero: high holds the PID "
                              "integrator (servo disabled), low lets it integrate."),
        Buttons(("zero_pid",)),
        Menu(("off_and_hold",)),
    ),
)


# --- tweezer -------------------------------------------------------------------------

def _trap_rows_default(ctx):
    p = ctx.params if ctx is not None else None
    if p is None:
        return [[75.e6, 0.18]]
    f = list(p.frequency_tweezer_list)
    a = list(p.amp_tweezer_list)
    return [[float(fi), float(ai)] for fi, ai in zip(f, a)]


def _in_mesh(f):
    return (F_CE_MIN <= f <= F_CE_MAX) or (F_NCE_MIN <= f <= F_NCE_MAX)


def _traps_check(rows, ctx):
    found = []
    total = sum(r[1] for r in rows)
    if total > 1. + 1e-9:
        found.append(Check.error(f"amplitudes sum to {total:.3f} > 1 (the AWG output "
                                 f"would clip; add_tweezer_list refuses this too)"))
    outside = [r[0] for r in rows if not _in_mesh(r[0])]
    if outside:
        found.append(Check.warn(
            "outside the calibrated position mesh (cateye "
            f"{F_CE_MIN / 1e6:g}-{F_CE_MAX / 1e6:g}, non-cateye {F_NCE_MIN / 1e6:g}-"
            f"{F_NCE_MAX / 1e6:g} MHz): "
            + ", ".join(f"{f / 1e6:.3f}" for f in outside)
            + " MHz -- positions extrapolated"))
    freqs = sorted(r[0] for r in rows)
    if any(b - a < 1.e3 for a, b in zip(freqs, freqs[1:])):
        found.append(Check.warn("two traps within 1 kHz of each other"))
    return found


def _trap_position(row, ctx):
    try:
        x = float(tweezer_xmesh.f_to_x(row[0])[0])
    except Exception:
        return ""
    return f"{x * 1e6:+.2f} µm" + ("" if _in_mesh(row[0]) else " (extrap.)")


def _awg_write(tw, rows):
    """Program static tones: one per row, and zero any tone this panel set
    before that is no longer listed (set_static_tweezers only writes the
    tones it is given).  Takes effect on the next AWG trigger."""
    freqs = [float(r[0]) for r in rows]
    amps = [float(r[1]) for r in rows]
    if sum(amps) > 1. + 1e-9:
        raise ValueError(f"amplitudes sum to {sum(amps):.3f} > 1")
    n_prev = int(getattr(tw, "_panel_n_tones", 0))
    if freqs:
        if sum(amps) > 0.:
            tw.set_static_tweezers(freqs, amps)
        else:
            # compute_tweezer_phases divides by the total amplitude.
            tw.set_static_tweezers(freqs, amps, [0.] * len(freqs))
    if n_prev > len(freqs):
        for idx in range(len(freqs), n_prev):
            tw.dds[idx].amp(0.)
        tw.dds.exec_at_trg()
        tw.dds.write()
    tw._panel_n_tones = len(freqs)
    tw._panel_traps = [[f, a] for f, a in zip(freqs, amps)]


def awg_connect(expt, args, payload):
    """Host step: open the AWG (awg_init: DDS mode, trigger on ext0) and load
    the trap table; the op's kernel code then triggers it."""
    tw = expt.tweezer
    tw.awg_init()
    tw._panel_n_tones = 0
    _awg_write(tw, payload["traps"])


def awg_apply(expt, args, payload):
    tw = expt.tweezer
    if getattr(tw, "card", None) is None:
        raise RuntimeError("the AWG is not connected by this monitor -- press Connect first")
    _awg_write(tw, payload["traps"])


def awg_disconnect(expt, args, payload):
    """Host step, after the kernel turned the AOD RF switch off: stop the card
    and release the connection (TweezerController.reset_awg)."""
    tw = expt.tweezer
    tw.reset_awg()
    tw._panel_n_tones = 0
    tw._panel_traps = []


def tweezer_host_state(expt):
    tw = expt.tweezer
    return {"awg_connected": getattr(tw, "card", None) is not None,
            "traps": [list(t) for t in getattr(tw, "_panel_traps", [])]}


def _awg_text(ctx):
    st = ctx.host_state
    if not st or not st.get("awg_connected"):
        return "not connected by this monitor"
    traps = st.get("traps") or []
    return (f"connected, {len(traps)} tone(s)" +
            (": " + ", ".join(f"{f / 1e6:.3f}" for f, _ in traps) + " MHz" if traps else ""))


def _tweezer_state(ctx):
    rf = ctx.is_on("ttl", "aod_rf_sw")
    ao1 = ctx.is_on("dds", "tweezer_pid_1")
    if rf is None:
        return Status("unknown", "")
    low = ctx.is_on("ttl", "tweezer_pid2_enable")
    if rf and ao1:
        if low:
            v = ctx.dac_voltage("v_pd_tweezer_pid2")
            return Status("on", "ON PID2" + (f" {v:.2f} V" if v is not None else ""),
                          "RF switch on, AO1 on, low-power servo (PID2)")
        v = ctx.dac_voltage("v_pd_tweezer_pid1")
        return Status("on", "ON PID1" + (f" {v:.2f} V" if v is not None else ""),
                      "RF switch on, AO1 on, high-power servo (PID1)")
    if rf or ao1:
        return Status("partial", "partial",
                      f"RF switch {'on' if rf else 'off'}, AO1 {'on' if ao1 else 'off'}")
    return Status("off", "off")


def _tweezer_on_check(args, ctx):
    if not ctx.host_state.get("awg_connected"):
        return Check.warn("this monitor has not connected the AWG: unless it is running "
                          "from elsewhere there is no RF on the AOD (Connect loads it)")
    return None


def _pd2_info(ctx):
    v2 = ctx.field("v_pd2")
    if v2 is None:
        return None
    return f"PID2 {v2:.3f} V ≈ PID1 {tweezer_vpd2_to_vpd1(v2):.4f} V (kexp.calibrations.tweezer)"


TWEEZER = CompositeDevice(
    key="tweezer",
    title="Tweezer",
    group="Traps",
    doc=("expt.tweezer: AWG (Spectrum, host-side) makes the AOD tones, aod_rf_sw "
         "gates them to the amplifier, awg_trigger applies queued AWG changes.  "
         "tweezer_pid_1 (DAC v_pd_tweezer_pid1) is the high-power servo, "
         "tweezer_pid_2 (DAC v_pd_tweezer_pid2, enabled by tweezer_pid2_enable) the "
         "low-power one.  tweezer_paint_amp sets painting.  The ALS laser that feeds "
         "it is not driven from here."),
    fields=(
        Arg("v_pd1", "PID1 setpoint", unit="V", decimals=3, step=0.05, minimum=0.,
            maximum=V_DAC_MAX, default=lambda ctx: ctx.params.v_pd_tweezer_1064,
            readback=lambda ctx: ctx.dac_voltage("v_pd_tweezer_pid1"),
            check=lambda v, ctx: (Check.warn(
                f"above v_pd_hf_tweezer_1064_ramp_end "
                f"({ctx.params.v_pd_hf_tweezer_1064_ramp_end:.2f} V)")
                if ctx.params is not None and v > ctx.params.v_pd_hf_tweezer_1064_ramp_end
                else None),
            param="v_pd_tweezer_1064",
            tooltip="High-power servo setpoint (tweezer.set_power). ↺ = "
                    "ExptParams v_pd_tweezer_1064."),
        Arg("v_pd2", "PID2 setpoint", unit="V", decimals=3, step=0.05, minimum=0.,
            maximum=V_DAC_MAX, default=lambda ctx: ctx.params.v_pd_hf_tweezer_1064_rampdown2_end,
            readback=lambda ctx: ctx.dac_voltage("v_pd_tweezer_pid2"),
            param="v_pd_hf_tweezer_1064_rampdown2_end",
            tooltip="Low-power servo setpoint (pid2_dac). ↺ = ExptParams "
                    "v_pd_hf_tweezer_1064_rampdown2_end."),
        Arg("paint", "Painting", unit="V", decimals=3, step=0.1,
            minimum=-V_DAC_MAX, maximum=V_PAINT_MAX, default=V_TWEEZER_PAINT_MIN,
            readback=lambda ctx: ctx.dac_voltage("tweezer_paint_amp"),
            tooltip=f"Painting amplitude DAC: {V_TWEEZER_PAINT_MIN} V = none, "
                    f"+{V_PAINT_MAX:g} V = full.  ↺ = none."),
        T_RAMP,
    ),
    tables=(
        Table("traps", "AWG traps",
              columns=(
                  Arg("f", "Frequency", unit="MHz", scale=1e-6, decimals=4, step=0.1,
                      minimum=50.e6, maximum=100.e6, default=75.e6,
                      tooltip="AOD tone. Hard 50-100 MHz is a typo guard, not a device limit."),
                  Arg("a", "Amplitude", decimals=3, step=0.01, minimum=0., maximum=1.,
                      default=0.1),
              ),
              default=_trap_rows_default, check=_traps_check,
              info=_trap_position, info_label="position",
              min_rows=0, max_rows=16,
              tooltip="Static AWG tones. ‘Defaults’ = ExptParams "
                      "frequency_tweezer_list / amp_tweezer_list."),
    ),
    ops=(
        Op("awg_connect", "Connect AWG + load", payload=("traps",), host=awg_connect,
           code="expt.tweezer.trigger()",
           tooltip="Host: awg_init() and load the trap table; then trigger the AWG. "
                   "The AOD RF switch is not touched."),
        Op("awg_apply", "Apply traps", payload=("traps",), host=awg_apply,
           code="expt.tweezer.trigger()",
           tooltip="Rewrite the static tones (removed rows go to zero amplitude), trigger."),
        Op("awg_disconnect", "Disconnect AWG", host=awg_disconnect, host_after=True,
           code="expt.tweezer.sw_ttl.off()", confirm="Stops the AWG output.",
           tooltip="AOD RF switch off, then reset_awg() (stop + release the card)."),
        Op("trigger", "Trigger AWG", code="expt.tweezer.trigger()"),
        Op("on", "On", args=("v_pd1", "paint"), check=_tweezer_on_check,
           tooltip="PID AO setpoints made explicit (AO1 at 0 V, AO2 at the PID2 "
                   "setpoint, so DDS.on cannot restore a stale one), then tweezer.on "
                   "(painting at the field value): PID1 to 0, AO2 + AO1 on, RF switch "
                   "on, PID1 integrator cleared; 1 ms; PID1 setpoint to v_pd1.",
           code="""
expt.tweezer.ao1_dds.update_dac_setpoint(0.)
expt.tweezer.ao2_dds.update_dac_setpoint(expt.tweezer.pid2_dac.v)
expt.tweezer.on(paint=True, v_awg_am={paint})
expt.tweezer.pid1_int_hold_zero.off()
delay(1.e-3)
expt.tweezer.set_power({v_pd1})
"""),
        Op("off", "Off", code="expt.tweezer.off()",
           tooltip="tweezer.off(): both AOs off, PID1 integrator held, PID1 to 0, "
                   "PID2 disabled, RF switch off."),
        Op("set_pd1", "Set", args=("v_pd1",), code="expt.tweezer.set_power({v_pd1})"),
        Op("ramp_pd1", "Ramp", args=("v_pd1", "t_ramp"),
           code="expt.tweezer.pid1_dac.linear_ramp({t_ramp}, expt.tweezer.pid1_dac.v, "
                "{v_pd1}, 100)"),
        Op("set_pd2", "Set", args=("v_pd2",), code="expt.tweezer.pid2_dac.set(v={v_pd2})"),
        Op("ramp_pd2", "Ramp", args=("v_pd2", "t_ramp"),
           code="expt.tweezer.pid2_dac.linear_ramp({t_ramp}, expt.tweezer.pid2_dac.v, "
                "{v_pd2}, 100)"),
        Op("servo_high", "High power (PID1)", code="expt.tweezer.pid2_enable_ttl.off()",
           tooltip="PID2 disabled: PID1 holds the power."),
        Op("servo_low", "Low power (PID2)", args=("v_pd2",),
           code="expt.tweezer.pid2_dac.set(v={v_pd2})\nexpt.tweezer.pid2_enable_ttl.on()",
           tooltip="PID2 setpoint to v_pd2, then PID2 enabled (as a low_power ramp starts)."),
        Op("set_paint", "Set", args=("paint",), code="expt.tweezer.paint_amp_dac.set(v={paint})"),
        Op("paint_off", "Painting off", code="expt.tweezer.painting_off()"),
        Op("pid1_clear", "Clear PID1 integrator",
           code="expt.tweezer.pid1_int_hold_zero.pulse(1.e-6)\n"
                "expt.tweezer.pid1_int_hold_zero.off()",
           tooltip="1 us pulse on tweezer_pid1_int_hold_zero (as tweezer.on does); "
                   "the line is left low (integrating)."),
    ),
    lamps=(
        Lamp("RF switch", "ttl", "aod_rf_sw"),
        Lamp("AO1", "dds", "tweezer_pid_1"),
        Lamp("AO2", "dds", "tweezer_pid_2"),
        Lamp("servo", "ttl", "tweezer_pid2_enable", "PID2 (low)", "PID1 (high)", "ok"),
    ),
    readouts=(Readout("AWG:", _awg_text),),
    state=_tweezer_state,
    host_state=tweezer_host_state,
    layout=(
        Buttons(("on", "off"), main=True),
        FieldRow(("v_pd1",), ("set_pd1", "ramp_pd1")),
        FieldRow(("v_pd2",), ("set_pd2", "ramp_pd2")),
        Info(_pd2_info),
        Buttons(("servo_high", "servo_low")),
        FieldRow(("t_ramp",)),
        FieldRow(("paint",), ("set_paint", "paint_off")),
        ChannelToggle("aod_rf_sw", "AOD RF switch (ttl 13)", on_text="on", off_text="off",
                      on_level="ok", tooltip="aod_rf_sw: gates the AWG output to the amplifier."),
        ChannelToggle("tweezer_pid1_int_hold_zero", "PID1 integrator (ttl 11)",
                      on_text="HELD at zero", off_text="running",
                      tooltip="tweezer_pid1_int_hold_zero: high holds PID1's integrator at "
                              "zero (tweezer.off leaves it high), low lets it integrate."),
        Buttons(("pid1_clear",)),
        TableRow("traps", ("awg_connect", "awg_apply")),
        Menu(("trigger", "awg_disconnect")),
    ),
)


# --- coils ---------------------------------------------------------------------------

def _coil_sync(c: str) -> str:
    """Re-derive a coil's cached currents and PID flag from its channels, so
    a ramp starts from what the DAC tab (or the last experiment) left."""
    return f"""
{c}.i_supply = {c}.supply_vdac_to_current({c}.i_control_dac.v)
{c}.i_pid = {c}.pid_vdac_to_current({c}.pid_dac.v)
{c}.pid_on = {c}.pid_ttl.state == 1
"""


def _coil_off_body(c: str) -> str:
    """Ramp coil ``c`` down from where it is and leave it open, PID off and
    discharged.  Needs ``{t_ramp}`` and ``{i_meas}`` fields: ``i_meas`` >= 0 is
    a measured current to start the ramp from (not with the PID on -- the
    supply then carries the PID overhead, which the coil does not)."""
    return _coil_sync(c) + f"""
i0 = {c}.i_supply
if {{i_meas}} >= 0. and not {c}.pid_on:
    i0 = {{i_meas}}
if {c}.pid_on:
    {c}.stop_pid()
    delay(50.e-3)
    i0 = {c}.i_supply
{c}.ramp_supply(t={{t_ramp}}, i_start=i0, i_end=0., n_steps=100)
{c}.set_voltage(0.)
delay(30.e-3)
{c}.igbt_ttl.off()
{c}.pid_ttl.off()
{c}.pid_on = False
delay(5.e-3)
{c}.discharge()
"""


def _coil_ops(c: str, pid: bool, hbridge: bool) -> tuple:
    """Ops for one coil; ``c`` is its path on expt (``expt.outer_coil``)."""
    sync = _coil_sync(c)
    ops = [
        Op("ramp_to", "Ramp to I", args=("i", "t_ramp", "v_supply", "i_meas"),
           tooltip="From the present current to I over t_ramp (100 steps). If the "
                   "coil is off (IGBT open, and no current measured): supply set to "
                   "0 A, voltage limit set, IGBT closed, then the ramp from 0 A.",
           code=sync + f"""
if {c}.pid_on:
    raise ValueError("coil PID is on")
if {c}.igbt_ttl.state == 0 and {{i_meas}} < {I_COIL_ON!r}:
    {c}.set_supply(0.)
    {c}.set_voltage({{v_supply}})
    {c}.on()
    delay(1.e-3)
    {c}.ramp_supply(t={{t_ramp}}, i_start=0., i_end={{i}}, n_steps=100)
else:
    i0 = {c}.i_supply
    if {{i_meas}} >= 0.:
        i0 = {{i_meas}}
    {c}.set_voltage({{v_supply}})
    {c}.on()
    {c}.ramp_supply(t={{t_ramp}}, i_start=i0, i_end={{i}}, n_steps=100)
"""),
        Op("off", "Off (ramp down)", args=("t_ramp", "i_meas"),
           tooltip="PID stopped if on (stop_pid, 50 ms, as reset_coils), supply ramped "
                   "to 0 A over t_ramp, voltage limit 0, 30 ms, IGBT open, PID off, "
                   "5 ms, discharge().",
           code=_coil_off_body(c)),
        Op("snap_off", "Snap off", danger=True,
           confirm="Snap off opens the IGBT and zeroes the supply at once, with no "
                   "ramp: the current in the coil is interrupted instantly. Use Off "
                   "(ramp down) unless that is what you need.",
           tooltip="big_coil.snap_off(): IGBT open, supply current and voltage to 0; "
                   "PID TTL off.",
           code=f"""
{c}.snap_off()
{c}.pid_ttl.off()
{c}.pid_on = False
"""),
        Op("discharge", "Discharge",
           tooltip="big_coil.discharge(): IGBT closed with zero setpoints for 130 ms, "
                   "then open.",
           code=f"{c}.discharge()"),
    ]
    if pid:
        # start_pid ramps the supply to i + compute_pid_overhead(i); the
        # calibration's numbers are formatted in (no globals in op code).
        i_end = (f"{c}.i_supply + {c}.i_supply * {slope_overhead_per_i_transducer!r} "
                 f"+ {offset_overhead_per_i_transducer!r}")
        ops += [
            Op("pid_on", "PID on",
               tooltip="start_pid() at the present supply current: PID setpoint = I, "
                       "PID TTL on, supply ramped up by the overhead over 50 ms.",
               code=sync + f"""
if {c}.igbt_ttl.state == 0:
    raise ValueError("coil is off")
if {c}.pid_on:
    raise ValueError("coil PID is already on")
if {c}.current_to_supply_vdac({i_end}) > {c}.i_control_dac.max_v:
    raise ValueError("the PID overhead would take the supply DAC past its limit")
{c}.start_pid()
"""),
            Op("pid_off", "PID off",
               tooltip="stop_pid(): supply back to the PID setpoint, 30 ms, PID TTL off.",
               code=sync + f"""
if not {c}.pid_on:
    raise ValueError("coil PID is off")
{c}.stop_pid()
"""),
        ]
    if hbridge:
        ops += [
            Op("helmholtz", "H-bridge → Helmholtz",
               confirm="Switch the H-bridge to Helmholtz (the coil must be off).",
               code=f"""
if {c}.igbt_ttl.state == 1:
    raise ValueError("coil is on")
delay(expt.p.t_hbridge_switch_delay)
expt.ttl.hbridge_helmholtz.on()
"""),
            Op("antihelmholtz", "H-bridge → anti-Helmholtz",
               confirm="Switch the H-bridge to anti-Helmholtz (the coil must be off).",
               code=f"""
if {c}.igbt_ttl.state == 1:
    raise ValueError("coil is on")
delay(expt.p.t_hbridge_switch_delay)
expt.ttl.hbridge_helmholtz.off()
"""),
        ]
    return tuple(ops)


def _measured_current(source):
    """A fresh measured current from telemetry, or None."""
    def get(ctx):
        sample = ctx.measured(source, T_MEASURED_FRESH_S) if hasattr(ctx, "measured") else None
        return None if sample is None else _float(sample.value)
    return get


def _i_meas_arg(source: str) -> Arg:
    measured = _measured_current(source)

    def default(ctx):
        # Only when the state file cannot be trusted: then a ramp must start
        # from what flows, not from what the file says.  Trusted, the DAC
        # value is exact about the DAC, which is what a ramp continues from.
        if getattr(ctx, "trusted", True):
            return -1.
        value = measured(ctx)
        return -1. if value is None else max(value, 0.)

    return Arg("i_meas", "Measured I", unit="A", decimals=1, minimum=-1., maximum=600.,
               default=default, replay=-1.,
               tooltip="Sent with the ramps: the Keysight's measured current when the "
                       "device state is untrusted (the ramp starts there), else -1 "
                       "(start from the DAC setpoint).")


def _interlock_measured() -> Measured:
    def text(sample, ctx):
        state = str(sample.value)
        enabled = ctx.measured("interlock/magnets_enabled", 10.)
        suffix = ""
        if enabled is not None and enabled.value is False:
            suffix = " · magnets DISABLED"
        return state + suffix

    def judge(sample, ctx):
        return "ok" if str(sample.value) == "ok" else "warn"

    return Measured("interlock", "interlock/state", text=text, judge=judge, stale_s=10.,
                    tooltip="Interlock server state (read only): ok | tripped | warmup | "
                            "safe_mode | unknown.")


def _coil_device(key, title, attr, supply_dac, pid_dac, igbt_ttl, pid_ttl,
                 slope, offset, pid_slope, pid_offset, i_max, i_warn, v_default,
                 v_dac_max, keysight, tolerance,
                 pid: bool, hbridge: bool, doc: str) -> CompositeDevice:
    source = f"keysight/{keysight}.current_a"
    measured_now = _measured_current(source)

    def current(ctx):
        v = ctx.dac_voltage(supply_dac)
        return None if v is None else slope * v + offset

    def pid_setpoint(ctx):
        v = ctx.dac_voltage(pid_dac)
        return None if v is None else pid_slope * v + pid_offset

    def expected(ctx):
        if not ctx.is_on("ttl", igbt_ttl):
            return 0.
        return current(ctx)

    def state(ctx):
        igbt = ctx.is_on("ttl", igbt_ttl)
        i = current(ctx)
        if igbt is None:
            return Status("unknown", "")
        pid_on = ctx.is_on("ttl", pid_ttl)
        if not igbt:
            m = measured_now(ctx)
            if m is not None and m > I_COIL_ON:
                return Status("hazard", f"measured {m:.1f} A",
                              "the state file says the IGBT is open, but the Keysight "
                              f"measures {m:.1f} A")
            return Status("off", "off")
        text = f"ON {i:.1f} A" if i is not None else "ON"
        detail = "IGBT closed" + (f", supply setpoint {i:.2f} A" if i is not None else "")
        if pid_on:
            text += " · PID"
            p = pid_setpoint(ctx)
            detail += ", PID on" + (f" at {p:.2f} A" if p is not None else "")
        if (i or 0.) > I_COIL_ON:
            return Status("hazard", text, detail)
        return Status("partial", text, detail + " (no current)")

    def hazard(ctx):
        st = state(ctx)
        return st.text if st.level == "hazard" else None

    def trust_check(args, ctx):
        if ctx.trusted:
            return None
        if measured_now(ctx) is None:
            return Check.error(
                "the device state is untrusted (" + str(ctx.trust.get("reason", "")) + ") "
                "and there is no fresh measured current from the Keysight server: the "
                "ramp would start from a guess. Bring the Keysight server up, or use "
                "'Trust state' once you know the file is right (Snap off works regardless).")
        return None

    def ramp_check(args, ctx):
        if ctx.is_on("ttl", pid_ttl):
            return Check.error("the PID is on -- turn it off first (PID off), then ramp")
        return None

    def pid_on_check(args, ctx):
        if not ctx.is_on("ttl", igbt_ttl):
            return Check.error("the coil is off (IGBT open): ramp it to the current "
                               "you want the PID to hold first")
        if ctx.is_on("ttl", pid_ttl):
            return Check.error("the PID is already on (starting it again would add "
                               "the overhead a second time)")
        i = current(ctx)
        if i is not None and i < I_COIL_ON:
            return Check.error(f"supply at {i:.2f} A: the PID engages at the present "
                               "current -- ramp up first")
        if i is not None:
            v_max = _frame_attr(ctx, "dac", supply_dac, "max_v", v_dac_max)
            i_end = i + i * slope_overhead_per_i_transducer + offset_overhead_per_i_transducer
            i_dac_max = slope * float(v_max) + offset
            if i_end > i_dac_max:
                return Check.error(
                    f"PID on at {i:.1f} A ramps the supply to {i_end:.1f} A (overhead), "
                    f"above what its DAC can set ({i_dac_max:.1f} A at {float(v_max):g} V): "
                    f"the DAC would write 0 V instead")
        return None

    def pid_off_check(args, ctx):
        if not ctx.is_on("ttl", pid_ttl):
            return Check.error("the PID is off -- PID off would set the supply to the "
                               "last PID setpoint")
        return None

    def discharge_check(args, ctx):
        i = current(ctx)
        if ctx.is_on("ttl", igbt_ttl) and i is not None and i > I_COIL_ON:
            return Check.warn(f"the coil is on at {i:.1f} A: discharge sets the supply "
                              "to 0 A at once (no ramp)")
        return None

    def hbridge_check(args, ctx):
        if ctx.is_on("ttl", igbt_ttl):
            return Check.error("the coil is on (IGBT closed) -- Off (ramp down) first")
        return None

    checks = {"ramp_to": _checks(ramp_check, trust_check), "off": trust_check,
              "pid_on": pid_on_check, "pid_off": pid_off_check,
              "discharge": discharge_check, "helmholtz": hbridge_check,
              "antihelmholtz": hbridge_check}
    ops = []
    for op in _coil_ops(f"expt.{attr}", pid, hbridge):
        check = checks.get(op.key)
        if check is not None:
            op = replace(op, check=check)
        ops.append(op)

    lamps = [Lamp("IGBT", "ttl", igbt_ttl, "closed", "open", "warn"),
             Lamp("PID", "ttl", pid_ttl, "on", "off", "ok")]
    if hbridge:
        lamps.append(Lamp("H-bridge", "ttl", "hbridge_helmholtz", "Helmholtz",
                          "anti-Helmholtz", "ok"))
    readouts = [Readout("supply", lambda ctx: None if current(ctx) is None
                        else f"{current(ctx):.2f} A")]
    if pid:
        readouts.append(Readout("PID set", lambda ctx: None if pid_setpoint(ctx) is None
                                else f"{pid_setpoint(ctx):.2f} A"))
    measured = (
        Measured("measured", source, unit="A", decimals=1, expect=expected,
                 tolerance=tolerance, stale_s=T_MEASURED_FRESH_S,
                 tooltip=f"Keysight {keysight} supply, measured output current (read "
                         f"only). Orange: more than {tolerance:g} A from the "
                         f"commanded current (0 A with the IGBT open)."),
        Measured("output", f"keysight/{keysight}.output_on", stale_s=T_MEASURED_FRESH_S,
                 text=lambda s, ctx: "on" if s.value else "OFF",
                 judge=lambda s, ctx: "ok" if s.value else "warn",
                 tooltip="Keysight output enable (read only)."),
        _interlock_measured(),
    )
    layout = [
        FieldRow(("i",), ("ramp_to",)),
        FieldRow(("t_ramp", "v_supply")),
        Buttons(("off",), main=True),
    ]
    if pid:
        layout.append(Buttons(("pid_on", "pid_off")))
    menu = ["discharge", "snap_off"]
    if hbridge:
        menu = ["helmholtz", "antihelmholtz"] + menu
    layout.append(Menu(tuple(menu)))

    return CompositeDevice(
        key=key, title=title, doc=doc, group="Coils & fields",
        fields=(
            Arg("i", "Current", unit="A", decimals=2, step=1., minimum=0., maximum=i_max,
                warn_above=i_warn, readback=current, default=0.,
                tooltip=f"Supply current (transducer A). Hard limit {i_max:g} A (supply "
                        f"DAC max_v); asks above {i_warn:g} A."),
            Arg("t_ramp", "Ramp time", unit="ms", scale=1e3, decimals=1, step=10.,
                minimum=5.e-3, maximum=10., default=50.e-3,
                tooltip="Duration of Ramp to I and of Off's ramp down (100 steps)."),
            Arg("v_supply", "V limit", unit="V", decimals=1, step=1., minimum=0.,
                maximum=V_COIL_SUPPLY_MAX, default=v_default,
                tooltip="Supply voltage (compliance) setpoint, set by Ramp to I."),
            _i_meas_arg(source),
        ),
        ops=tuple(ops),
        lamps=tuple(lamps),
        readouts=tuple(readouts),
        measured=measured,
        state=state,
        hazard=hazard,
        safe_op="off",
        max_on_s=COIL_MAX_ON_S,
        layout=tuple(layout),
    )


OUTER_COIL = _coil_device(
    "outer_coil", "Outer coil (Feshbach)", "outer_coil",
    supply_dac="outer_coil_supply_current", pid_dac="outer_coil_pid",
    igbt_ttl="outer_coil_igbt", pid_ttl="outer_coil_pid_ttl",
    slope=slope_i_transducer_per_v_setpoint_supply_outer,
    offset=offset_i_transducer_per_v_setpoint_supply_outer,
    pid_slope=slope_i_transducer_per_v_setpoint_pid_outer,
    pid_offset=offset_i_transducer_per_v_setpoint_pid_outer,
    i_max=I_OUTER_MAX, i_warn=I_OUTER_WARN, v_default=70.,
    v_dac_max=V_OUTER_SUPPLY_DAC_MAX, keysight="outer", tolerance=I_OUTER_MEASURED_TOL,
    pid=True, hbridge=False,
    doc=("expt.outer_coil (igbt_magnet): supply current DAC outer_coil_supply_current, "
         "voltage DAC outer_coil_supply_voltage, IGBT outer_coil_igbt, PID setpoint DAC "
         "outer_coil_pid, PID enable outer_coil_pid_ttl.  Currents use "
         "kexp.calibrations.magnets.  Measured current: the 500 A Keysight (.78)."))

INNER_COIL = _coil_device(
    "inner_coil", "Inner coil", "inner_coil",
    supply_dac="inner_coil_supply_current", pid_dac="inner_coil_pid",
    igbt_ttl="inner_coil_igbt", pid_ttl="inner_coil_pid_ttl",
    slope=slope_i_per_v_setpoint_supply_inner, offset=0.,
    pid_slope=1., pid_offset=0.,
    i_max=I_INNER_MAX, i_warn=I_INNER_WARN, v_default=20.,
    v_dac_max=V_INNER_SUPPLY_DAC_MAX, keysight="inner", tolerance=I_INNER_MEASURED_TOL,
    pid=False, hbridge=True,
    doc=("expt.inner_coil (hbridge_magnet): supply current DAC inner_coil_supply_current "
         "(17 A/V), voltage DAC inner_coil_supply_voltage, IGBT inner_coil_igbt, "
         "H-bridge hbridge_helmholtz.  Its PID TTL is shown; PID control is offered "
         "for the outer coil only.  Measured current: the 170 A Keysight (.77)."))


# --- shims ---------------------------------------------------------------------------

def _shim_arg(axis: str, param: str) -> Arg:
    dac = f"{axis}shim_current_control"
    return Arg(axis, f"{axis} shim", unit="V", decimals=3, step=0.05, minimum=0.,
               maximum=V_DAC_MAX, warn_above=V_SHIM_WARN,
               default=lambda ctx: getattr(ctx.params, param, None),
               readback=lambda ctx: ctx.dac_voltage(dac), param=param,
               tooltip=f"DAC {dac} (shim supply control voltage). ↺ = ExptParams "
                       f"{param} (the MOT value). Asks above {V_SHIM_WARN:g} V.")


def _shim_presets(ctx):
    p = ctx.params
    if p is None:
        return None
    parts = []
    for name, suffix in (("MOT", ""), ("GM", "_gm"), ("OP", "_op")):
        try:
            vals = [float(getattr(p, f"v_{a}shim_current{suffix}")) for a in "xyz"]
        except (AttributeError, TypeError, ValueError):
            continue
        parts.append(f"{name} {vals[0]:.2f}/{vals[1]:.2f}/{vals[2]:.2f}")
    return "presets (x/y/z V): " + " · ".join(parts) if parts else None


def _shims_state(ctx):
    vals = [ctx.dac_voltage(f"{a}shim_current_control") for a in "xyz"]
    if any(v is None for v in vals):
        return Status("unknown", "")
    flipped = ctx.is_on("ttl", "zshim_hbridge_flip")
    text = "/".join(f"{v:.2f}" for v in vals) + " V"
    detail = f"x {vals[0]:.3f} V, y {vals[1]:.3f} V, z {vals[2]:.3f} V" + \
             (", z polarity flipped" if flipped else "")
    if all(abs(v) < 1.e-3 for v in vals):
        return Status("off", "zero", detail)
    level = "warn" if any(v > V_SHIM_WARN for v in vals) else "on"
    return Status(level, text + (" · z flip" if flipped else ""), detail)


def _z_flip_check(args, ctx):
    v = ctx.dac_voltage("zshim_current_control")
    if v is not None and v > 0.01:
        return Check.error(f"z shim at {v:.3f} V -- set it to 0 V before flipping its "
                           "H-bridge")
    return None


Z_ZERO_CHECK = """
if expt.dac.zshim_current_control.v > 0.01:
    raise ValueError("z shim is not at 0 V")
"""

SHIMS = CompositeDevice(
    key="shims",
    title="Shim coils",
    group="Coils & fields",
    doc=("Cooling.set_shims: DACs xshim/yshim/zshim_current_control set the three shim "
         "supplies; zshim_hbridge_flip reverses the z shim (mot() sets it normal)."),
    fields=(_shim_arg("x", "v_xshim_current"), _shim_arg("y", "v_yshim_current"),
            _shim_arg("z", "v_zshim_current")),
    ops=(
        Op("set", "Set", args=("x", "y", "z"), code="expt.set_shims({x}, {y}, {z})",
           tooltip="set_shims(x, y, z): all three at once."),
        Op("preset_mot", "MOT", tooltip="set_shims with the ExptParams MOT values.",
           code="expt.set_shims(expt.p.v_xshim_current, expt.p.v_yshim_current, "
                "expt.p.v_zshim_current)"),
        Op("preset_gm", "GM", tooltip="set_shims with the ExptParams gray-molasses values.",
           code="expt.set_shims(expt.p.v_xshim_current_gm, expt.p.v_yshim_current_gm, "
                "expt.p.v_zshim_current_gm)"),
        Op("preset_op", "OP", tooltip="set_shims with the ExptParams optical-pumping values.",
           code="expt.set_shims(expt.p.v_xshim_current_op, expt.p.v_yshim_current_op, "
                "expt.p.v_zshim_current_op)"),
        Op("zero", "Zero", code="expt.set_shims(0., 0., 0.)", tooltip="All three to 0 V."),
        Op("z_normal", "z polarity normal", check=_z_flip_check,
           code=Z_ZERO_CHECK + "\nexpt.ttl.zshim_hbridge_flip.off()",
           tooltip="zshim_hbridge_flip low (as mot() leaves it). Needs the z shim at 0 V."),
        Op("z_flipped", "z polarity flipped", check=_z_flip_check,
           code=Z_ZERO_CHECK + "\nexpt.ttl.zshim_hbridge_flip.on()",
           confirm="Reverse the z shim's polarity?",
           tooltip="zshim_hbridge_flip high. Needs the z shim at 0 V."),
    ),
    lamps=(Lamp("z polarity", "ttl", "zshim_hbridge_flip", "flipped", "normal", "warn"),),
    state=_shims_state,
    layout=(
        FieldRow(("x",), ("set",)),
        FieldRow(("y",)),
        FieldRow(("z",)),
        Buttons(("preset_mot", "preset_gm", "preset_op", "zero")),
        Info(_shim_presets),
        Menu(("z_normal", "z_flipped")),
    ),
)


# --- MOT -----------------------------------------------------------------------------

def _mot_state(ctx):
    d3 = ctx.is_on("dds", "d2_3d_c")
    d2 = ctx.is_on("dds", "d2_2dh_c")
    push = ctx.is_on("dds", "push")
    coil = ctx.is_on("ttl", "inner_coil_igbt")
    if d3 is None or coil is None:
        return Status("unknown", "")
    detail = (f"3D beams {'on' if d3 else 'off'}, 2D beams {'on' if d2 else 'off'}, "
              f"push {'on' if push else 'off'}, inner coil {'on' if coil else 'off'}")
    if d3 and d2 and push and coil:
        return Status("on", "ON", detail)
    if not (d3 or d2 or push or coil):
        return Status("off", "off", detail)
    return Status("partial", "partial", detail)


def _mot_on_check(args, ctx):
    found = []
    if ctx.is_on("ttl", "inner_coil_pid_ttl"):
        found.append(Check.error("the inner coil's PID TTL is on"))
    if ctx.is_on("ttl", "hbridge_helmholtz"):
        found.append(Check.error("the H-bridge is in Helmholtz -- a MOT needs "
                                 "anti-Helmholtz (Inner coil ⋯ menu)"))
    v = ctx.dac_voltage("inner_coil_supply_current")
    i_now = None if v is None else slope_i_per_v_setpoint_supply_inner * v
    m = _measured_current("keysight/inner.current_a")(ctx)
    if m is not None and (i_now is None or m > i_now):
        i_now = m
    coil_on = ctx.is_on("ttl", "inner_coil_igbt") or (m is not None and m > I_COIL_ON)
    if coil_on and i_now is not None and i_now > float(args.get("i", 0.)) + 5.:
        found.append(Check.error(f"the inner coil is at {i_now:.1f} A: MOT on would snap it "
                                 f"to {float(args.get('i', 0.)):.1f} A -- ramp it down "
                                 "first (Inner coil, or MOT Off)"))
    if not ctx.trusted and m is None:
        found.append(Check.error("the device state is untrusted and there is no fresh "
                                 "measured inner-coil current: cannot tell what the coil "
                                 "is at"))
    return found


MOT = CompositeDevice(
    key="mot",
    title="MOT",
    group="Cooling",
    doc=("Cooling.load_2D_mot + Cooling.mot with the ExptParams defaults: 2D beams, "
         "2D coil current, 3D beams, push, inner coil at the MOT current (switched "
         "on at it, as every sequence does), MOT shim values, z polarity normal.  Off "
         "turns the light and 2D current off and RAMPS the inner coil down."),
    fields=(
        Arg("i", "Coil current", unit="A", decimals=1, step=0.5, minimum=0.,
            maximum=I_MOT_MAX, warn_above=I_MOT_WARN,
            default=lambda ctx: ctx.params.i_mot, param="i_mot",
            readback=lambda ctx: (None if not ctx.is_on("ttl", "inner_coil_igbt")
                                  or ctx.dac_voltage("inner_coil_supply_current") is None
                                  else slope_i_per_v_setpoint_supply_inner
                                  * ctx.dac_voltage("inner_coil_supply_current")),
            tooltip=f"Inner-coil current for the MOT. ↺ = ExptParams i_mot. Hard "
                    f"limit {I_MOT_MAX:g} A (below Cooling's 100 'default' sentinel)."),
        Arg("t_ramp", "Off ramp", unit="ms", scale=1e3, decimals=1, step=10.,
            minimum=5.e-3, maximum=10., default=50.e-3,
            tooltip="How long Off ramps the inner coil down."),
        _i_meas_arg("keysight/inner.current_a"),
    ),
    ops=(
        Op("on", "On", args=("i", "i_meas"), check=_mot_on_check,
           tooltip="load_2D_mot(0) then mot(0, i_supply=I): refused with the inner "
                   "coil's PID on, the H-bridge in Helmholtz, or the coil more than "
                   "5 A above I.",
           code=_coil_sync("expt.inner_coil") + """
if expt.inner_coil.pid_on:
    raise ValueError("inner coil PID is on")
if expt.ttl.hbridge_helmholtz.state == 1:
    raise ValueError("H-bridge is in Helmholtz")
i_now = expt.inner_coil.i_supply
if {i_meas} > i_now:
    i_now = {i_meas}
if (expt.inner_coil.igbt_ttl.state == 1 or {i_meas} >= 1.) and i_now > {i} + 5.:
    raise ValueError("inner coil above the MOT current")
expt.load_2D_mot(0.)
expt.mot(0., i_supply={i})
"""),
        Op("off", "Off", args=("t_ramp", "i_meas"),
           tooltip="3D + 2D beams and push off, 2D coil current to 0 V, then the inner "
                   "coil ramped down over the off ramp and discharged.",
           code="""
expt.switch_d2_3d(0)
expt.switch_d2_2d(0)
expt.dds.push.off()
expt.dac.supply_current_2dmot.set(v=0.)
""" + _coil_off_body("expt.inner_coil")),
        Op("beams_off", "Beams off (coil unchanged)",
           code="expt.switch_d2_3d(0)\nexpt.switch_d2_2d(0)\nexpt.dds.push.off()"),
    ),
    lamps=(
        Lamp("3D", "dds", "d2_3d_c"),
        Lamp("2D", "dds", "d2_2dh_c"),
        Lamp("push", "dds", "push"),
        Lamp("coil", "ttl", "inner_coil_igbt", "on", "off", "warn"),
    ),
    readouts=(Readout("2D current", lambda ctx: None
                      if ctx.dac_voltage("supply_current_2dmot") is None
                      else f"{ctx.dac_voltage('supply_current_2dmot'):.3f} V"),),
    state=_mot_state,
    layout=(
        Buttons(("on", "off"), main=True),
        FieldRow(("i",)),
        FieldRow(("t_ramp",)),
        Menu(("beams_off",)),
    ),
)


# --- D1 gray molasses ----------------------------------------------------------------

def _d1_detuning_readback(name):
    def get(ctx):
        f = ctx.dds_frequency(name)
        dds = getattr(getattr(ctx, "frames", None), "dds", None)
        obj = getattr(dds, name, None)
        if f is None or obj is None:
            return None
        try:
            return float(obj.frequency_to_detuning(f))
        except Exception:
            return None
    return get


def _d1_state(ctx):
    c, r = ctx.is_on("dds", "d1_3d_c"), ctx.is_on("dds", "d1_3d_r")
    if c is None or r is None:
        return Status("unknown", "")
    if c and r:
        return Status("on", "ON", "cooler and repump AOs on")
    if c or r:
        return Status("partial", "partial",
                      f"cooler {'on' if c else 'off'}, repump {'on' if r else 'off'}")
    return Status("off", "off")


def _d1_detuning_arg(name, dds, label, param):
    return Arg(name, label, unit="Γ", decimals=2, step=0.1,
               minimum=-DETUNE_D1_MAX, maximum=DETUNE_D1_MAX,
               warn_below=DETUNE_D1_WARN[0], warn_above=DETUNE_D1_WARN[1],
               default=lambda ctx: getattr(ctx.params, param, None), param=param,
               readback=_d1_detuning_readback(dds),
               tooltip=f"{dds} detuning in linewidths (set_dds_gamma). ↺ = ExptParams "
                       f"{param}.")


def _d1_vpd_arg(name, dds, label, param):
    return Arg(name, label, unit="V", decimals=3, step=0.05, minimum=0., maximum=V_DAC_MAX,
               default=lambda ctx: getattr(ctx.params, param, None),
               readback=lambda ctx: ctx.dds_v_pd(dds),
               tooltip=f"{dds} VVA (v_pd). ↺ = ExptParams {param} (derived from the "
                       f"power fraction, so it is not offered for 'adopt as default').")


D1_SET = """
expt.dds.d1_3d_c.set_dds_gamma(delta={det_c})
expt.dds.d1_3d_c.update_dac_setpoint({v_c})
delay(8.e-9)
expt.dds.d1_3d_r.set_dds_gamma(delta={det_r})
expt.dds.d1_3d_r.update_dac_setpoint({v_r})
"""

D1_GM = CompositeDevice(
    key="d1_gm",
    title="D1 gray molasses",
    group="Cooling",
    doc=("The D1 3D beams used by Cooling.gm: d1_3d_c (cooler) and d1_3d_r (repump), "
         "each a DDS with a VVA (vva_d1_3d_c/r).  On sets both and switches them on; "
         "the D2 beams, shims and coils are not touched."),
    fields=(
        _d1_detuning_arg("det_c", "d1_3d_c", "Cooler detuning", "detune_d1_c_gm"),
        _d1_detuning_arg("det_r", "d1_3d_r", "Repump detuning", "detune_d1_r_gm"),
        _d1_vpd_arg("v_c", "d1_3d_c", "Cooler VVA", "v_pd_d1_c_gm"),
        _d1_vpd_arg("v_r", "d1_3d_r", "Repump VVA", "v_pd_d1_r_gm"),
    ),
    ops=(
        Op("on", "On", args=("det_c", "det_r", "v_c", "v_r"),
           tooltip="Both AOs to their detunings, VVAs set explicitly (so DDS.on cannot "
                   "restore a stale setpoint), switch_d1_3d(1).",
           code=D1_SET + "\nexpt.switch_d1_3d(1)"),
        Op("off", "Off", code="expt.switch_d1_3d(0)", tooltip="switch_d1_3d(0)."),
        Op("set", "Set", args=("det_c", "det_r", "v_c", "v_r"), code=D1_SET,
           tooltip="Detunings and VVAs rewritten; switch state kept."),
    ),
    lamps=(Lamp("cooler", "dds", "d1_3d_c"), Lamp("repump", "dds", "d1_3d_r")),
    state=_d1_state,
    layout=(
        Buttons(("on", "off"), main=True),
        FieldRow(("det_c", "det_r"), ("set",)),
        FieldRow(("v_c", "v_r")),
    ),
)


#: The Composite tab, in display order (cards of a group are kept together).
COMPOSITE_DEVICES = (IMAGING, RAMAN, RY_405, RY_980, LIGHTSHEET, TWEEZER,
                     OUTER_COIL, INNER_COIL, SHIMS, MOT, D1_GM)


# --- scenes --------------------------------------------------------------------------

COMPOSITE_SCENES = (
    Scene(
        key="outer_field_hold",
        title="Outer coil: hold a field, then ramp down",
        doc=("Ramps the outer coil to I, holds it, and always ramps it down again -- "
             "also when a step fails or the scene is cancelled, and whether or not a "
             "GUI is still open (the server runs it)."),
        fields=(
            Arg("i", "Current", unit="A", decimals=1, step=1., minimum=0., maximum=I_OUTER_MAX,
                warn_above=I_OUTER_WARN, default=20.),
            Arg("hold", "Hold", unit="s", decimals=1, step=5., minimum=0., maximum=3600.,
                default=30.),
        ),
        steps=(Step("outer_coil.ramp_to", {"i": "{i}"}, "ramp to I"),
               Hold("{hold}", "hold")),
        finally_=(Step("outer_coil.off", {"i_meas": -1.}, "ramp down"),),
    ),
    Scene(
        key="mot_look",
        title="MOT: on for a while, then off",
        doc="MOT on with its defaults, held, then MOT off (coil ramped down).",
        fields=(Arg("hold", "Hold", unit="s", decimals=1, step=5., minimum=0.,
                    maximum=600., default=10.),),
        steps=(Step("mot.on", label="MOT on"), Hold("{hold}", "hold")),
        finally_=(Step("mot.off", {"i_meas": -1.}, "MOT off"),),
    ),
    Scene(
        key="lights_off",
        title="All probe and cooling light off",
        doc="Imaging, Raman, Rydberg 405/980, D1 and the MOT beams off. Coils untouched.",
        steps=(Step("imaging.off"), Step("raman.off"), Step("ry_405.off"),
               Step("ry_980.off"), Step("d1_gm.off"), Step("mot.beams_off")),
        leaves_on="nothing new -- it only switches light off",
    ),
)


def composite_devices():
    return COMPOSITE_DEVICES
