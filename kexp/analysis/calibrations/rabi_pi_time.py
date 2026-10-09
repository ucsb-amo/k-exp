"""Rabi pi time t_pi = 1/(2 f_Rabi) (the rate pi time) from a pulse-length scan.

The fit is waxa's Rabi fitter, ``waxa.analysis.rabi.fit_rabi`` (the
replacement for the fitting inside ``waxa.plotting.rabi_oscillation``, which
throws its covariance away): ``offset + amp/2 env(t) cos(omega t + phi)``,
started from a frequency scan, decay model by AICc, repeats grouped by pulse
length.

The written value is ``pi / omega`` = 1/(2 f_Rabi), the RATE pi time: the K
machine's models subtract the turn-on (``t_raman_pulse_offset``) themselves, so
``t_raman_pi_pulse`` must not include it (memory: rabi-and-lightshift-fits,
2026-09-28). The commanded pi time (dead time included) is in ``fit["also"]``
for reference, never written.

The uncertainty is the fit's: ``pi/omega * sigma_omega/omega`` with
``sigma_omega`` from the covariance. fit_rabi scales the covariance by chi2/dof
ALWAYS in the "unweighted" mode used here (the noise is estimated from the
residuals), and in its weighted modes only when chi2/dof > 1. When the fit
gives no finite uncertainty, ``unc`` is None (and the result is flagged); none
is made up.

Shots with a non-finite pulse length or signal are left out of the fit and
counted in ``excluded``; nothing else is left out.

Weighting: this analysis passes ``noise="unweighted"`` by default -- every shot
is fitted and the noise is taken from the residuals. waxa's ``fit_rabi`` itself
is NOT changed: its own default stays ``noise="auto"`` ("sem" when there are
repeats), for every other caller. The choice here is by the coverage of the
reported uncertainty on synthetic flops with a known pi time (an honest error
bar has pull std ~1, ~68 % of pulls within 1 sigma, ~95 % within 2). The study
is ``coverage_study_rabi_pi_time.py`` in this package (seeds and cases in it;
``python -m kexp.analysis.calibrations.coverage_study_rabi_pi_time``); its
output, 2026-10-09, 300 seeds per row:

    case                     noise         n fail pull std  robust  |p|<1  |p|<2  bias %  rms %
    -------------------------------------------------------------------------------------------
    additive 30, 3 repeats   auto        300    0     1.29    1.34   0.55   0.90  -0.090  0.546
    additive 30, 3 repeats   pooled      300    0     0.97    0.93   0.69   0.96  -0.055  0.435
    additive 30, 3 repeats   unweighted  300    0     0.98    0.97   0.68   0.96  -0.056  0.431
    additive 30, 1 repeat    auto        300    0     1.02    1.01   0.68   0.93  -0.063  0.770
    additive 30, 1 repeat    pooled        0  300      nan     nan    nan    nan    +nan    nan
    additive 30, 1 repeat    unweighted  300    0     1.02    1.01   0.68   0.93  -0.063  0.770
    additive 30, 10 repeats  auto        300    0     1.06    0.97   0.69   0.94  -0.006  0.256
    additive 30, 10 repeats  pooled      300    0     0.94    1.01   0.74   0.96  -0.015  0.236
    additive 30, 10 repeats  unweighted  300    0     0.97    1.00   0.72   0.96  -0.015  0.236
    mult 0.10, 3 repeats     auto        300    0     1.42    1.39   0.51   0.84  -0.031  0.938
    mult 0.10, 3 repeats     pooled      300    0     0.99    1.02   0.68   0.96  +0.055  0.707
    mult 0.10, 3 repeats     unweighted  300    0     0.97    0.96   0.71   0.96  -0.012  0.763
    mult 0.10, 5 repeats     auto        300    0     1.20    1.15   0.60   0.92  -0.058  0.597
    mult 0.10, 5 repeats     pooled      300    0     0.88    0.87   0.73   0.99  -0.046  0.475
    mult 0.10, 5 repeats     unweighted  300    0     0.87    0.87   0.72   0.98  -0.050  0.526
    mult 0.25, 3 repeats     auto        300    0     1.41    1.45   0.49   0.83  -0.204  1.888
    mult 0.25, 3 repeats     pooled      300    0     0.94    0.93   0.72   0.96  -0.132  1.368
    mult 0.25, 3 repeats     unweighted  300    0     0.91    0.93   0.72   0.97  -0.160  1.605
    mult 0.25, 5 repeats     auto        300    0     1.28    1.34   0.56   0.87  -0.055  1.337
    mult 0.25, 5 repeats     pooled      300    0     1.04    1.17   0.65   0.96  -0.019  1.167
    mult 0.25, 5 repeats     unweighted  300    0     0.97    0.88   0.73   0.96  -0.045  1.343

Read: "auto" under-states the error in 5 of the 6 cases with repeats (pull std
1.20-1.42, 49-60 % within 1 sigma); it is calibrated for 10 repeats of additive
noise (1.06), and without repeats it is the unweighted fit. "pooled" and
"unweighted" are calibrated in every case here (pull std 0.87-1.04; the 0.87-0.88
of 10 % multiplicative noise with 5 repeats is slightly conservative); "pooled"
fails outright without repeats. "unweighted" is the default because it works
with and without repeats. Bias is small against the scatter: for "pooled" and
"unweighted" |bias| <= 0.16 % with rms 0.24-1.6 %; "auto" reaches -0.204 %
(rms up to 1.9 %).
(An earlier, unrecorded scratch run with other seeds also showed one
catastrophic "pooled" fit at 10 % multiplicative noise with 5 repeats; this
recorded run does not reproduce it, so it is not counted as evidence here.)

Options: ``signal`` (an attribute path on ``ad``, default ``"atom_number"``),
``xvar`` (name or index of the pulse-length xvar; default: the only one),
``model`` (fit_rabi's, default "auto": decay envelope by AICc) and ``noise``
(passed to fit_rabi), ``figure_path`` (set by the framework).
"""

from __future__ import annotations

import math
import os

import numpy as np

from waxx.calibration.record import CalResult

METHOD = ("waxa.analysis.rabi.fit_rabi; written value pi/omega = 1/(2 f_Rabi) (rate pi time); "
          "unc from the fit covariance")


def _signal(ad, path):
    obj = ad
    for part in str(path).split("."):
        obj = getattr(obj, part)
    return np.asarray(obj, dtype=float)


def _pulse_axis(ad, xvar):
    names = [str(n) for n in ad.xvarnames]
    if len(names) != 1:
        raise ValueError(f"a {len(names)}-xvar run ({names}): this analysis takes a 1-D "
                         f"pulse-length scan")
    if xvar is not None and xvar not in (0, names[0]):
        raise ValueError(f"xvar {xvar!r} is not this run's xvar ({names[0]})")
    return np.asarray(ad.xvars[0], dtype=float), names[0]


def _run_id(ad):
    rid = getattr(getattr(ad, "run_info", None), "run_id", None)
    try:
        return int(np.ravel(rid)[0])
    except (TypeError, ValueError, IndexError):
        return 0


def _fail(key, reason, n_used=0, excluded=None, rid=0):
    return CalResult(key=key, value=math.nan, unc=None, unit="s", run_id=rid, n_used=n_used,
                     excluded=excluded or {"count": 0, "reason": ""}, method=METHOD,
                     fit={"ok": False, "reason": reason}, analysis="rabi_pi_time")


def calibrate(ad, key, *, signal="atom_number", xvar=None, model="auto", noise="unweighted",
              figure_path=None, **opts):
    """CalResult for ``key`` (a pi-time param, seconds) from the Rabi flop in ``ad``."""
    from waxa.analysis.rabi import fit_rabi

    rid = _run_id(ad)
    if opts:
        return _fail(key, f"unknown option(s) {sorted(opts)}", rid=rid)
    try:
        t, tname = _pulse_axis(ad, xvar)
        y = _signal(ad, signal)
    except (AttributeError, ValueError, TypeError) as e:
        return _fail(key, f"cannot read the scan: {e}", rid=rid)
    t, y = t.ravel(), y.ravel()
    if t.shape != y.shape:
        return _fail(key, f"pulse lengths {t.shape} and {signal} {y.shape} do not match", rid=rid)
    good = np.isfinite(t) & np.isfinite(y)
    n_bad = int((~good).sum())
    excluded = {"count": n_bad,
                "reason": f"non-finite pulse length or {signal}" if n_bad else ""}
    n_used = int(good.sum())

    fit = fit_rabi(t[good], y[good], model=model, noise=noise, run_ids=(rid,) if rid else (),
                   labels=(f"run {rid}",) if rid else (), xvarname=tname, signal_name=str(signal),
                   params=getattr(ad, "params", None))
    if not fit.ok:
        return _fail(key, f"Rabi fit failed: {fit.reason}", n_used=n_used, excluded=excluded, rid=rid)

    value = float(fit.t_pi_rate)
    unc = float(fit.t_pi_rate_err)
    if not (math.isfinite(unc) and unc > 0):
        unc = None                     # flagged downstream; never invented
    fitd = {
        "ok": True,
        "model": fit.model,
        "noise": fit.noise,
        "params": {"omega": fit.omega, "f_rabi": fit.f_rabi, "phase": fit.phase,
                   "gamma": fit.gamma, "offsets": list(fit.offsets),
                   "amplitudes": list(fit.amplitudes)},
        "errors": {"omega": fit.omega_err, "f_rabi": fit.f_rabi_err, "phase": fit.phase_err,
                   "gamma": fit.gamma_err, "t_pi_rate": fit.t_pi_rate_err},
        "goodness": {"chi2": fit.chi2, "dof": fit.dof, "chi2r": fit.chi2r,
                     "errors_scaled": fit.errors_scaled, "aicc": dict(fit.aicc),
                     "n_points": fit.n_points, "n_periods": fit.n_periods},
        "warnings": list(fit.warnings),
        "also": {"t_pi_commanded": fit.t_pi, "t_pi_commanded_err": fit.t_pi_err,
                 "t_dead": fit.t_dead, "t_dead_err": fit.t_dead_err},
        "signal": str(signal),
        "xvar": tname,
    }
    written_fig = None
    if figure_path:
        try:
            written_fig = _figure(fit, value, unc, key, ad, figure_path)
        except Exception as e:                     # a figure never costs the number
            fitd["figure_error"] = f"{type(e).__name__}: {e}"
    return CalResult(key=key, value=value, unc=unc, unit="s", run_id=rid, n_used=n_used,
                     excluded=excluded, method=METHOD, fit=fitd, figure_path=written_fig,
                     analysis="rabi_pi_time")


def _needs_images(opts):
    """The default signal (atom_number) comes from the camera images; a
    DataVault signal ("data.<key>", e.g. data.apd) does not."""
    return not str(opts.get("signal", "atom_number")).startswith("data.")


calibrate.needs_images = _needs_images


def _figure(fit, value, unc, key, ad, path):
    """Data, fit and residuals (waxa plot_rabi) with the written value marked;
    saved with the Agg canvas (no pyplot window, safe off the main thread)."""
    from matplotlib.figure import Figure
    from waxa.analysis.rabi.plotting import plot_rabi

    fig = Figure(figsize=(8, 5.5))
    ax = fig.add_subplot(1, 1, 1)
    in_use = getattr(getattr(ad, "params", None), key, None)
    try:
        in_use = float(np.ravel(in_use)[0]) if in_use is not None else None
    except (TypeError, ValueError, IndexError):
        in_use = None
    plot_rabi(fit, ax=ax, residuals=False, reference=in_use)
    try:                                           # the x unit plot_rabi chose
        from waxa.plotting.units import detect_unit
        allt = np.concatenate([d.tu for d in fit.datasets])
        unit, mult, _ = detect_unit(xvarnames=[fit.xvarname], xvar_values=allt,
                                    params_obj=fit.params)
    except Exception:
        unit, mult = "us", 1e6
    ax.axvline(value * mult, color="C4", lw=1.6)
    u = f" +/- {unc * mult:.4g}" if unc is not None else " (no uncertainty)"
    ax.plot([], [], "-", color="C4", label=f"{key} = pi/Omega = {value * mult:.6g}{u} {unit}")
    ax.legend(fontsize=8)
    rid = ", ".join(map(str, fit.run_ids)) or "?"
    ax.set_title(f"run {rid} | {key}: rate pi time 1/(2 f_Rabi) | f_Rabi = "
                 f"{fit.f_rabi / 1e3:.3f} +/- {fit.f_rabi_err / 1e3:.3f} kHz", fontsize=9)
    fig.tight_layout()
    from waxx.calibration.analysis import figure_tmp_path
    path = str(path)
    tmp = str(figure_tmp_path(path))       # <dir>/.tmp/...: never a half-written figure at path
    try:
        fig.savefig(tmp, dpi=120)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path
