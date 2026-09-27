"""Rabi-posterior calibration analysis: every estimator on one run, one verdict.

    python -m kexp.analysis.rabi_posterior_cli RUN_ID [RUN_ID ...] [--out DIR] [options]

For each pulse-train run (rabi_posterior_pulse_train or apd_joint_calibration)
this runs, on the SAME data:

  1. data checks        -- shots excluded (never taken / non-finite, counted and
                           named), pulse-schedule design, cycle timing
                           (period - drawn pulse must be constant), APD signal
                           above the dark level (stage in?), readout polarity
                           (model-free first-pulse regression).
  2. RabiPosterior      -- f_rabi only, every APD and Bloch constant FIXED at
                           the run's params (or --cal overrides). Wide grid,
                           then a zoom. Goodness-of-fit gate
                           (GOF_EXCESS_NOISE_LIMIT). This is the estimator the
                           live feedback loop resembles, so its GOF says whether
                           the stored calibration describes the machine.
  3. RabiJointPosterior -- f_rabi, midpoint, light shift and back-action
                           coherence gridded, APD endpoints and noise
                           marginalized. Two stages: a wide locator, then a zoom
                           around it; the wide stage's mass outside the zoom
                           window is reported. Model adequacy from its own
                           residuals (rms vs assumed sigma, variance explained,
                           per-pulse structure, within-shot correlation).
  4. pinned variant     -- f_rabi pinned (default 1/(2 t_raman_pi_pulse) from
                           the run's params), light shift and coherence fitted
                           (the lightshift_coherence_posterior notebook). Slopes
                           per 1% of the pin and the pin's pull against step 3.
  5. block consistency  -- the shots split into K time-ordered blocks (by
                           acquisition order), f_rabi fitted per block with the
                           nuisances pinned at step 3 and the APD endpoints
                           re-marginalized per block; chi^2 of the block means.
                           Drift inside the run shows up here.
  6. systematics        -- turn-on delay and residual detuning rows of
                           RabiPosterior.systematic_budget on the step-3 fitted
                           calibration (those two are NOT marginalized by step 3).

and then evaluates the gates fixed in advance in
C:\\lab\\skynet_log\\outputs\\2026-09-27_rabi_posterior_plan\\PLAN.md (constants
GATE_* below). Three separate verdicts, because they license different things:

  t_pi       may t_raman_pi_pulse be written back from this run?
  nuisances  may frequency_lightshift / back_action_coherence be written back?
  fixed_cal  does the STORED calibration describe the run (RabiPosterior GOF and
             agreement with the joint fit)? A FAIL here is a finding about the
             APD calibration, not about the Rabi frequency.

Nothing is written back. Proposed lines are printed and saved only when the
relevant verdict passes, and they are proposals.

Outputs (per invocation, in --out): results.json (every number, the gates, the
exclusions, the calibration provenance, the command line) and, unless
--no-figures, PNG figures per run. Writes only inside C:\\lab\\skynet_log\\outputs.

Data are loaded read-only with atomdata(run_id, roi_id='auto', lite=False,
ignore_images=True). No other access to the run files.

Regression (2026-09-27, against numbers documented in memory notes / notebooks):
see PLAN.md section 6.
"""

import argparse
import copy
import datetime as _dt
import json
import math
import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from kexp.analysis.rabi_posterior import (
    DEFAULT_F_RABI_MAX,
    DEFAULT_F_RABI_MIN,
    DEFAULT_N_GRID,
    GOF_EXCESS_NOISE_LIMIT,
    JOINT_AXES,
    RabiCalibration,
    RabiJointPosterior,
    RabiPosterior,
    evolve_pulse_train,
    expected_photon_fraction,
)

__all__ = [
    "RunData", "AnalysisOptions", "load_run", "run_data_from_arrays",
    "analyze_run", "combine_runs", "main", "GATES",
]

DEFAULT_OUT_ROOT = Path(r"C:\lab\skynet_log\outputs\2026-09-27_rabi_posterior_plan")

# ---------------------------------------------------------------------------
# Pre-registered gates (PLAN.md section 5). Change them only by editing the
# plan first and saying so -- never to make a run pass.
# ---------------------------------------------------------------------------
GATE_GOF_LIMIT = GOF_EXCESS_NOISE_LIMIT      # RabiPosterior residual / assumed sigma
GATE_JOINT_EXCESS_LIMIT = 1.5                # joint residual rms / assumed sigma_v
GATE_R2_WARN = 0.3                           # variance explained by the joint model
GATE_WINDOW_MASS_FAIL = 0.95                 # stage-1 f mass inside the stage-2 window
GATE_WINDOW_MASS_WARN = 0.99
GATE_RP_VS_JOINT_PASS = 1.0                  # |f_RP - f_joint| / sigma_joint
GATE_RP_VS_JOINT_FAIL = 2.0
GATE_REF_PULL = 2.0                          # |f_joint - f_ref| / combined sigma
GATE_PIN_PULL = 2.0                          # |f_joint - f_pin| / sigma_joint
GATE_BLOCK_P = 0.01                          # chi^2 p-value of the block means
GATE_TIMING_NS = 5.0                         # spread of (period - drawn pulse)
GATE_SIGNAL_SIGMA = 5.0                      # APD reads vs dark level, in dark sd
GATE_LOOSE_FRAC = 0.10                       # nuisance relative width to propose it
GATE_MIN_SHOTS = 5

GATES = {k: v for k, v in globals().items() if k.startswith("GATE_")}

IMAGING_NAMES = {0: "ABSORPTION", 1: "DISPERSIVE", 2: "FLUORESCENCE", 3: "POLMOD"}

PASS, WARN, FAIL, NA = "PASS", "WARN", "FAIL", "N/A"


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

@dataclass
class RunData:
    """One run's pulse-train record, already stripped of unusable shots."""
    run_id: object
    apd: np.ndarray                     # (n_shot, n_pulse) volts
    t_eff: np.ndarray                   # (n_shot, n_pulse) programmed durations, s
    cal: RabiCalibration                # from the run's params (+ overrides)
    acq_order: np.ndarray               # row indices in acquisition order
    acq_order_source: str = "sequential (assumed)"
    t_rec: np.ndarray = None            # (n_shot, n_pulse) pulse start times, s
    apd_reference: np.ndarray = None    # (n_shot, 2) [light leak, dark]
    meta: dict = field(default_factory=dict)
    excluded: list = field(default_factory=list)   # [{'rows': [...], 'reason': str}]
    ad: object = None                   # the atomdata, when loaded from disk

    @property
    def n_shot(self):
        return self.apd.shape[0]

    @property
    def n_pulse(self):
        return self.apd.shape[1]


def _scalar(v):
    a = np.ravel(np.asarray(v))
    if a.size == 0:
        return None
    x = a[0]
    if isinstance(x, bytes):
        return x.decode(errors="replace")
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    return x


def _default_loader(run_id):
    from waxa import atomdata
    # Read-only: lite=False (lite=True can write _lite copies), roi_id='auto'
    # (no dialog), images skipped (pulse-train runs take none).
    return atomdata(int(run_id), roi_id='auto', lite=False, ignore_images=True)


def _acquisition_order(ad, n_rows):
    """Row indices in the order the shots were taken, and where that came from."""
    ri = getattr(ad, "run_info", None)
    so = getattr(ri, "shot_order", None) if ri is not None else None
    if so is not None:
        so = np.asarray(so, dtype=int).ravel()
        if so.size == n_rows and np.array_equal(np.sort(so), np.arange(n_rows)):
            return so, "run_info.shot_order"
    si = getattr(ad, "sort_idx", None)
    if si is None:
        return np.arange(n_rows), "sequential (assumed: no shot_order / sort_idx in file)"
    try:
        si = np.asarray(si, dtype=object)
        if si.size:
            cand = np.asarray(si[0] if si.dtype == object else si, dtype=int).ravel()
            if cand.size == n_rows and np.array_equal(np.sort(cand), np.arange(n_rows)):
                return cand, "data/sort_idx (legacy shuffle)"
    except Exception:
        pass
    return np.arange(n_rows), "sequential (assumed: no shot_order / sort_idx in file)"


def run_data_from_arrays(run_id, apd, t_eff, cal, *, t_rec=None, apd_reference=None,
                         acq_order=None, meta=None, completed=None, ad=None,
                         acq_order_source=None):
    """Build RunData from arrays, dropping unusable rows and recording why.

    completed: optional (n_shot,) bool -- False rows were never taken.
    """
    apd = np.asarray(apd, dtype=float)
    apd = apd[None, :] if apd.ndim == 1 else apd.reshape(-1, apd.shape[-1])
    n_rows, n_pulse = apd.shape
    t_eff = np.asarray(t_eff, dtype=float)
    if t_eff.ndim == 0:
        t_eff = np.full(apd.shape, float(t_eff))
    elif t_eff.ndim == 1 and t_eff.size == n_pulse:
        t_eff = np.tile(t_eff, (n_rows, 1))
    else:
        t_eff = t_eff.reshape(-1, t_eff.shape[-1])
    if t_eff.shape != apd.shape:
        raise ValueError(f"t_eff shape {t_eff.shape} does not match apd {apd.shape}")

    keep = np.ones(n_rows, dtype=bool)
    excluded = []
    if completed is not None:
        completed = np.asarray(completed, dtype=bool).ravel()
        if completed.size == n_rows and not completed.all():
            rows = np.where(~completed)[0]
            excluded.append({"rows": rows.tolist(), "reason": "never taken (run incomplete)"})
            keep &= completed
    bad_v = ~np.all(np.isfinite(apd), axis=1)
    if np.any(bad_v & keep):
        rows = np.where(bad_v & keep)[0]
        excluded.append({"rows": rows.tolist(), "reason": "non-finite APD value"})
        keep &= ~bad_v
    bad_t = ~np.all(np.isfinite(t_eff) & (t_eff > 0), axis=1)
    if np.any(bad_t & keep):
        rows = np.where(bad_t & keep)[0]
        excluded.append({"rows": rows.tolist(),
                         "reason": "pulse durations missing/non-positive (container unwritten)"})
        keep &= ~bad_t

    old_to_new = -np.ones(n_rows, dtype=int)
    old_to_new[keep] = np.arange(int(keep.sum()))
    if acq_order is None:
        acq_order = np.arange(n_rows)
        acq_order_source = acq_order_source or "sequential (assumed)"
    acq = old_to_new[np.asarray(acq_order, dtype=int)]
    acq = acq[acq >= 0]

    def _rows(x):
        """Per-shot container -> (n_kept, k), or None if it does not line up."""
        if x is None:
            return None
        x = np.asarray(x, dtype=float)
        if x.size == 0 or x.size % n_rows:
            return None
        return x.reshape(n_rows, -1)[keep]

    return RunData(run_id=run_id, apd=apd[keep], t_eff=t_eff[keep], cal=cal,
                   acq_order=acq, acq_order_source=acq_order_source or "given",
                   t_rec=_rows(t_rec), apd_reference=_rows(apd_reference),
                   meta=dict(meta or {}), excluded=excluded, ad=ad)


def load_run(run_id, loader=None, cal_overrides=None):
    """Load one run read-only and return RunData (unusable shots dropped, logged)."""
    ad = (loader or _default_loader)(run_id)
    apd = np.asarray(ad.data.apd, dtype=float)
    n_pulse = apd.shape[-1]
    apd = apd.reshape(-1, n_pulse)
    n_rows = apd.shape[0]

    t_src = "ad.data.t_raman_pulse"
    t_eff = getattr(ad.data, "t_raman_pulse", None)
    t_arr = None if t_eff is None else np.asarray(t_eff, dtype=float)
    if t_arr is None or not (t_arr.size and np.any(t_arr > 0)):
        t_src = "ad.p.t_raman_pulse (no usable per-shot container)"
        t_arr = np.asarray(getattr(ad.p, "t_raman_pulse"), dtype=float)
    if t_arr.ndim >= 1 and t_arr.size == n_rows * n_pulse:
        t_arr = t_arr.reshape(n_rows, n_pulse)
    elif t_arr.ndim == 1 and t_arr.size == n_rows and n_rows != n_pulse:
        # a scanned scalar duration (one per shot), same for every pulse
        t_arr = np.repeat(t_arr[:, None], n_pulse, axis=1)

    cal = RabiCalibration.from_params(ad.p, **(cal_overrides or {}))

    completed = None
    ri = ad.run_info
    n_done = getattr(ri, "n_shots_completed", None)
    so = getattr(ri, "shot_order", None)
    acq, acq_src = _acquisition_order(ad, n_rows)
    if n_done is not None:
        n_done = int(_scalar(n_done))
        if n_done < n_rows:
            completed = np.zeros(n_rows, dtype=bool)
            completed[acq[:n_done]] = True

    meta = {
        "expt_class": _scalar(getattr(ri, "expt_class", None)),
        "experiment_filepath": _scalar(getattr(ri, "experiment_filepath", None)),
        "run_datetime_str": _scalar(getattr(ri, "run_datetime_str", None)),
        "imaging_type": IMAGING_NAMES.get(_scalar(getattr(ri, "imaging_type", -1)), "?"),
        "data_complete": _scalar(getattr(ri, "data_complete", None)),
        "incomplete_reason": _scalar(getattr(ri, "incomplete_reason", None)),
        "n_shots_completed": n_done,
        "n_rows_in_file": n_rows,
        "t_raman_pulse_source": t_src,
        "camera_key": _scalar(getattr(getattr(ad, "camera_params", None), "key", None)),
        "xvarnames": [str(x) for x in getattr(ad, "xvarnames", [])],
    }
    for name in ("N_pulses", "N_repeats", "t_raman_pi_pulse", "t_img_pulse", "amp_imaging",
                 "t_raman_pulse_seed", "t_raman_pulse_random_bool",
                 "t_raman_pulse_min_frac_pi", "t_raman_pulse_max_frac_pi",
                 "t_raman_pulse_block_bool", "t_pulse_gap", "t_apd_slack",
                 "frequency_raman_transition", "fraction_power_raman", "phase_slm_mask",
                 "frequency_detuned_hf_midpoint", "t_tweezer_hold"):
        v = getattr(ad.p, name, None)
        if v is not None:
            a = np.ravel(np.asarray(v, dtype=float))
            meta[f"p.{name}"] = float(a[0]) if a.size == 1 else a.tolist()[:50]

    return run_data_from_arrays(
        _scalar(ri.run_id), apd, t_arr, cal,
        t_rec=getattr(ad.data, "t", None),
        apd_reference=getattr(ad.data, "apd_reference", None),
        acq_order=acq, acq_order_source=acq_src, meta=meta,
        completed=completed, ad=ad)


# ---------------------------------------------------------------------------
# options
# ---------------------------------------------------------------------------

@dataclass
class AnalysisOptions:
    rp_grid: tuple = None                # (lo, hi, n) explicit -> single stage
    # 0.25 kHz steps: a 100-shot scanned run has a ~0.1-0.2 kHz wide peak,
    # and a wide grid coarser than that can step over it.
    rp_wide: tuple = (DEFAULT_F_RABI_MIN, DEFAULT_F_RABI_MAX, 2 * DEFAULT_N_GRID - 1)
    rp_zoom_n: int = 601
    joint_f: tuple = None                # explicit (lo, hi, n) -> single stage
    joint_wide: tuple = (DEFAULT_F_RABI_MIN, DEFAULT_F_RABI_MAX, 2 * DEFAULT_N_GRID - 1)
    joint_wide_nuis: dict = field(default_factory=lambda: {
        "midpoint": (0.25, 0.75, 11), "lightshift": "alias", "lightshift_n": 21,
        "coherence": (0.05, 1.0, 20)})
    joint_zoom_n: int = 121
    midpoint: object = (0.25, 0.75, 21)  # tuple, float (pin) or None (pin at cal)
    lightshift: object = "alias"         # "alias" -> (0, 1/(2 t_img), lightshift_n)
    lightshift_n: int = 41
    coherence: object = (0.05, 1.0, 39)
    v_range_sign: object = "calibration"
    pin_f: object = "auto"               # "auto" | "none" | Hz
    pin_lightshift_n: int = 101
    pin_coherence: tuple = (0.05, 1.0, 77)
    pin_midpoint: object = None          # None -> pinned at the run's calibration
    pin_slope_frac: float = 0.01
    ref_t_pi: float = None               # override reference pi time, s
    ref_frac_unc: float = 0.03           # fractional 1-sigma of the reference f_rabi
    blocks: int = 5
    block_f_n: int = 121
    detuning_hz: float = 500.0
    delay_frac: float = 0.25
    # turn-on delay profile (ns); the APD-mapping analysis of 83148-83150
    # preferred ~0.8 us over the 127 ns in the params (delta chi2 = 21)
    delay_profile_ns: tuple = (0., 64., 127., 200., 300., 400., 500., 600., 700., 800.,
                               900., 1000., 1200.)
    delay_profile_f_n: int = 1201
    refit_at_profiled_delay: bool = True
    skip_systematics: bool = False
    skip_pinned: bool = False
    figures: bool = True


def _quick_options():
    """Coarse grids for tests and a fast first look. Not for quoted numbers."""
    return AnalysisOptions(
        rp_wide=(DEFAULT_F_RABI_MIN, DEFAULT_F_RABI_MAX, 191), rp_zoom_n=201,
        joint_wide=(DEFAULT_F_RABI_MIN, DEFAULT_F_RABI_MAX, 191),
        joint_wide_nuis={"midpoint": (0.25, 0.75, 5), "lightshift": "alias",
                         "lightshift_n": 9, "coherence": (0.05, 1.0, 8)},
        joint_zoom_n=61, midpoint=(0.25, 0.75, 9), lightshift_n=17,
        coherence=(0.05, 1.0, 16), pin_lightshift_n=33, pin_coherence=(0.05, 1.0, 25),
        blocks=3, block_f_n=61, figures=False,
        delay_profile_ns=(0., 127., 400., 800.), delay_profile_f_n=301,
        refit_at_profiled_delay=False)


def _axis_spec(spec, n_alias, t_img):
    if isinstance(spec, str) and spec == "alias":
        return (0.0, 0.5 / t_img, int(n_alias))
    return spec


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _gate(status, value=None, criterion="", note=""):
    return {"status": status, "value": value, "criterion": criterion, "note": note}


def _design(t_eff):
    """Classify the pulse schedule."""
    keys = np.rint(t_eff / 1e-12).astype(np.int64)
    n_distinct = int(np.unique(keys, axis=0).shape[0])
    const_rows = bool(np.all(np.ptp(t_eff, axis=1) < 1e-12))
    n = t_eff.shape[0]
    if const_rows and n_distinct > 1:
        kind = "scanned constant-duration (apd_joint_calibration-like)"
    elif const_rows:
        kind = "single constant duration (aliases: per-shot f unidentifiable)"
    elif n_distinct == 1:
        kind = "randomized, one pinned schedule shared by every shot"
    elif n_distinct == n:
        kind = "randomized, fresh schedule per shot"
    else:
        kind = "randomized, some schedules repeated"
    return {"kind": kind, "n_distinct_schedules": n_distinct,
            "constant_within_shot": const_rows,
            "t_min_us": float(t_eff.min() * 1e6), "t_max_us": float(t_eff.max() * 1e6)}


def _timing(rd):
    if rd.t_rec is None or rd.t_rec.shape != rd.t_eff.shape or rd.n_pulse < 2:
        return _gate(NA, note="no data.t container"), None
    dt = np.diff(rd.t_rec, axis=1)
    over = dt - rd.t_eff[:, :-1]
    spread_ns = float(over.std() * 1e9)
    info = {"period_minus_pulse_us": float(over.mean() * 1e6), "spread_ns": spread_ns}
    st = PASS if spread_ns <= GATE_TIMING_NS else FAIL
    return _gate(st, spread_ns, f"spread of (period - drawn pulse) <= {GATE_TIMING_NS} ns",
                 "a spread means the RTIO timeline stalled; the fixed-t_img model breaks"), info


def _signal(rd):
    """Are the APD reads distinguishable from the detector dark level?"""
    if rd.apd_reference is None or rd.apd_reference.shape[1] < 2:
        return _gate(NA, note="no apd_reference container"), None
    dark = rd.apd_reference[:, 1]
    leak = rd.apd_reference[:, 0]
    sd = float(np.std(dark, ddof=1)) if dark.size > 1 else float("nan")
    sd = sd if (np.isfinite(sd) and sd > 0) else 1e-4
    sep = float((np.median(rd.apd) - np.median(dark)) / sd)
    info = {"median_apd_V": float(np.median(rd.apd)), "median_dark_V": float(np.median(dark)),
            "median_light_leak_V": float(np.median(leak)), "dark_sd_V": sd,
            "apd_ptp_V": float(np.ptp(rd.apd)), "separation_in_dark_sd": sep}
    st = PASS if abs(sep) >= GATE_SIGNAL_SIGMA else FAIL
    return _gate(st, sep, f"|median(apd) - median(dark)| >= {GATE_SIGNAL_SIGMA} dark sd",
                 "reads at the dark level mean no light on the APD: pickoff stage OUT, "
                 "imaging off, or shutter closed"), info


def _polarity(jp):
    pol = jp.polarity_check()
    out = {k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in pol.items()}
    if pol["agree"] is None:
        return _gate(WARN, None, "first-pulse slope sign == calibration sign", pol["note"]), out
    st = PASS if pol["agree"] else FAIL
    return _gate(st, pol["slope"], "first-pulse slope sign == calibration sign",
                 "an inverted readout (e.g. flat SLM mask) makes every fixed-calibration "
                 "number meaningless"), out


def _shot_scatter(res):
    f = res.f_rabi_grid
    w = res.posterior_shot
    maps = f[np.argmax(w, axis=1)]
    mu = (w * f).sum(axis=1)
    sd = np.sqrt(np.maximum((w * f * f).sum(axis=1) - mu ** 2, 0.0))
    if maps.size < 2:
        return None
    scatter = float(maps.std(ddof=1))
    expected = float(np.sqrt(np.mean(sd ** 2)))
    return {"per_shot_map_scatter_hz": scatter, "expected_hz": expected,
            "ratio": scatter / expected if expected > 0 else float("inf")}


def _stats(st):
    return {k: (float(st[k]) if k in ("mean", "std", "map") else
                [float(x) for x in st[k]] if k in ("ci68", "ci95") else st[k])
            for k in ("mean", "std", "map", "ci68", "ci95", "pinned")}


def _model_voltage(t_eff, f, cal):
    s_z, _ = evolve_pulse_train(t_eff - cal.t_turn_on_delay, t_eff, np.array([f]), cal)
    g = expected_photon_fraction(s_z[:, :, 0], cal.feedback_measurement_midpoint_fraction,
                                 cal.feedback_measurement_midpoint_remap_enabled)
    return cal.v_apd_all_down + (cal.v_apd_all_up - cal.v_apd_all_down) * g


def _adequacy(apd, v_model, sigma_v):
    r = apd - v_model
    rms = float(np.sqrt(np.mean(r * r)))
    raw = float(np.std(apd))
    n_s, n_p = r.shape
    var = float(np.mean(r * r))
    rho = float("nan")
    if n_p > 1 and var > 0:
        tot = r.sum(axis=1)
        num = float(np.sum(tot * tot - np.sum(r * r, axis=1)))
        rho = num / (n_s * n_p * (n_p - 1) * var)
    col_mean = r.mean(axis=0)
    col_se = r.std(axis=0, ddof=1) / np.sqrt(n_s) if n_s > 1 else np.full(n_p, np.nan)
    z = col_mean / np.where(col_se > 0, col_se, np.nan)
    return {"resid_rms_mV": rms * 1e3, "raw_sd_mV": raw * 1e3,
            "sigma_v_assumed_mV": float(sigma_v) * 1e3,
            "excess": rms / sigma_v if sigma_v > 0 else float("inf"),
            "r2": 1.0 - (rms * rms) / (raw * raw) if raw > 0 else float("nan"),
            "within_shot_resid_corr": rho,
            "design_effect": 1.0 + (n_p - 1) * max(rho, 0.0) if np.isfinite(rho) else float("nan"),
            "per_pulse_mean_resid_mV": (col_mean * 1e3).tolist(),
            "per_pulse_resid_z": [float(x) for x in z],
            "max_abs_per_pulse_z": float(np.nanmax(np.abs(z))) if np.any(np.isfinite(z)) else float("nan")}


def _count_modes(marg, min_mass=0.05):
    """Separated modes of a 1-D marginal holding >= min_mass each.

    A mode is a maximal run of grid points above 5% of the peak; runs separated
    by a dip below that level count separately.
    """
    marg = np.asarray(marg, dtype=float)
    if marg.size < 3 or marg.max() <= 0:
        return 1
    above = marg > 0.05 * marg.max()
    n, i = 0, 0
    while i < marg.size:
        if above[i]:
            j = i
            while j < marg.size and above[j]:
                j += 1
            if marg[i:j].sum() >= min_mass:
                n += 1
            i = j
        else:
            i += 1
    return max(n, 1)


def _sigma_v(cal):
    return abs(cal.std_n_photons_per_shot * cal.v_range / cal.n_photons_per_shot)


# ---------------------------------------------------------------------------
# the estimators
# ---------------------------------------------------------------------------

def _fixed(rd, cal, opt):
    """RabiPosterior at the fixed calibration: wide + zoom (or one explicit grid)."""
    out = {}
    kw = dict(apd=rd.apd, t_raman_pulse=rd.t_eff, calibration=copy.deepcopy(cal))
    if opt.rp_grid is not None:
        lo, hi, n = opt.rp_grid
        rp = RabiPosterior(rd.ad, f_rabi_min=lo, f_rabi_max=hi, n_grid=int(n), **kw)
        res = rp.run()
        out["grid"] = [lo, hi, int(n)]
        out["stage"] = "explicit grid"
    else:
        lo, hi, n = opt.rp_wide
        rp_w = RabiPosterior(rd.ad, f_rabi_min=lo, f_rabi_max=hi, n_grid=int(n), **kw)
        wide = rp_w.run()
        out["wide"] = {"grid": [lo, hi, int(n)], "f_map": wide.f_map, "f_mean": wide.f_mean,
                       "f_std": wide.f_std, "ci95": list(wide.ci95),
                       "excess_noise_factor": wide.metadata["excess_noise_factor"]}
        win = _zoom_window(wide.f_map, wide.f_std, wide.ci95, (lo, hi), (hi - lo) / (n - 1))
        if win is None:
            rp, res = rp_w, wide
            out["grid"] = [lo, hi, int(n)]
            out["stage"] = "wide only (posterior not localized; no zoom)"
            out["localized"] = False
        else:
            zlo, zhi, zn = win
            zn = max(int(opt.rp_zoom_n), zn)
            rp = RabiPosterior(rd.ad, f_rabi_min=zlo, f_rabi_max=zhi, n_grid=zn,
                               **dict(kw, calibration=copy.deepcopy(cal)))
            res = rp.run()
            inside = (wide.f_rabi_grid >= zlo) & (wide.f_rabi_grid <= zhi)
            out["wide"]["mass_in_zoom_window"] = float(wide.posterior_joint[inside].sum())
            out["grid"] = [zlo, zhi, zn]
            out["stage"] = "wide + zoom"
            out["localized"] = True
    md = res.metadata
    out.update({
        "f_map": res.f_map, "f_mean": res.f_mean, "f_std": res.f_std,
        "ci68": list(res.ci68), "ci95": list(res.ci95), "t_pi_map": res.t_pi_map,
        "excess_noise_factor": md["excess_noise_factor"],
        "resid_rms_photons": md["resid_rms_photons"],
        "sigma_assumed_photons": md["sigma_assumed_photons"],
        "gof_warning": md.get("gof_warning"), "boundary_warning": md.get("boundary_warning"),
        "per_shot": _shot_scatter(res),
    })
    return rp, res, out


def _joint_kwargs(rd, cal, opt, v_sign):
    return dict(apd=rd.apd, t_raman_pulse=rd.t_eff, calibration=copy.deepcopy(cal),
                v_range_sign=v_sign)


def _zoom_window(f_map, f_std, ci95, span, step_wide):
    """Zoom window around a localized wide-stage posterior, or None if it is not.

    Localized means the 95% interval is narrower than LOCALIZED_FRAC of the MAP.
    A posterior that is not localized over the wide window (aliases, or data too
    weak to pick one) is reported as it is -- zooming on one of its modes would
    manufacture a precision the data do not have.
    """
    lo_w, hi_w = span
    if not (np.isfinite(f_map) and f_map > 0):
        return None
    if (ci95[1] - ci95[0]) > LOCALIZED_FRAC * f_map:
        return None
    pad = max(4.0 * f_std, 1.5e3, 4.0 * step_wide)
    lo = max(min(ci95[0], f_map) - pad, lo_w, 1.0e3)
    hi = min(max(ci95[1], f_map) + pad, hi_w)
    # never coarser than the wide stage, and at least ~6 points per sigma
    step = min(step_wide, max(f_std / 6.0, 5.0))
    n = int(min(801, max(61, math.ceil((hi - lo) / step) + 1)))
    return lo, hi, n


LOCALIZED_FRAC = 0.20


def _joint(rd, cal, opt):
    """RabiJointPosterior, two stages unless an explicit f grid is given."""
    t_img = cal.t_img_pulse
    out = {"localized": None}
    rw = None
    if opt.joint_f is not None:
        f_spec = tuple(opt.joint_f)
        out["stage"] = "explicit grid"
    else:
        nw = opt.joint_wide_nuis
        lo, hi, n = opt.joint_wide
        jw = RabiJointPosterior(
            rd.ad, f_rabi_grid=(lo, hi, int(n)),
            midpoint_grid=nw["midpoint"],
            lightshift_grid=_axis_spec(nw["lightshift"], nw["lightshift_n"], t_img),
            coherence_grid=nw["coherence"], **_joint_kwargs(rd, cal, opt, opt.v_range_sign))
        rw = jw.run()
        stw = rw.axis_stats["f_rabi"]
        out["wide"] = {"grid": [lo, hi, int(n)], "f": _stats(stw),
                       "nuisance_grids": {k: (list(v) if isinstance(v, tuple) else v)
                                          for k, v in nw.items()}}
        win = _zoom_window(stw["map"], stw["std"], stw["ci95"], (lo, hi), (hi - lo) / (n - 1))
        if win is None:
            out["localized"] = False
            out["stage"] = "wide only (f not localized: 95% CI wider than " \
                           f"{100*LOCALIZED_FRAC:.0f}% of the MAP; no zoom)"
            f_spec = (lo, hi, int(n))
        else:
            out["localized"] = True
            f_spec = (win[0], win[1], max(int(opt.joint_zoom_n), win[2]))
            g = rw.grids["f_rabi"]
            inside = (g >= f_spec[0]) & (g <= f_spec[1])
            out["wide"]["mass_in_zoom_window"] = float(stw["marginal"][inside].sum())
            out["stage"] = "wide + zoom"
    jp = RabiJointPosterior(
        rd.ad, f_rabi_grid=f_spec, midpoint_grid=opt.midpoint,
        lightshift_grid=_axis_spec(opt.lightshift, opt.lightshift_n, t_img),
        coherence_grid=opt.coherence, **_joint_kwargs(rd, cal, opt, opt.v_range_sign))
    res = jp.run()
    out["n_modes"] = _count_modes(res.axis_stats["f_rabi"]["marginal"])
    out["grid_f"] = list(f_spec)
    out["axes"] = {name: _stats(res.axis_stats[name]) for name in JOINT_AXES}
    out["v_down"], out["v_up"], out["v_range"] = (list(res.v_down), list(res.v_up),
                                                   list(res.v_range))
    out["boundary_warnings"] = list(res.metadata.get("boundary_warnings", []))
    out["polarity_warning"] = res.metadata.get("polarity_warning")
    out["design_warning"] = res.metadata.get("design_warning")
    out["v_range_sign_constraint"] = res.metadata.get("v_range_sign_constraint")
    f_mean = res.axis_stats["f_rabi"]["mean"]
    cal_fit = res.fitted_calibration()
    # Adequacy is judged at the MAP cell (every outer axis at its joint MAP,
    # endpoints conditional on that cell): posterior means of a multimodal
    # posterior are not a model of anything. For a localized posterior the
    # two agree, and the posterior-mean version is kept for comparison.
    best = res.best()
    out["map_cell"] = best
    cal_map = replace(cal, feedback_measurement_midpoint_fraction=best["midpoint_fraction"],
                      frequency_lightshift=best["frequency_lightshift"],
                      back_action_coherence=best["back_action_coherence"],
                      v_apd_all_down=best["v_apd_all_down"], v_apd_all_up=best["v_apd_all_up"])
    v_model = _model_voltage(jp.t_eff, best["f_rabi"], cal_map)
    out["adequacy"] = _adequacy(jp.apd, v_model, jp.sigma_v)
    out["adequacy_at_means"] = {k: v for k, v in _adequacy(
        jp.apd, _model_voltage(jp.t_eff, f_mean, cal_fit), jp.sigma_v).items()
        if k in ("resid_rms_mV", "excess", "r2")}
    return jp, res, cal_fit, v_model, out


def _pinned(rd, cal, opt, f_pin):
    t_img = cal.t_img_pulse
    kw = _joint_kwargs(rd, cal, opt, opt.v_range_sign)

    def fit(fp, ls_n, coh):
        return RabiJointPosterior(rd.ad, f_rabi_grid=float(fp),
                                  lightshift_grid=(0.0, 0.5 / t_img, int(ls_n)),
                                  coherence_grid=coh, midpoint_grid=opt.pin_midpoint,
                                  **dict(kw, calibration=copy.deepcopy(cal)))
    jp = fit(f_pin, opt.pin_lightshift_n, tuple(opt.pin_coherence))
    res = jp.run()
    cal_fit = res.fitted_calibration()
    v_model = _model_voltage(jp.t_eff, f_pin, cal_fit)
    out = {"f_pin": float(f_pin),
           "axes": {n: _stats(res.axis_stats[n]) for n in
                    ("midpoint_fraction", "frequency_lightshift", "back_action_coherence")},
           "v_down": list(res.v_down), "v_up": list(res.v_up),
           "boundary_warnings": list(res.metadata.get("boundary_warnings", [])),
           "adequacy": _adequacy(jp.apd, v_model, jp.sigma_v)}
    slopes = {}
    fr = opt.pin_slope_frac
    if fr > 0:
        # the lightshift_coherence_posterior notebook's slope grids (81, 39 at 101, 77)
        coarse_ls = max(9, int(round(opt.pin_lightshift_n * 0.8)))
        coarse_c = (opt.pin_coherence[0], opt.pin_coherence[1],
                    max(8, (int(opt.pin_coherence[2]) + 1) // 2))
        rm = fit(f_pin * (1 - fr), coarse_ls, coarse_c).run()
        rp_ = fit(f_pin * (1 + fr), coarse_ls, coarse_c).run()
        for name in ("frequency_lightshift", "back_action_coherence"):
            d = (rp_.axis_stats[name]["mean"] - rm.axis_stats[name]["mean"]) / (2 * 100 * fr)
            slopes[name + "_per_percent"] = float(d)
    out["slopes"] = slopes
    return jp, res, out


def _blocks(rd, cal_fit, opt, f_window, v_sign):
    """f_rabi per time-ordered block, nuisances pinned at the joint means."""
    K = int(opt.blocks)
    if K < 2 or rd.n_shot < 2 * K:
        return None, _gate(NA, note=f"blocks={K} with {rd.n_shot} shots: too few to split")
    order = rd.acq_order
    chunks = [c for c in np.array_split(order, K) if c.size]
    lo, hi = f_window
    # |sigma_v|: with an inverted readout (v_range_sign='data') the fitted
    # calibration carries v_up < v_down, and the library derives a negative
    # default sigma_v from it. The scale only anchors endpoint priors here.
    sig = _sigma_v(cal_fit)
    sig = sig if (np.isfinite(sig) and sig > 0) else 1e-3
    rows = []
    for k, idx in enumerate(chunks):
        idx = np.sort(idx)
        n_sched = int(np.unique(np.rint(rd.t_eff[idx] / 1e-12).astype(np.int64), axis=0).shape[0])
        jb = RabiJointPosterior(None, apd=rd.apd[idx], t_raman_pulse=rd.t_eff[idx],
                                calibration=copy.deepcopy(cal_fit),
                                f_rabi_grid=(lo, hi, int(opt.block_f_n)),
                                midpoint_grid=None, lightshift_grid=None, coherence_grid=None,
                                v_range_sign=v_sign, sigma_v=sig)
        rb = jb.run()
        st = rb.axis_stats["f_rabi"]
        rows.append({"block": k, "n_shot": int(idx.size), "n_distinct_schedules": n_sched,
                     "f_mean": float(st["mean"]), "f_std": float(st["std"]),
                     "f_map": float(st["map"]), "v_range": list(rb.v_range),
                     "v_down": list(rb.v_down), "railed": bool(rb.metadata.get("boundary_warnings"))})
    info = {"K": len(rows), "order_source": rd.acq_order_source, "rows": rows}
    thin = [r for r in rows if r["n_distinct_schedules"] < 3 and r["n_shot"] > 1
            and np.all(np.ptp(rd.t_eff, axis=1) < 1e-12)]
    if thin:
        return info, _gate(NA, note="blocks hold < 3 durations each (scanned design taken in "
                                     "sequential order): time is confounded with duration, so "
                                     "the block check cannot separate drift from the model. "
                                     "Take the scanned run with shuffle=True.")
    m = np.array([r["f_mean"] for r in rows])
    s = np.array([r["f_std"] for r in rows])
    w = 1.0 / np.maximum(s, 1e-9) ** 2
    mean = float(np.sum(w * m) / np.sum(w))
    chi2 = float(np.sum(w * (m - mean) ** 2))
    dof = len(rows) - 1
    try:
        from scipy.stats import chi2 as _chi2
        p = float(_chi2.sf(chi2, dof))
    except Exception:
        p = float("nan")
    # The APD contrast per block: the whole-run joint fit assumes one pair of
    # endpoints for the run, the blocks each get their own. A drifting contrast
    # (seen 2026-09-03 in 78312 and between runs 83148-83150) shows up here.
    vr = np.array([r["v_range"][0] for r in rows])
    vs = np.array([max(r["v_range"][1], 1e-9) for r in rows])
    wv = 1.0 / vs ** 2
    vr_mean = float(np.sum(wv * vr) / np.sum(wv))
    vr_chi2 = float(np.sum(wv * (vr - vr_mean) ** 2))
    try:
        from scipy.stats import chi2 as _chi2v
        vr_p = float(_chi2v.sf(vr_chi2, dof))
    except Exception:
        vr_p = float("nan")
    info.update({"weighted_mean": mean, "weighted_mean_err": float(1.0 / np.sqrt(np.sum(w))),
                 "chi2": chi2, "dof": dof, "p": p,
                 "scale": math.sqrt(max(chi2 / dof, 1.0)) if dof > 0 else 1.0,
                 "v_range_by_block_mV": [x * 1e3 for x in vr],
                 "v_range_err_by_block_mV": [x * 1e3 for x in vs],
                 "v_range_chi2": vr_chi2, "v_range_p": vr_p})
    railed = [r["block"] for r in rows if r["railed"]]
    note = "blocks railed at the window edge: " + str(railed) if railed else ""
    st = PASS if (np.isfinite(p) and p >= GATE_BLOCK_P and not railed) else FAIL
    return info, _gate(st, p, f"chi^2 p-value of block means >= {GATE_BLOCK_P}", note)


def _delay_profile(rd, cal_fit, f_center, v_sign, opt):
    """Profile likelihood over the Raman turn-on delay t0 (t_ideal = t_eff - t0).

    RabiJointPosterior does not grid t0, and a wrong t0 is a scale error on every
    rotation angle that f_rabi would absorb. For each t0 this refits f_rabi (wide
    window: a different t0 moves f by up to ~10%) with the APD endpoints and
    noise marginalized and the light shift / coherence / midpoint PINNED at the
    127-ns joint means -- so it is a conditional profile, fast and smooth, not a
    full marginalization. -2 log L = n log(RSS) up to a constant (Gaussian,
    unknown sigma), so dchi2 = n log(RSS / RSS_min).

    Identifiable only when the durations span a wide range (the scanned design);
    for a narrow randomized window it comes out flat, which is reported as such.
    """
    t0s = np.asarray(opt.delay_profile_ns, dtype=float) * 1e-9
    t_min = float(rd.t_eff.min())
    t0s = t0s[t0s < 0.9 * t_min]
    if t0s.size < 3:
        return None
    sig = _sigma_v(cal_fit)
    sig = sig if (np.isfinite(sig) and sig > 0) else 1e-3
    lo, hi = 0.75 * f_center, 1.35 * f_center
    n_data = rd.apd.size
    rows = []
    for t0 in t0s:
        c = replace(cal_fit, t_turn_on_delay=float(t0))
        jb = RabiJointPosterior(None, apd=rd.apd, t_raman_pulse=rd.t_eff, calibration=c,
                                f_rabi_grid=(lo, hi, int(opt.delay_profile_f_n)),
                                midpoint_grid=None, lightshift_grid=None, coherence_grid=None,
                                v_range_sign=v_sign, sigma_v=sig)
        rb = jb.run()
        best = rb.best()
        cm = replace(c, v_apd_all_down=best["v_apd_all_down"], v_apd_all_up=best["v_apd_all_up"])
        r = rd.apd - _model_voltage(rd.t_eff, best["f_rabi"], cm)
        rows.append({"t0_ns": float(t0 * 1e9), "f_map_hz": best["f_rabi"],
                     "f_mean_hz": float(rb.axis_stats["f_rabi"]["mean"]),
                     "f_std_hz": float(rb.axis_stats["f_rabi"]["std"]),
                     "rss_V2": float(np.sum(r * r))})
    rss = np.array([x["rss_V2"] for x in rows])
    d = n_data * np.log(rss / rss.min())
    for x, di in zip(rows, d):
        x["dchi2"] = float(di)
    t0n = np.array([x["t0_ns"] for x in rows])
    k = int(np.argmin(d))
    out = {"rows": rows, "conditional_on": "light shift, coherence, midpoint at the joint means",
           "t0_best_grid_ns": float(t0n[k]), "at_grid_edge": bool(k in (0, len(rows) - 1))}
    # parabola through the minimum and its neighbours -> t0_hat, sigma (dchi2 = 1)
    if 0 < k < len(rows) - 1:
        a, b, _ = np.polyfit(t0n[k - 1:k + 2], d[k - 1:k + 2], 2)
        if a > 0:
            out["t0_hat_ns"] = float(-b / (2 * a))
            out["t0_sigma_ns"] = float(1.0 / math.sqrt(a))
    fm = np.array([x["f_mean_hz"] for x in rows])
    out["df_dt0_hz_per_ns"] = float(np.polyfit(t0n, fm, 1)[0])
    out["flat"] = bool(d.max() < 4.0)
    return out


def _systematics(rd, cal_fit, f_mean, window, adequacy, opt):
    cal_sys = copy.deepcopy(cal_fit)
    # noise scale from this fit's residuals (the joint marginalized it)
    v_rng = abs(cal_sys.v_range)
    if v_rng > 0:
        cal_sys.std_n_photons_per_shot = (adequacy["resid_rms_mV"] * 1e-3
                                          * cal_sys.n_photons_per_shot / v_rng)
    lo, hi = window
    rp = RabiPosterior(rd.ad, apd=rd.apd, t_raman_pulse=rd.t_eff, calibration=cal_sys,
                       f_rabi_min=lo, f_rabi_max=hi, n_grid=301)
    base = rp.run()
    fr = {"t_turn_on_delay": opt.delay_frac} if opt.delay_frac > 0 else {}
    bud = rp.systematic_budget(fractions=fr, detuning_hz=opt.detuning_hz, verbose=False)
    rows = [{k: (float(v) if isinstance(v, (float, np.floating)) else v)
             for k, v in r.items()} for r in bud["rows"]]
    return {"fitted_cal_rp": {"f_mean": base.f_mean, "f_std": base.f_std,
                              "excess_noise_factor": base.metadata["excess_noise_factor"]},
            "rows": rows, "total_hz": float(bud["total_quadrature"]),
            "note": ("t_turn_on_delay fraction is a placeholder unless measured; the detuning row "
                     "is order-of-magnitude (the model precesses over the pulse, not the gap)")}


# ---------------------------------------------------------------------------
# one run
# ---------------------------------------------------------------------------

def analyze_run(rd: RunData, opt: AnalysisOptions, out_dir: Path = None, log=print):
    """Every estimator and every gate on one run. Returns a JSON-able dict."""
    rid = rd.run_id
    cal = rd.cal
    R = {"run_id": rid, "meta": rd.meta, "n_shot": rd.n_shot, "n_pulse": rd.n_pulse,
         "excluded": rd.excluded,
         "n_excluded": int(sum(len(e["rows"]) for e in rd.excluded)),
         "acq_order_source": rd.acq_order_source,
         "calibration": {f: getattr(cal, f) for f in RabiCalibration.CALIBRATION_FIELDS},
         "calibration_sources": dict(cal.sources),
         "sigma_v_assumed_mV": _sigma_v(cal) * 1e3}
    gates = {}
    R["design"] = _design(rd.t_eff)
    log(f"\n=== run {rid}: {rd.n_shot} shots x {rd.n_pulse} pulses | {R['design']['kind']}")
    if R["n_excluded"]:
        for e in rd.excluded:
            log(f"  EXCLUDED {len(e['rows'])} shot(s) {e['rows']}: {e['reason']}")
    log(f"  {cal.provenance_line()}")

    gates["enough_shots"] = _gate(PASS if rd.n_shot >= GATE_MIN_SHOTS else FAIL, rd.n_shot,
                                  f"n_shot >= {GATE_MIN_SHOTS}")
    img = rd.meta.get("imaging_type")
    gates["imaging_type"] = _gate(PASS if img == "DISPERSIVE" else
                                  (WARN if img in (None, "?") else FAIL), img,
                                  "DISPERSIVE (SLM phase-contrast mask)",
                                  "ABSORPTION writes a flat SLM mask and inverts the readout")
    gates["timing"], R["timing"] = _timing(rd)
    gates["apd_signal"], R["signal"] = _signal(rd)

    # --- polarity (model-free), via a throwaway joint object (its own sign
    # constraint is irrelevant here: only polarity_check() is called)
    jp0 = RabiJointPosterior(rd.ad, apd=rd.apd, t_raman_pulse=rd.t_eff,
                             calibration=copy.deepcopy(cal), f_rabi_grid=None,
                             v_range_sign=1.0) \
        if np.isfinite(cal.t_raman_pi_pulse) else None
    if jp0 is not None:
        gates["polarity"], R["polarity"] = _polarity(jp0)
    else:
        gates["polarity"], R["polarity"] = _gate(NA, note="no t_raman_pi_pulse"), None
    if opt.v_range_sign == "data" and gates["polarity"]["status"] == FAIL:
        gates["polarity"]["status"] = WARN
        gates["polarity"]["note"] += " -- analysed with v_range_sign='data' (the run's own polarity)"

    # --- 1. fixed calibration
    log("  [1/5] RabiPosterior (fixed calibration)")
    rp, rp_res, R["fixed"] = _fixed(rd, cal, opt)
    fx = R["fixed"]
    log(f"        f = {fx['f_mean']/1e3:.4f} +/- {fx['f_std']/1e3:.4f} kHz (MAP {fx['f_map']/1e3:.4f}),"
        f" GOF {fx['excess_noise_factor']:.2f}x")

    # --- 2. joint
    log("  [2/5] RabiJointPosterior (f, midpoint, light shift, coherence; APD marginalized)")
    jp, jres, cal_fit, v_model, R["joint"] = _joint(rd, cal, opt)
    J = R["joint"]
    fj, sj = J["axes"]["f_rabi"]["mean"], J["axes"]["f_rabi"]["std"]
    log(f"        f = {fj/1e3:.4f} +/- {sj/1e3:.4f} kHz | LS {J['axes']['frequency_lightshift']['mean']/1e3:.2f}"
        f" +/- {J['axes']['frequency_lightshift']['std']/1e3:.2f} kHz | C {J['axes']['back_action_coherence']['mean']:.3f}"
        f" +/- {J['axes']['back_action_coherence']['std']:.3f} | mid {J['axes']['midpoint_fraction']['mean']:.3f}"
        f" | resid {J['adequacy']['resid_rms_mV']:.2f} mV ({J['adequacy']['excess']:.2f}x), R2 {J['adequacy']['r2']:.2f}")

    # --- 3. pinned
    f_ref_default = cal.f_rabi_calibration
    if opt.skip_pinned or opt.pin_f == "none":
        R["pinned"] = None
        pjp = pres = None
    else:
        f_pin = f_ref_default if opt.pin_f == "auto" else float(opt.pin_f)
        if opt.pin_f == "auto" and opt.ref_t_pi:
            f_pin = 1.0 / (2.0 * opt.ref_t_pi)
        log(f"  [3/5] pinned fit at f = {f_pin/1e3:.4f} kHz (light shift, coherence)")
        pjp, pres, R["pinned"] = _pinned(rd, cal, opt, f_pin)
        P = R["pinned"]
        P["pull_vs_joint"] = (fj - f_pin) / sj if sj > 0 else float("nan")
        log(f"        LS {P['axes']['frequency_lightshift']['mean']/1e3:.2f} +/- "
            f"{P['axes']['frequency_lightshift']['std']/1e3:.2f} kHz | C "
            f"{P['axes']['back_action_coherence']['mean']:.3f} +/- {P['axes']['back_action_coherence']['std']:.3f}"
            f" | pin pull {P['pull_vs_joint']:+.1f} sigma | resid {P['adequacy']['excess']:.2f}x")

    # The joint fit is usable downstream only if it located f and did not rail
    # on f or the midpoint; otherwise the block and systematics steps would be
    # computed about a meaningless centre.
    hard_rail = [w for w in J["boundary_warnings"]
                 if w.split(":")[0] in ("f_rabi", "midpoint_fraction")]
    joint_usable = (J["localized"] is not False) and not hard_rail

    # --- 4. blocks
    log(f"  [4/5] block consistency ({opt.blocks} time-ordered blocks, order: {rd.acq_order_source})")
    if joint_usable:
        R["blocks"], gates["block_consistency"] = _blocks(
            rd, cal_fit, opt, (J["grid_f"][0], J["grid_f"][1]), jp._v_range_sign or None)
    else:
        R["blocks"], gates["block_consistency"] = None, _gate(
            NA, note="joint fit not usable (not localized or railed): no centre to test about")
    if R["blocks"] and "p" in R["blocks"]:
        B = R["blocks"]
        log(f"        chi2 {B['chi2']:.2f} / {B['dof']} dof, p = {B['p']:.3g}; v_range by block "
            + ", ".join(f"{x:.1f}" for x in B["v_range_by_block_mV"]) + " mV")
    else:
        log("        " + gates["block_consistency"]["note"])

    # --- 4b. turn-on delay profile
    R["delay_profile"] = None
    gates["turn_on_delay"] = _gate(NA, note="joint fit not usable or profile disabled")
    if joint_usable and len(opt.delay_profile_ns) >= 3:
        log("  [4b]  turn-on delay profile (conditional on the joint's nuisances)")
        DP = _delay_profile(rd, cal_fit, fj, jp._v_range_sign or None, opt)
        R["delay_profile"] = DP
        if DP is None:
            gates["turn_on_delay"] = _gate(NA, note="pulses too short for the profile grid")
        else:
            t0c = cal.t_turn_on_delay * 1e9
            line = ", ".join(f"{x['t0_ns']:.0f}:{x['dchi2']:.1f}" for x in DP["rows"])
            log(f"        dchi2 by t0 (ns): {line}")
            t0g = np.array([x["t0_ns"] for x in DP["rows"]])
            dg = np.array([x["dchi2"] for x in DP["rows"]])
            d_model = float(np.interp(t0c, t0g, dg))
            DP["dchi2_at_model_t0"] = d_model
            if "t0_hat_ns" in DP:
                log(f"        t0 = {DP['t0_hat_ns']:.0f} +/- {DP['t0_sigma_ns']:.0f} ns; model "
                    f"{t0c:.0f} ns has dchi2 {d_model:.1f}; df/dt0 = "
                    f"{DP['df_dt0_hz_per_ns']:.2f} Hz/ns")
            else:
                log(f"        profile minimum at the grid point {DP['t0_best_grid_ns']:.0f} ns "
                    f"(edge: {DP['at_grid_edge']}); model {t0c:.0f} ns has dchi2 {d_model:.1f}")
            note = ("FAIL: the delay the model assumes is rejected by the data, so f_rabi is an "
                    "effective value for this run's duration mix; write back t_raman_pi_pulse "
                    "and t_raman_pulse_offset together, from 'joint_at_profiled_t0'")
            if DP["at_grid_edge"] and d_model > 4.0:
                note += " (profile minimum at the grid edge: widen --delay-profile-ns)"
            gates["turn_on_delay"] = _gate(PASS if d_model <= 4.0 else FAIL, d_model,
                                           "profile dchi2 at the model's t0 <= 4 (2 sigma)",
                                           note if d_model > 4.0 else
                                           ("profile flat: t0 not identified by this design"
                                            if DP["flat"] else ""))
            if gates["turn_on_delay"]["status"] == FAIL and opt.refit_at_profiled_delay:
                t0h = DP.get("t0_hat_ns", DP["t0_best_grid_ns"]) * 1e-9
                log(f"        re-running the joint fit at t0 = {t0h*1e9:.0f} ns")
                cal_t0 = replace(cal, t_turn_on_delay=t0h)
                _, jres2, _, _, J2 = _joint(rd, cal_t0, opt)
                R["joint_at_profiled_t0"] = {"t0_ns": t0h * 1e9, "axes": J2["axes"],
                                             "adequacy": J2["adequacy"],
                                             "localized": J2["localized"],
                                             "boundary_warnings": J2["boundary_warnings"]}
                a2 = J2["axes"]["f_rabi"]
                log(f"        joint at t0 = {t0h*1e9:.0f} ns: f = {a2['mean']/1e3:.4f} +/- "
                    f"{a2['std']/1e3:.4f} kHz, resid {J2['adequacy']['resid_rms_mV']:.2f} mV")

    # --- 5. systematics
    if opt.skip_systematics or not joint_usable:
        R["systematics"] = None if opt.skip_systematics else {
            "skipped": "joint fit not usable (not localized or railed)"}
    else:
        log("  [5/5] systematics (turn-on delay, residual detuning) on the fitted calibration")
        R["systematics"] = _systematics(rd, cal_fit, fj, (J["grid_f"][0], J["grid_f"][1]),
                                        J["adequacy"], opt)

    # --- the number
    # Two uncertainties, because f_rabi and the turn-on delay t0 are correlated
    # (theta = 2 pi f (t - t0)):
    #   sigma_total      -- f as the model's EFFECTIVE Rabi frequency at the
    #                       model's t0 (what the kernel, which uses that t0,
    #                       needs): statistics (block-scaled) + detuning.
    #   sigma_true_omega -- the physical Rabi frequency: sigma_total plus
    #                       |df/dt0| * sigma(t0), from the t0 profile when it is
    #                       interior, else the delay_frac placeholder. This is
    #                       the one to compare with an absorption flop (which
    #                       fits t0 freely).
    scale = R["blocks"].get("scale", 1.0) if R["blocks"] else 1.0
    s_stat = sj * scale
    rows = {r["name"]: r for r in (R["systematics"] or {}).get("rows", [])}
    s_det = rows.get("raman transition frequency", {}).get("half_range", 0.0)
    DP = R.get("delay_profile")
    t0_model_ns = cal.t_turn_on_delay * 1e9
    if DP and "t0_sigma_ns" in DP and not DP.get("flat"):
        s_t0_ns = max(DP["t0_sigma_ns"], abs(DP["t0_hat_ns"] - t0_model_ns))
        s_delay = abs(DP["df_dt0_hz_per_ns"]) * s_t0_ns
        delay_src = (f"t0 profile: |df/dt0| {abs(DP['df_dt0_hz_per_ns']):.2f} Hz/ns x "
                     f"{s_t0_ns:.0f} ns (max of sigma_t0 and |t0_hat - model|)")
    elif DP:
        s_t0_ns = opt.delay_frac * t0_model_ns
        s_delay = abs(DP["df_dt0_hz_per_ns"]) * s_t0_ns
        delay_src = (f"t0 profile slope {abs(DP['df_dt0_hz_per_ns']):.2f} Hz/ns x placeholder "
                     f"{s_t0_ns:.0f} ns ({100*opt.delay_frac:.0f}% of the model t0)")
    else:
        s_delay = rows.get("t_turn_on_delay", {}).get("half_range", 0.0)
        delay_src = f"systematic_budget row, placeholder {100*opt.delay_frac:.0f}% of t0"
    s_tot = math.sqrt(s_stat ** 2 + s_det ** 2)
    s_true = math.sqrt(s_tot ** 2 + s_delay ** 2)
    t_pi = 1.0 / (2.0 * fj)
    R["result"] = {"f_rabi_hz": fj, "sigma_stat_hz": sj, "block_scale": scale,
                   "sigma_stat_scaled_hz": s_stat, "sigma_detuning_hz": s_det,
                   "sigma_total_hz": s_tot, "t0_model_ns": t0_model_ns,
                   "sigma_delay_hz": s_delay, "sigma_delay_source": delay_src,
                   "sigma_true_omega_hz": s_true, "t_pi_s": t_pi,
                   "sigma_t_pi_s": s_tot / (2.0 * fj * fj),
                   "sigma_t_pi_true_s": s_true / (2.0 * fj * fj)}

    # --- APD contrast drift, and whether it moved the whole-run answer
    B = R["blocks"]
    if B and "v_range_p" in B:
        vp = B["v_range_p"]
        gates["apd_contrast_stable"] = _gate(
            PASS if (np.isfinite(vp) and vp >= GATE_BLOCK_P) else WARN, vp,
            f"chi^2 p-value of per-block v_range >= {GATE_BLOCK_P}",
            "v_range by block (mV): " + ", ".join(f"{x:.1f}" for x in B["v_range_by_block_mV"]))
        # Yardstick is sigma_joint: f_blocks is conditional on the joint's nuisance
        # means (its own error leaves their uncertainty out), and both come from
        # the same shots, so a gap below the quoted joint width does not matter.
        d = (fj - B["weighted_mean"]) / max(sj, 1e-9)
        R["result"]["f_blocks_hz"] = B["weighted_mean"]
        R["result"]["f_blocks_err_cond_hz"] = B["weighted_mean_err"]
        st = PASS if abs(d) <= 1.0 else (WARN if abs(d) <= 2.0 else FAIL)
        gates["joint_vs_blocks"] = _gate(
            st, d, "|f_joint - f_blocks| / sigma_joint <= 1 (FAIL > 2)",
            "f_blocks re-fits the APD endpoints per block, so it is robust to a contrast that "
            "drifts during the run; a gap means the whole-run fit was pulled by that drift")
    else:
        gates["apd_contrast_stable"] = _gate(NA, note="no block fits")
        gates["joint_vs_blocks"] = _gate(NA, note="no block fits")

    # --- reference
    t_ref = opt.ref_t_pi or cal.t_raman_pi_pulse
    ref = {"t_ref_s": t_ref, "source": "--ref-t-pi" if opt.ref_t_pi else "run params t_raman_pi_pulse",
           "frac_unc": opt.ref_frac_unc}
    if t_ref and np.isfinite(t_ref) and t_ref > 0:
        f_ref = 1.0 / (2.0 * t_ref)
        comb = math.sqrt(s_true ** 2 + (opt.ref_frac_unc * f_ref) ** 2)
        ref.update({"f_ref_hz": f_ref, "ratio": fj / f_ref, "pull": (fj - f_ref) / comb})
        gates["reference_agreement"] = _gate(PASS if abs(ref["pull"]) <= GATE_REF_PULL else FAIL,
                                             ref["pull"], f"|pull| <= {GATE_REF_PULL}",
                                             f"reference {ref['source']}, +/-{100*opt.ref_frac_unc:.1f}%")
    else:
        gates["reference_agreement"] = _gate(NA, note="no reference pi time")
    R["reference"] = ref

    # --- joint gates
    if J["localized"] is False:
        ci = J["wide"]["f"]["ci95"]
        gates["joint_localized"] = _gate(
            FAIL, [ci[0], ci[1]], f"wide-stage 95% CI narrower than {100*LOCALIZED_FRAC:.0f}% of MAP",
            "the joint fit cannot pick f_rabi over the wide window (aliases or weak data); "
            "a narrower window would choose the answer, not the data")
    else:
        mass = J.get("wide", {}).get("mass_in_zoom_window")
        if mass is None:
            gates["joint_localized"] = _gate(NA, note="explicit f grid: no wide stage run")
        else:
            st = PASS if mass >= GATE_WINDOW_MASS_WARN else (
                WARN if mass >= GATE_WINDOW_MASS_FAIL else FAIL)
            gates["joint_localized"] = _gate(
                st, mass, f"wide-stage f mass inside the zoom window >= {GATE_WINDOW_MASS_WARN}"
                          f" (FAIL < {GATE_WINDOW_MASS_FAIL})")
    gates["joint_single_mode"] = _gate(PASS if J["n_modes"] == 1 else WARN, J["n_modes"],
                                       "one mode (>= 5% mass) in the final f marginal")
    hard = hard_rail
    soft = [w for w in J["boundary_warnings"] if w not in hard]
    gates["joint_no_railing"] = _gate(FAIL if hard else PASS, len(hard),
                                      "f_rabi and midpoint not within two steps of a grid edge",
                                      "; ".join(hard))
    gates["joint_nuisance_edges"] = _gate(WARN if soft else PASS, len(soft),
                                          "light shift / coherence away from grid edges",
                                          "; ".join(soft) + (" (light shift edges are the alias "
                                          "symmetry points 0 and 1/(2 t_img); a coherence at the "
                                          "floor means the record lacks the predicted pulse-to-pulse "
                                          "structure)" if soft else ""))
    A = J["adequacy"]
    gates["joint_adequacy"] = _gate(PASS if A["excess"] <= GATE_JOINT_EXCESS_LIMIT else FAIL,
                                    A["excess"], f"joint resid rms / sigma_v <= {GATE_JOINT_EXCESS_LIMIT}",
                                    f"R^2 {A['r2']:.2f}, within-shot resid corr "
                                    f"{A['within_shot_resid_corr']:.2f}, max |per-pulse z| "
                                    f"{A['max_abs_per_pulse_z']:.1f}")
    gates["joint_variance_explained"] = _gate(PASS if A["r2"] >= GATE_R2_WARN else WARN, A["r2"],
                                              f"R^2 >= {GATE_R2_WARN}")
    gates["rp_gof"] = _gate(PASS if fx["excess_noise_factor"] <= GATE_GOF_LIMIT else FAIL,
                            fx["excess_noise_factor"], f"RabiPosterior excess <= {GATE_GOF_LIMIT}",
                            "fixed-calibration fit; FAIL = the stored APD/Bloch calibration does "
                            "not describe this run")
    loc = fx.get("localized")
    gates["rp_localized"] = _gate(NA if loc is None else (PASS if loc else FAIL), loc,
                                  f"RabiPosterior wide-stage 95% CI narrower than "
                                  f"{100*LOCALIZED_FRAC:.0f}% of MAP")
    if joint_usable:
        d = (fx["f_mean"] - fj) / sj if sj > 0 else float("inf")
        st = PASS if abs(d) <= GATE_RP_VS_JOINT_PASS else (
            WARN if abs(d) <= GATE_RP_VS_JOINT_FAIL else FAIL)
        gates["rp_vs_joint"] = _gate(st, d, f"|f_RP - f_joint| / sigma_joint <= "
                                     f"{GATE_RP_VS_JOINT_PASS} (FAIL > {GATE_RP_VS_JOINT_FAIL})")
    else:
        gates["rp_vs_joint"] = _gate(NA, note="joint fit not usable")
    if fx.get("boundary_warning"):
        gates["rp_no_railing"] = _gate(FAIL, None, "RabiPosterior MAP away from grid edges",
                                       fx["boundary_warning"])
    else:
        gates["rp_no_railing"] = _gate(PASS, None, "RabiPosterior MAP away from grid edges")
    if R["pinned"] is not None and not joint_usable:
        gates["pin_consistent"] = _gate(NA, note="joint fit not usable: no free f to compare")
    elif R["pinned"] is not None:
        pull = R["pinned"]["pull_vs_joint"]
        gates["pin_consistent"] = _gate(PASS if abs(pull) <= GATE_PIN_PULL else FAIL, pull,
                                        f"|f_joint - f_pin| / sigma_joint <= {GATE_PIN_PULL}",
                                        "FAIL = the pinned light shift/coherence are conditional on "
                                        "an f_rabi the data reject (sensitivity study only)")
    rel = {}
    for name in ("frequency_lightshift", "back_action_coherence", "midpoint_fraction"):
        a = J["axes"][name]
        rel[name] = abs(a["std"] / a["mean"]) if a["mean"] else float("inf")
    gates["nuisances_tight"] = _gate(
        PASS if max(rel["frequency_lightshift"], rel["back_action_coherence"]) <= GATE_LOOSE_FRAC else WARN,
        rel, f"light shift and coherence relative width <= {GATE_LOOSE_FRAC}")
    ps = fx.get("per_shot")
    if ps and R["design"]["kind"].startswith("randomized, fresh"):
        gates["per_shot_scatter"] = _gate(PASS if ps["ratio"] <= 1.5 else WARN, ps["ratio"],
                                          "per-shot MAP scatter / per-shot width <= 1.5")
    else:
        gates["per_shot_scatter"] = _gate(NA, ps["ratio"] if ps else None,
                                          note="per-shot posteriors alias for this design")

    R["gates"] = gates
    R["verdicts"] = _verdicts(gates)
    R["proposal"] = _proposal(R)
    log("  verdicts: " + ", ".join(f"{k} {v['status']}" for k, v in R["verdicts"].items()))

    if opt.figures and out_dir is not None:
        R["figures"] = _figures(rd, R, rp, jp, cal_fit, v_model, pjp, out_dir)
    return R


_VERDICT_GATES = {
    "t_pi": ["enough_shots", "imaging_type", "timing", "apd_signal", "polarity",
             "joint_localized", "joint_single_mode", "joint_no_railing", "joint_adequacy",
             "block_consistency", "joint_vs_blocks", "apd_contrast_stable",
             "turn_on_delay", "reference_agreement"],
    "nuisances": ["enough_shots", "imaging_type", "timing", "apd_signal", "polarity",
                  "joint_localized", "joint_single_mode", "joint_no_railing", "joint_adequacy",
                  "block_consistency", "turn_on_delay", "joint_nuisance_edges",
                  "nuisances_tight"],
    "fixed_cal": ["polarity", "rp_localized", "rp_gof", "rp_no_railing", "rp_vs_joint"],
}


# N/A on one of these means the evidence a verdict rests on was not produced
_EVIDENCE_GATES = ("block_consistency", "reference_agreement", "rp_vs_joint",
                   "joint_localized", "rp_localized", "joint_vs_blocks")


def _verdicts(gates):
    out = {}
    for name, keys in _VERDICT_GATES.items():
        sts = {k: gates[k]["status"] for k in keys if k in gates}
        fails = [k for k, s in sts.items() if s == FAIL]
        warns = [k for k, s in sts.items() if s == WARN]
        # N/A counts as not-passed for the gates that carry the evidence
        missing = [k for k, s in sts.items() if s == NA and k in _EVIDENCE_GATES]
        status = FAIL if fails else (WARN if (warns or missing) else PASS)
        out[name] = {"status": status, "failed": fails, "warned": warns, "not_evaluated": missing}
    return out


def _proposal(R):
    """Paste lines -- ONLY printed when the matching verdict is PASS. Never applied."""
    today = _dt.date.today().isoformat()
    rid = R["run_id"]
    out = {}
    res = R["result"]
    if R["verdicts"]["t_pi"]["status"] == PASS:
        out["kexp/config/expt_params.py"] = [
            "# comment out the current line, then:",
            f"self.t_raman_pi_pulse = {res['t_pi_s']:.4e} #{rid} rabi posterior (joint), {today}"
            f"  # +/- {res['sigma_t_pi_s']*1e9:.0f} ns effective at t0 = "
            f"{res['t0_model_ns']:.0f} ns (+/- {res['sigma_t_pi_true_s']*1e9:.0f} ns incl. t0)"]
    if R["verdicts"]["nuisances"]["status"] == PASS:
        J = R["joint"]["axes"]
        ls, c = J["frequency_lightshift"], J["back_action_coherence"]
        out["HF_experiments/feedback/expt_params_feedback.py"] = [
            "# comment out the current lines, then:",
            f"# run {rid} | RabiJointPosterior (f_rabi free), {today}",
            f"self.frequency_lightshift = {ls['mean']:.4g}  # Hz +/- {ls['std']:.3g}, at "
            f"t_img_pulse = {R['calibration']['t_img_pulse']:.1e} s (identified mod 1/t_img, up to sign)",
            f"self.back_action_coherence = {c['mean']:.4f}  # +/- {c['std']:.4f}"]
    return out


# ---------------------------------------------------------------------------
# several runs
# ---------------------------------------------------------------------------

def combine_runs(results):
    """Inverse-variance mean of the per-run joint f_rabi and a chi^2 across runs."""
    rows = [(r["run_id"], r["result"]["f_rabi_hz"], r["result"]["sigma_total_hz"],
             r["verdicts"]["t_pi"]["status"]) for r in results]
    if len(rows) < 2:
        return None
    f = np.array([x[1] for x in rows])
    s = np.array([x[2] for x in rows])
    w = 1.0 / s ** 2
    mean = float(np.sum(w * f) / np.sum(w))
    err = float(1.0 / np.sqrt(np.sum(w)))
    chi2 = float(np.sum(w * (f - mean) ** 2))
    dof = len(rows) - 1
    try:
        from scipy.stats import chi2 as _chi2
        p = float(_chi2.sf(chi2, dof))
    except Exception:
        p = float("nan")
    scale = math.sqrt(max(chi2 / dof, 1.0))
    return {"runs": [x[0] for x in rows], "per_run_t_pi_verdict": [x[3] for x in rows],
            "f_mean_hz": mean, "f_err_hz": err, "f_err_scaled_hz": err * scale,
            "chi2": chi2, "dof": dof, "p": p,
            "gate": _gate(PASS if (np.isfinite(p) and p >= GATE_BLOCK_P) else FAIL, p,
                          f"run-to-run chi^2 p-value >= {GATE_BLOCK_P}"),
            "t_pi_s": 1.0 / (2.0 * mean), "sigma_t_pi_s": err * scale / (2.0 * mean * mean)}


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------

def _figures(rd, R, rp, jp, cal_fit, v_model, pjp, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rid = R["run_id"]
    t_img = rd.cal.t_img_pulse
    amp = rd.meta.get("p.amp_imaging", float("nan"))
    tag = (f"run {rid} | t_img {t_img*1e6:.1f} us | amp_imaging {amp} | "
           f"t_pi(params) {rd.cal.t_raman_pi_pulse*1e6:.4f} us")
    files = []

    def save(fig, name):
        p = out_dir / f"run{rid}_{name}.png"
        fig.savefig(p, dpi=130, bbox_inches="tight")
        plt.close(fig)
        files.append(p.name)

    try:
        fig, _ = rp.plot_report()
        fig.suptitle(tag + " | RabiPosterior, fixed calibration", fontsize="small")
        save(fig, "fixed_report")
    except Exception as e:                       # a plot must never stop the analysis
        R.setdefault("figure_errors", []).append(f"fixed_report: {e!r}")

    try:
        names = [n for n in JOINT_AXES if not jp.pinned[n]]
        fig, axes = plt.subplots(1, len(names), figsize=(3.6 * len(names), 3.2))
        jp.plot_marginals(axes=axes)
        fig.suptitle(tag + " | RabiJointPosterior marginals", fontsize="small")
        fig.tight_layout()
        save(fig, "joint_marginals")
        if len(names) >= 2:
            fig, _ = jp.plot_corner()
            fig.suptitle(tag + " | joint posterior, pairwise", fontsize="small")
            save(fig, "joint_corner")
    except Exception as e:
        R.setdefault("figure_errors", []).append(f"joint: {e!r}")

    try:
        v = jp.apd
        r = (v - v_model) * 1e3
        sig = jp.sigma_v * 1e3
        n_s, n_p = v.shape
        k = np.arange(1, n_p + 1)
        fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
        for i in range(n_s):
            a = 0.8 if n_s == 1 else max(0.08, min(0.5, 6.0 / n_s))
            ax[0].plot(k, v[i] * 1e3, "o-", ms=2.5, lw=0.6, color="C0", alpha=a)
            ax[0].plot(k, v_model[i] * 1e3, "s--", ms=2.5, lw=0.6, color="C3", alpha=a)
        ax[0].plot([], [], "o-", color="C0", label="measured")
        ax[0].plot([], [], "s--", color="C3", label="joint model")
        ax[0].set_xlabel("pulse index"); ax[0].set_ylabel("APD voltage (mV)")
        ax[0].legend(fontsize="x-small"); ax[0].set_title("traces", fontsize="small")
        lim = np.array([min(v.min(), v_model.min()), max(v.max(), v_model.max())]) * 1e3
        ax[1].plot(v.ravel() * 1e3, v_model.ravel() * 1e3, "o", ms=2.5, alpha=0.5)
        ax[1].plot(lim, lim, "k--", lw=1)
        ax[1].fill_between(lim, lim - sig, lim + sig, color="0.5", alpha=0.15,
                           label=f"+/-1 sigma_v ({sig:.1f} mV)")
        ax[1].set_xlabel("measured (mV)"); ax[1].set_ylabel("model (mV)")
        ax[1].legend(fontsize="x-small"); ax[1].set_title("parity", fontsize="small")
        ax[2].axhspan(-sig, sig, color="0.5", alpha=0.15)
        for i in range(n_s):
            ax[2].plot(k, r[i], "-", lw=0.5, color="C0", alpha=0.25)
        se = r.std(axis=0, ddof=1) / np.sqrt(n_s) if n_s > 1 else np.zeros(n_p)
        ax[2].errorbar(k, r.mean(axis=0), yerr=se, fmt="ko-", ms=3, capsize=2,
                       label="mean over shots +/- SE")
        ax[2].axhline(0, color="0.6", lw=0.8)
        ax[2].set_xlabel("pulse index"); ax[2].set_ylabel("measured - model (mV)")
        ax[2].legend(fontsize="x-small"); ax[2].set_title("residuals", fontsize="small")
        A = R["joint"]["adequacy"]
        fig.suptitle(f"{tag} | joint fit f = {R['result']['f_rabi_hz']/1e3:.3f} kHz | resid "
                     f"{A['resid_rms_mV']:.2f} mV vs sigma_v {A['sigma_v_assumed_mV']:.2f} mV "
                     f"({A['excess']:.2f}x), R2 {A['r2']:.2f}", fontsize="small")
        fig.tight_layout()
        save(fig, "joint_residuals")
    except Exception as e:
        R.setdefault("figure_errors", []).append(f"residuals: {e!r}")

    if pjp is not None:
        try:
            names = [n for n in JOINT_AXES if not pjp.pinned[n]]
            fig, axes = plt.subplots(1, len(names), figsize=(3.8 * len(names), 3.2))
            pjp.plot_marginals(axes=axes)
            fig.suptitle(f"{tag} | f_rabi pinned at {R['pinned']['f_pin']/1e3:.4f} kHz "
                         f"(pin pull vs joint {R['pinned']['pull_vs_joint']:+.1f} sigma)",
                         fontsize="small")
            fig.tight_layout()
            save(fig, "pinned_marginals")
        except Exception as e:
            R.setdefault("figure_errors", []).append(f"pinned: {e!r}")

    B = R.get("blocks")
    if B and B.get("rows"):
        try:
            rows = B["rows"]
            k = [r["block"] for r in rows]
            fig, ax = plt.subplots(1, 2, figsize=(9, 3.2))
            ax[0].errorbar(k, [r["f_mean"] / 1e3 for r in rows],
                           yerr=[r["f_std"] / 1e3 for r in rows], fmt="o", capsize=3)
            if "weighted_mean" in B:
                ax[0].axhline(B["weighted_mean"] / 1e3, color="C3", ls="--", lw=1,
                              label=f"weighted mean, chi2 {B['chi2']:.1f}/{B['dof']} (p {B['p']:.2g})")
                ax[0].legend(fontsize="x-small")
            ax[0].set_xlabel("block (acquisition order)"); ax[0].set_ylabel("rabi frequency (kHz)")
            ax[1].errorbar(k, [r["v_range"][0] * 1e3 for r in rows],
                           yerr=[r["v_range"][1] * 1e3 for r in rows], fmt="s", color="C1", capsize=3)
            ax[1].set_xlabel("block (acquisition order)"); ax[1].set_ylabel("fitted v_range (mV)")
            fig.suptitle(f"{tag} | block consistency ({B['order_source']})", fontsize="small")
            fig.tight_layout()
            save(fig, "blocks")
        except Exception as e:
            R.setdefault("figure_errors", []).append(f"blocks: {e!r}")
    return files


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

OUTPUT_ROOT = Path(r"C:\lab\skynet_log\outputs")


def _check_out_dir(path: Path):
    """Allow-list: outputs go only inside OUTPUT_ROOT, the lab's local agent/analysis
    output folder (.claude/lab-rules.md section 1). A relative --out is taken
    relative to OUTPUT_ROOT."""
    p = Path(path)
    if not p.is_absolute():
        p = OUTPUT_ROOT / p
    p = p.resolve()
    root = OUTPUT_ROOT.resolve()
    if p != root and root not in p.parents:
        raise SystemExit(f"--out must be inside {OUTPUT_ROOT}: {path}")
    return p


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return _jsonable(x.tolist())
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return v if math.isfinite(v) else str(v)
    if isinstance(x, (str, int, bool)) or x is None:
        return x
    return repr(x)


def _print_summary(results, combined, log=print):
    log("\n" + "=" * 96)
    log("f_joint +/- sigma_total (effective at the model t0) [+/- incl. t0 uncertainty]")
    log(f"{'run':>7} {'f_joint (kHz)':>32} {'t_pi (us)':>18} {'f_RP (kHz)':>12} {'RP GOF':>7}"
        f" {'LS (kHz)':>14} {'C':>12}  t_pi / nuis / fixed_cal")
    for R in results:
        J = R["joint"]["axes"]
        res = R["result"]
        log(f"{R['run_id']:>7} {res['f_rabi_hz']/1e3:>10.3f} +/- {res['sigma_total_hz']/1e3:<6.3f}"
            f"[{res['sigma_true_omega_hz']/1e3:<6.3f}]"
            f" {res['t_pi_s']*1e6:>8.4f}+/-{res['sigma_t_pi_s']*1e6:<6.4f}"
            f" {R['fixed']['f_mean']/1e3:>12.3f} {R['fixed']['excess_noise_factor']:>6.2f}x"
            f" {J['frequency_lightshift']['mean']/1e3:>6.2f}+/-{J['frequency_lightshift']['std']/1e3:<5.2f}"
            f" {J['back_action_coherence']['mean']:>5.3f}+/-{J['back_action_coherence']['std']:<5.3f}"
            f"  {R['verdicts']['t_pi']['status']} / {R['verdicts']['nuisances']['status']} / "
            f"{R['verdicts']['fixed_cal']['status']}")
        for vname, v in R["verdicts"].items():
            if v["failed"] or v["warned"] or v["not_evaluated"]:
                log(f"        {vname}: failed {v['failed']} warned {v['warned']} "
                    f"not evaluated {v['not_evaluated']}")
        if R.get("n_excluded"):
            log(f"        {R['n_excluded']} shot(s) excluded: "
                + "; ".join(f"{len(e['rows'])} {e['reason']}" for e in R["excluded"]))
    if combined:
        log(f"combined ({len(combined['runs'])} runs): f = {combined['f_mean_hz']/1e3:.4f} +/- "
            f"{combined['f_err_scaled_hz']/1e3:.4f} kHz (chi2 {combined['chi2']:.2f}/{combined['dof']},"
            f" p {combined['p']:.3g}: {combined['gate']['status']})")
    for R in results:
        for target, lines in R["proposal"].items():
            log(f"\nPROPOSAL (not applied) from run {R['run_id']} -> {target}")
            for ln in lines:
                log("    " + ln)
    log("=" * 96)


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------

def _grid_arg(values, name):
    """'lo hi n' -> tuple; 'pin' -> None (pin at calibration); one number -> pinned value."""
    if values is None:
        return "default"
    if len(values) == 1 and values[0].lower() == "pin":
        return None
    if len(values) == 1:
        return float(values[0])
    if len(values) == 3:
        return (float(values[0]), float(values[1]), int(float(values[2])))
    raise SystemExit(f"--{name}: give 'lo hi n', 'pin', or one value")


def build_parser():
    p = argparse.ArgumentParser(
        prog="python -m kexp.analysis.rabi_posterior_cli",
        description="RabiPosterior + RabiJointPosterior (+ pinned light-shift/coherence fit) on "
                    "pulse-train runs, with the pre-registered gates of the 2026-09-27 plan.")
    p.add_argument("runs", nargs="+", type=int, help="run ids (positive)")
    p.add_argument("--out", default=None,
                   help=f"output folder (default {DEFAULT_OUT_ROOT}\\cli\\<stamp>_<runs>)")
    p.add_argument("--quick", action="store_true", help="coarse grids (a first look, not for quoting)")
    p.add_argument("--no-figures", action="store_true")
    p.add_argument("--rp-grid", nargs=3, type=float, metavar=("LO", "HI", "N"),
                   help="explicit RabiPosterior grid (skips wide+zoom)")
    p.add_argument("--joint-f", nargs=3, type=float, metavar=("LO", "HI", "N"),
                   help="explicit joint f grid (skips the wide locator stage)")
    p.add_argument("--joint-wide", nargs=3, type=float, metavar=("LO", "HI", "N"),
                   help="wide locator grid for the joint fit (default 10e3 200e3 761)")
    p.add_argument("--joint-midpoint", nargs="+", help="'lo hi n' | 'pin' | value")
    p.add_argument("--joint-lightshift", nargs="+", help="'lo hi n' | 'pin' | value "
                   "(default 0 .. 1/(2 t_img), the identifiable half alias period)")
    p.add_argument("--joint-coherence", nargs="+", help="'lo hi n' | 'pin' | value")
    p.add_argument("--v-range-sign", default="calibration",
                   help="calibration (default) | data (runs before 2026-08-25) | +1 | -1 | free")
    p.add_argument("--pin-f", default="auto",
                   help="pinned-fit f_rabi: auto (1/(2 t_raman_pi_pulse) or --ref-t-pi) | none | Hz")
    p.add_argument("--pin-lightshift-n", type=int, default=None)
    p.add_argument("--pin-coherence", nargs=3, type=float, metavar=("LO", "HI", "N"))
    p.add_argument("--ref-t-pi", type=float, default=None,
                   help="reference pi time (s), e.g. from a same-session absorption flop")
    p.add_argument("--ref-frac-unc", type=float, default=0.03,
                   help="fractional 1-sigma of the reference f_rabi (default 0.03: ~2.9%% refit of 83102)")
    p.add_argument("--blocks", type=int, default=None, help="time-ordered blocks (0 disables)")
    p.add_argument("--detuning-hz", type=float, default=500.0,
                   help="1-sigma residual Raman detuning for the systematic row (from a Ramsey check)")
    p.add_argument("--delay-frac", type=float, default=0.25,
                   help="fractional 1-sigma of the 127 ns turn-on delay (placeholder)")
    p.add_argument("--delay-profile-ns", nargs="*", type=float, default=None,
                   help="turn-on delays to profile (ns); give none to disable")
    p.add_argument("--no-systematics", action="store_true")
    p.add_argument("--no-pinned", action="store_true")
    p.add_argument("--cal", nargs="*", default=[], metavar="FIELD=VALUE",
                   help="RabiCalibration overrides for every estimator (recorded as 'override'), "
                        "e.g. v_apd_all_up=-0.17 v_apd_all_down=-0.212")
    return p


def options_from_args(a):
    opt = _quick_options() if a.quick else AnalysisOptions()
    if a.no_figures:
        opt.figures = False
    if a.rp_grid:
        opt.rp_grid = (a.rp_grid[0], a.rp_grid[1], int(a.rp_grid[2]))
    if a.joint_f:
        opt.joint_f = (a.joint_f[0], a.joint_f[1], int(a.joint_f[2]))
    if a.joint_wide:
        opt.joint_wide = (a.joint_wide[0], a.joint_wide[1], int(a.joint_wide[2]))
    for attr, name in (("midpoint", "joint_midpoint"), ("lightshift", "joint_lightshift"),
                       ("coherence", "joint_coherence")):
        g = _grid_arg(getattr(a, name), name)
        if g != "default":
            setattr(opt, attr, g)
    vs = a.v_range_sign
    opt.v_range_sign = (None if vs == "free" else vs if vs in ("calibration", "data")
                        else float(vs))
    opt.pin_f = a.pin_f if a.pin_f in ("auto", "none") else float(a.pin_f)
    if a.pin_lightshift_n:
        opt.pin_lightshift_n = a.pin_lightshift_n
    if a.pin_coherence:
        opt.pin_coherence = (a.pin_coherence[0], a.pin_coherence[1], int(a.pin_coherence[2]))
    opt.ref_t_pi = a.ref_t_pi
    opt.ref_frac_unc = a.ref_frac_unc
    if a.blocks is not None:
        opt.blocks = a.blocks
    opt.detuning_hz = a.detuning_hz
    opt.delay_frac = a.delay_frac
    opt.skip_systematics = a.no_systematics
    if a.delay_profile_ns is not None:
        opt.delay_profile_ns = tuple(a.delay_profile_ns)
    opt.skip_pinned = a.no_pinned
    return opt


def _parse_cal(items):
    out = {}
    for it in items:
        k, _, v = it.partition("=")
        if not _ or k not in RabiCalibration.CALIBRATION_FIELDS:
            raise SystemExit(f"--cal {it!r}: need FIELD=VALUE with FIELD one of "
                             f"{', '.join(RabiCalibration.CALIBRATION_FIELDS)}")
        out[k] = (v.lower() in ("1", "true", "yes")) if k.endswith("_enabled") else float(v)
    return out


def main(argv=None, loader=None):
    a = build_parser().parse_args(argv)
    if any(r <= 0 for r in a.runs):
        raise SystemExit("run ids must be positive (relative indices like 0 / -1 are not "
                         "accepted: say which run you mean)")
    opt = options_from_args(a)
    cal_over = _parse_cal(a.cal)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = Path(a.out) if a.out else (DEFAULT_OUT_ROOT / "cli" /
                                     f"{stamp}_runs_{'_'.join(str(r) for r in a.runs)}")
    out = _check_out_dir(out)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    for rid in a.runs:
        rd = load_run(rid, loader=loader, cal_overrides=cal_over)
        results.append(analyze_run(rd, opt, out_dir=out))
    combined = combine_runs(results)
    _print_summary(results, combined)

    doc = {"generated": stamp, "argv": list(sys.argv if argv is None else argv),
           "module": __name__, "gates": GATES, "options": opt.__dict__,
           "cal_overrides": cal_over, "runs": results, "combined": combined,
           "note": "Proposals are NOT applied. Numbers are only as good as the gates say."}
    path = out / "results.json"
    path.write_text(json.dumps(_jsonable(doc), indent=2))
    print(f"\nwrote {path}")
    return doc


if __name__ == "__main__":
    main()
