"""SI <-> OPX unit conversions.

Everything user-facing in this lab is SI (times in seconds, frequencies in
Hz). The OPX wants durations in 4 ns clock cycles (play/wait) or integer
nanoseconds (config pulse lengths) and frequencies as integer Hz. All
conversion happens host-side, at program-build time -- nothing here runs on
the OPX.

Generic (future waxx.control.opx): no kexp imports, no qm imports.
"""

import numpy as np

CLOCK_NS = 4          # OPX+ PPU clock cycle
MIN_PULSE_CC = 4      # shortest play/wait: 4 cycles = 16 ns

# Grid-rounding warning threshold: snapping to the 4 ns clock is inherent,
# so only rounding that moves a time by more than this fraction of the
# requested value is worth a warning (unconditional -- not verbosity-gated).
GRID_WARN_REL = 0.01

# OPX+ analog output full scale (into 50 ohm). Waveform samples beyond this
# are a config error the QOP would reject anyway; catch it with a clear
# message at build time instead.
MAX_ANALOG_V = 0.499

# QUA `fixed` is signed 4.28 fixed point: representable values are
# [-8, 8) in steps of 2^-28. A per-shot float outside that range would be
# rejected (or wrapped) by the QOP compiler far from the line that wrote it.
QUA_FIXED_LIMIT = 8.

# amp() scaling factors of a play must lie in [-2, 2).
QUA_AMP_LIMIT = 2.


def s_to_cc(t, key=''):
    """Seconds -> integer clock cycles (scalar or ndarray), rounded.

    Warns (once per call) when rounding to the 4 ns grid moves any value by
    more than GRID_WARN_REL (1%) of what was requested, and raises when a
    nonzero duration rounds below the 16 ns minimum -- silently stretching a
    pulse would misreport what the machine did.
    """
    t = np.asarray(t, dtype=float)
    ns = t * 1e9
    cc = np.rint(ns / CLOCK_NS)
    err = np.abs(ns - cc * CLOCK_NS)
    rel = np.divide(err, np.abs(ns), out=np.zeros_like(err), where=ns != 0)
    rel_max = float(np.max(rel)) if rel.size else 0.
    if rel_max > GRID_WARN_REL:
        label = f" for '{key}'" if key else ""
        print(f"[opx] WARNING: duration{label} is off the {CLOCK_NS} ns grid "
              f"by up to {float(np.max(err)):.1f} ns ({rel_max:.1%} of the "
              f"requested time); rounding to the nearest cycle.")
    bad = (cc > 0) & (cc < MIN_PULSE_CC)
    if np.any(bad):
        label = f" for '{key}'" if key else ""
        raise ValueError(
            f"[opx] duration{label} rounds to under the OPX minimum of "
            f"{MIN_PULSE_CC * CLOCK_NS} ns (got {np.min(ns[bad]):.1f} ns).")
    if cc.ndim == 0:
        return int(cc)
    return cc.astype(np.int64)


def s_to_ns(t, key=''):
    """Seconds -> integer nanoseconds (for config pulse lengths)."""
    t = np.asarray(t, dtype=float)
    ns = np.rint(t * 1e9)
    if ns.ndim == 0:
        return int(ns)
    return ns.astype(np.int64)


def hz_to_int(f):
    """Hz (float, SI) -> integer Hz for update_frequency / config IFs."""
    f = np.asarray(f, dtype=float)
    out = np.rint(f)
    if out.ndim == 0:
        return int(out)
    return out.astype(np.int64)


def demod2volts(data, t_integration_s):
    """Raw OPX integration result -> mean volts over the integration window.

    Same convention as qualang_tools.units.unit.demod2volts (dual demod /
    plain integration): volts = 4096 * raw / duration_ns. To be checked
    against the ARTIQ sampler APD path on hardware (milestone M3) before the
    absolute scale is trusted.
    """
    duration_ns = float(t_integration_s) * 1e9
    return 4096.0 * np.asarray(data) / duration_ns
