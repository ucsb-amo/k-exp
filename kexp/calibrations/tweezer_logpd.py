"""Tweezer intensity lock with a logarithmic photodiode: power <-> setpoint conversions.

Detector: Koheron PDX10R, log(A) output. Datasheet (nominal, NOT a calibration): 300 mV/decade,
100 pA intercept photocurrent, 1 kOhm output impedance, 600 kHz bandwidth above 3 uA of photocurrent
(lower below: roughly 100 kHz at tens of nA, kHz at nW), rated input 1 nW-5 mW (InGaAs) / 0.5 nW-4 mW (Si).
At 1064 nm use the InGaAs version; its responsivity at 1064 nm is not on the datasheet (1.1 A/W is at
1550 nm), so the power -> volts map below must be measured. No temperature-drift or noise specs are given.

Firmware: kexp/control/quarto/pid_tweezer_intensity_stabilize_logpd/. The log PD reads
V = LOGPD_V_AT_P_REF + LOGPD_V_PER_DECADE * log10(P / LOGPD_P_REF_W), where P is the power the
calibration's reference meter measured (say where, in the calibration comment).

Two ways to drive the setpoint (firmware "smode"):
  smode 0 -- the setpoint maps to the log-PD voltage: target = soffset + sgain * setpoint
             (power_to_log_setpoint). The calibration is versioned here and saved with the run.
  smode 1 -- the setpoint is linear in power (power_to_linear_setpoint); the firmware takes the log
             and holds its own copy of the calibration -- read it back with its "cal" command and record it.

Host-side only (numpy). Precompute ramps in prepare() and hand the kernel arrays.

To calibrate: step the tweezer power with the loop open (fixed AO control voltages), read the log PD
(Sampler, via the firmware's DAC3 monitor, so the 1 kOhm output into the Quarto input is included) and a
power meter; block the beam for the floor reading. Fit with
waxa.fitting.log_photodiode.fit_log_photodiode, cutting the floor (dark reading + margin) and the
compression region, and state what was cut. Comment out the old line, tag the new one with run id and
date, as in tweezer.py.
"""

import numpy as np

# Reference power: a definition (sets the units of LOGPD_V_AT_P_REF), not a measurement.
LOGPD_P_REF_W = 1.e-3

# NOT CALIBRATED: NaN until measured. Every conversion below raises while one it needs is NaN.
LOGPD_V_PER_DECADE = np.nan      # V/decade (nominal 0.300)
LOGPD_V_AT_P_REF = np.nan        # V at LOGPD_P_REF_W
LOGPD_V_FLOOR = np.nan           # log-PD reading with the beam blocked (V)
LOGPD_V_SAT = np.nan             # reading above which the output compresses (V); NaN = not checked

# Lowest allowed target: this many decades of power above the floor reading. At 2 decades the floor
# adds ~1 % to the photocurrent, i.e. a ~1 % error in held power.
LOGPD_FLOOR_MARGIN_DECADES = 2.
# Optional higher lowest target (V), e.g. just below the lowest power a sequence uses, so the smode-0
# setpoint map can start there. NaN = floor + margin.
LOGPD_V_SET_MIN = np.nan

# The firmware reads the PD on the Quarto's +/-2.5 V ADC range (PD_ADC_RANGE).
LOGPD_ADC_RANGE_V = 2.5
FIRMWARE_HYST_V = 0.01           # firmware "hyst"

# smode 0 setpoint map (firmware sgain / soffset): target = SETPOINT_OFFSET_V + SETPOINT_GAIN * setpoint.
# A choice, not a calibration: choose_setpoint_map() gives values; 0 V must land below vset_min (= off).
SETPOINT_GAIN = np.nan
SETPOINT_OFFSET_V = np.nan

# smode 1 only: setpoint volts per watt (a choice of scale; the full ramp should use most of 0-10 V).
LINEAR_SETPOINT_V_PER_W = np.nan

SETPOINT_MAX_V = 9.99


def _require(*names):
    g = globals()
    missing = [n for n in names if not np.isfinite(g[n])]
    if missing:
        raise ValueError(f"tweezer_logpd not calibrated: {', '.join(missing)} is NaN "
                         f"(kexp/calibrations/tweezer_logpd.py)")


def v_setpoint_min() -> float:
    """Lowest log-PD target allowed (V): floor + margin, or LOGPD_V_SET_MIN if higher. Firmware vset_min."""
    _require("LOGPD_V_FLOOR", "LOGPD_V_PER_DECADE")
    if LOGPD_V_PER_DECADE <= 0:
        # the firmware's floor switch (target >= vset_min) assumes more light = higher voltage
        raise ValueError("LOGPD_V_PER_DECADE <= 0: firmware and checks assume a rising log-PD output")
    v = LOGPD_V_FLOOR + LOGPD_FLOOR_MARGIN_DECADES * LOGPD_V_PER_DECADE
    if np.isfinite(LOGPD_V_SET_MIN):
        v = max(v, LOGPD_V_SET_MIN)
    return float(v)


def power_to_vlogpd(p_w, check=True):
    """Power (W, scalar or array) -> log-PD voltage.

    With check=True (default), raises if any requested power is <= 0, below vset_min, in the
    compression region or outside the ADC range -- the lock could not hold it as requested.
    """
    _require("LOGPD_V_PER_DECADE", "LOGPD_V_AT_P_REF")
    p = np.asarray(p_w, dtype=float)
    if np.any(~(p > 0)):
        raise ValueError("power must be > 0 W; a log setpoint has no zero -- turn the loop off with its TTL "
                         "or a 0 V setpoint")
    v = LOGPD_V_AT_P_REF + LOGPD_V_PER_DECADE * np.log10(p / LOGPD_P_REF_W)
    if check:
        _check_range(v, p)
    return v if v.ndim else float(v)


def vlogpd_to_power(v):
    """Log-PD voltage -> power (W). No range check: use it to read back what was held."""
    _require("LOGPD_V_PER_DECADE", "LOGPD_V_AT_P_REF")
    p = LOGPD_P_REF_W * 10 ** ((np.asarray(v, dtype=float) - LOGPD_V_AT_P_REF) / LOGPD_V_PER_DECADE)
    return p if p.ndim else float(p)


def power_to_log_setpoint(p_w, check=True):
    """Power (W) -> setpoint volts for smode 0. 0 W -> 0 V, which the setpoint map puts below vset_min (off)."""
    _require("SETPOINT_GAIN", "SETPOINT_OFFSET_V")
    _check_zero_is_off()
    p = np.asarray(p_w, dtype=float)
    if np.any(p < 0) or not np.all(np.isfinite(p)):
        raise ValueError("power must be finite and >= 0 W")
    s = np.zeros_like(p)
    on = p > 0
    if np.any(on):
        s[on] = (power_to_vlogpd(p[on], check=check) - SETPOINT_OFFSET_V) / SETPOINT_GAIN
    _check_setpoint(s)
    return s if s.ndim else float(s)


def power_to_linear_setpoint(p_w, check=True):
    """Power (W) -> setpoint volts for smode 1 (linear in power). 0 W -> 0 V = off.

    With check=True, every nonzero power must also pass power_to_vlogpd's range check, since that is
    the target the firmware will compute from it.
    """
    _require("LINEAR_SETPOINT_V_PER_W")
    p = np.asarray(p_w, dtype=float)
    if np.any(p < 0) or not np.all(np.isfinite(p)):
        raise ValueError("power must be finite and >= 0 W")
    if check and np.any(p > 0):
        power_to_vlogpd(p[p > 0], check=True)
    s = p * LINEAR_SETPOINT_V_PER_W
    _check_setpoint(s)
    return s if s.ndim else float(s)


def choose_setpoint_map(p_max_w, s_max=9.5):
    """smode 0: (sgain, soffset) putting 0 V just below vset_min (off) and p_max_w at s_max volts.

    Raise LOGPD_V_SET_MIN toward the lowest power you use to get finer steps; the ratio of the target
    window to the DAC span sets the setpoint resolution.
    """
    soffset = v_setpoint_min() - 2 * FIRMWARE_HYST_V
    sgain = (power_to_vlogpd(p_max_w) - soffset) / s_max
    return float(sgain), float(soffset)


def firmware_constants(smode=0) -> dict:
    """Values to load into the Quarto (serial "key value") for the given smode; compare with its "cal"."""
    _require("LOGPD_V_PER_DECADE", "LOGPD_V_AT_P_REF", "LOGPD_V_FLOOR")
    c = {"smode": int(smode), "klog": LOGPD_V_PER_DECADE, "vref": LOGPD_V_AT_P_REF,
         "vset_min": v_setpoint_min(), "hyst": FIRMWARE_HYST_V,
         "vsat": LOGPD_V_SAT if np.isfinite(LOGPD_V_SAT) else float("nan")}
    if smode == 0:
        _require("SETPOINT_GAIN", "SETPOINT_OFFSET_V")
        _check_zero_is_off()
        c["sgain"] = SETPOINT_GAIN
        c["soffset"] = SETPOINT_OFFSET_V
    elif smode == 1:
        _require("LINEAR_SETPOINT_V_PER_W")
        c["sref"] = LINEAR_SETPOINT_V_PER_W * LOGPD_P_REF_W
    else:
        raise ValueError(f"smode must be 0 or 1, not {smode}")
    return c


def _check_zero_is_off():
    if not SETPOINT_OFFSET_V < v_setpoint_min() - FIRMWARE_HYST_V:
        raise ValueError(f"SETPOINT_OFFSET_V = {SETPOINT_OFFSET_V:.4g} V is not below vset_min - hyst "
                         f"({v_setpoint_min() - FIRMWARE_HYST_V:.4g} V): a 0 V setpoint would turn the "
                         f"tweezer ON at low power instead of off")
    if not SETPOINT_GAIN > 0:
        raise ValueError("SETPOINT_GAIN must be > 0")


def _check_setpoint(s):
    if np.any(s > SETPOINT_MAX_V) or np.any(s < 0):
        raise ValueError(f"setpoint outside 0-{SETPOINT_MAX_V} V (range {np.min(s):.4g} to {np.max(s):.4g} V)")


def _check_range(v, p):
    vmin = v_setpoint_min()
    low = v < vmin
    if np.any(low):
        raise ValueError(f"{int(low.sum())} setpoint(s) below vset_min: lowest "
                         f"{np.min(p[low] if p.ndim else p):.4g} W -> {np.min(v):.4g} V < {vmin:.4g} V")
    high = v >= LOGPD_ADC_RANGE_V
    if np.isfinite(LOGPD_V_SAT):
        high |= v >= LOGPD_V_SAT
    if np.any(high):
        lim = min(LOGPD_ADC_RANGE_V, LOGPD_V_SAT) if np.isfinite(LOGPD_V_SAT) else LOGPD_ADC_RANGE_V
        raise ValueError(f"{int(np.sum(high))} setpoint(s) in the compression region or above the ADC range: "
                         f"{np.max(v):.4g} V >= {lim:.4g} V")
