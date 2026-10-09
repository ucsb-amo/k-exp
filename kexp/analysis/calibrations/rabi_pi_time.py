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
``sigma_omega`` from the covariance (scaled by sqrt(chi2/dof) when that is
above 1, as fit_rabi does). When the fit gives no finite uncertainty, ``unc`` is
None (and the result is flagged); none is made up.

Shots with a non-finite pulse length or signal are left out of the fit and
counted in ``excluded``; nothing else is left out.

Options: ``signal`` (an attribute path on ``ad``, default ``"atom_number"``),
``xvar`` (name or index of the pulse-length xvar; default: the only one),
``model`` / ``noise`` (passed to fit_rabi; defaults "auto"), ``figure_path``
(set by the framework).
"""

from __future__ import annotations

import math

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


def calibrate(ad, key, *, signal="atom_number", xvar=None, model="auto", noise="auto",
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
        _, mult, _ = detect_unit(xvarnames=[fit.xvarname], xvar_values=allt, params_obj=fit.params)
    except Exception:
        mult = 1e6
    ax.axvline(value * mult, color="C4", lw=1.6)
    u = f" +/- {unc * 1e6:.4f}" if unc is not None else " (no uncertainty)"
    ax.plot([], [], "-", color="C4", label=f"{key} = pi/Omega = {value * 1e6:.4f}{u} us")
    ax.legend(fontsize=8)
    rid = ", ".join(map(str, fit.run_ids)) or "?"
    ax.set_title(f"run {rid} | {key}: rate pi time 1/(2 f_Rabi) | f_Rabi = "
                 f"{fit.f_rabi / 1e3:.3f} +/- {fit.f_rabi_err / 1e3:.3f} kHz", fontsize=9)
    fig.tight_layout()
    fig.savefig(str(path), dpi=120)
    return str(path)
