"""APD voltage -> spin state: the feedback readout calibration from APD-vs-state runs.

K-machine wrapper around :func:`waxa.analysis.readout.calibrate_readout` for the
calibration experiment
``kexp/experiments/HF_experiments/feedback/calibrations/apd_voltage_vs_state_2.py``
(class ``sigma_z``): a Raman pulse of scanned length ``t_raman_pulse`` from ``|up>``,
then ``N_pulses`` integrated dispersive APD pulses (``ad.data.apd``, shape
(n_shots, N_pulses)), with the photodiode scope trace saved as ``scope_data['PD']``.
It replaces the notebook ``k-jam/analysis/artisinal/apd_pulse_analysis_interpolate.ipynb``
(whose math is ported into ``waxa.analysis.readout``) and knows what waxa does not:
which params hold the calibration, the scope gain chain, the K39 D2 photon energy.

Command line (writes only under ``--out``; data are loaded read-only)::

    python -m kexp.analysis.apd_state_mapping 83148 83149 83150 --out C:\\lab\\skynet_log\\outputs\\x
    python -m kexp.analysis.apd_state_mapping 83150 --skip-first-pulse --no-scope

In Python::

    from kexp.analysis.apd_state_mapping import apd_state_mapping
    m = apd_state_mapping([83148, 83149, 83150])
    print(m.report()); m.cal.plot_pulses(); print(m.params_block())

The params it proposes (``expt_params_feedback.py``; read by ``kexp.base.feedback``):

    v_apd_all_up / v_apd_all_down     APD volts at S_z = +1 / -1
    feedback_measurement_midpoint_fraction
                                      0.5 = linear map; else the quadratic remap
    n_photons_per_shot                photons in one pulse, up minus down (scope)
    std_n_photons_per_shot            the likelihood sigma, in the same photon units:
                                      n_photons_per_shot * sigma_V / (v_up - v_down)

Only the ratio ``std_n_photons_per_shot / n_photons_per_shot`` enters the fixed-sigma
likelihood (``Feedback.generate_posterior``), and it is set here from the noise of the
APD value the feedback actually reads, per single pulse, at the NOISIER endpoint.

Every readout pulse is used by default, because the feedback reads every pulse (pulse 1
included) with one calibration and one sigma.  ``--skip-first-pulse`` reproduces the
notebook's ``SKIP_FIRST_PULSE = True``; the per-pulse table and the "pulse p minus the
others" test show whether pulse 1 differs.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np

# Scope chain from the notebook's options cell (cell 4).  These are NOT recorded in the
# run file: if the SRS gain or the termination changed, the photon number is wrong.
SCOPE_CHAIN = dict(
    gain_from_apd_to_scope=500.0,      # SRS gain from APD output to scope input
    voltage_div_termination=1.0,       # 2.0 for 50-ohm termination, 1.0 for high-Z
    responsivity_volts_per_watt=26.5e6,
)
SCOPE_LABEL = "PD"
XVAR = "t_raman_pulse"
FEEDBACK_FIELDS = ("t_img_pulse", "amp_imaging", "v_apd_all_up", "v_apd_all_down", "n_photons_per_shot",
                   "std_n_photons_per_shot", "feedback_measurement_midpoint_fraction")
# params that must be the same in every run that is pooled
CONSISTENCY_PARAMS = ("t_raman_pi_pulse", "t_raman_pulse_offset", "amp_imaging", "t_pci_pulse", "N_pulses",
                      "t_between_pulses_mu", "phase_slm_mask", "frequency_detuned_hf_midpoint",
                      "frequency_raman_transition", "fraction_power_raman", "t_tweezer_hold", "N_repeats")
OUTPUT_ROOT = r"C:\lab\skynet_log\outputs"   # the only place this CLI writes (lab-rules section 1)
DEFAULT_OUT = os.path.join(OUTPUT_ROOT, "apd_state_mapping")


def photon_energy():
    """K39 D2 photon energy (J), as the notebook computes it (cell 16)."""
    from kamo import constants as c, Potassium39
    wavelength = Potassium39().getTransitionWavelength(4, 0, 1 / 2, 4, 1, 3 / 2)
    return float(c.h * c.c / wavelength)


def volt_seconds_to_photons(chain=None):
    """Scope V s -> photons: 1 / (SRS gain * responsivity / termination * photon energy)."""
    ch = dict(SCOPE_CHAIN if chain is None else chain)
    return 1.0 / (ch["gain_from_apd_to_scope"] * (ch["responsivity_volts_per_watt"] / ch["voltage_div_termination"])
                  * photon_energy())


def _scalar(v):
    a = np.asarray(v)
    return float(a.ravel()[0]) if a.size else np.nan


def _run_label(ids):
    ids = list(ids)
    if len(ids) > 1 and ids == list(range(ids[0], ids[0] + len(ids))):
        return f"{ids[0]}-{ids[-1]}"
    return ",".join(map(str, ids))


# ------------------------------------------------------------------ loading
def load_run(run_id, with_scope=True, scope_windows=None):
    """One run, read-only: (dict of per-shot arrays, params, ScopePulses or None)."""
    from waxa import atomdata
    from waxa.analysis.readout import integrate_scope_pulses

    ad = atomdata(int(run_id), roi_id="auto", lite=False)
    names = [str(n) for n in ad.xvarnames]
    if names != [XVAR]:
        raise ValueError(f"run {run_id}: expected the single xvar {XVAR!r}, got {names}")
    t = np.asarray(ad.xvars[0], float).ravel()
    apd = np.asarray(ad.data.apd, float)
    if apd.ndim == 1:
        apd = apd[:, None]
    if apd.shape[0] != t.size:
        raise ValueError(f"run {run_id}: data.apd has {apd.shape[0]} shots, the xvar {t.size}")
    ts = np.asarray(getattr(ad, "timestamp_shot_end", np.array([])), float).ravel()
    rid = int(np.ravel(ad.run_info.run_id)[0])
    info = dict(run_id=rid, datetime=_decode(getattr(ad.run_info, "run_datetime_str", "")),
                experiment=_expt_class(ad), timestamps=ts if ts.size == t.size else None,
                params={k: _scalar(getattr(ad.p, k)) for k in CONSISTENCY_PARAMS if hasattr(ad.p, k)},
                data_complete=getattr(ad, "data_complete", None))
    scope = None
    if with_scope:
        sd = getattr(ad, "scope_data", None)
        if sd is None or SCOPE_LABEL not in sd:
            info["scope_missing"] = True
        else:
            tr = sd[SCOPE_LABEL][0]
            scope = integrate_scope_pulses(tr.t, tr.v, t_duration=float(ad.p.t_pci_pulse), n_pulses=apd.shape[1],
                                           t_between_pulses=float(ad.p.t_between_pulses_mu) * 1e-9,
                                           **(scope_windows or {}))
    return dict(t=t, apd=apd, info=info), ad.params, scope


def _decode(s):
    return s.decode() if isinstance(s, (bytes, bytearray)) else str(s)


def _expt_class(ad):
    code = getattr(getattr(ad, "experiment_code", None), "experiment", "") or ""
    for line in str(code).splitlines():
        if line.startswith("class "):
            return line.split("(")[0].replace("class ", "").strip()
    return ""


# ------------------------------------------------------------------ result
@dataclass(eq=False)
class ApdStateMapping:
    cal: object                                   # waxa ReadoutCalibration
    runs: list = field(default_factory=list)      # per-run info dicts
    current: dict = field(default_factory=dict)   # the params file's values now
    current_opx: dict = field(default_factory=dict)
    param_warnings: tuple = ()
    date: str = ""

    @property
    def run_ids(self):
        return tuple(r["run_id"] for r in self.runs)

    def proposed_values(self):
        """{param: (old, new, how)} for the feedback params this calibration sets."""
        p = self.cal.proposal
        if not p:
            return {}
        out = {
            "v_apd_all_up": (self.current.get("v_apd_all_up"), p["v_up"],
                             f"S_z=+1 of the degree-{p['degree']} single-shot fit, +/- {p['v_up_err']:.2g} V "
                             f"(+/- {p['v_up_err_with_run_scatter']:.2g} with run-to-run scatter)"),
            "v_apd_all_down": (self.current.get("v_apd_all_down"), p["v_down"],
                               f"S_z=-1 of the degree-{p['degree']} single-shot fit, +/- {p['v_down_err']:.2g} V "
                               f"(+/- {p['v_down_err_with_run_scatter']:.2g} with run-to-run scatter)"),
            "feedback_measurement_midpoint_fraction": (
                self.current.get("feedback_measurement_midpoint_fraction"), p["midpoint"],
                "linear map (quadratic term not resolved)" if p["degree"] == 1
                else f"quadratic fit, +/- {p['midpoint_err']:.2g}"),
        }
        if "n_photons_per_pulse" in p:
            n_new = p["n_photons_per_pulse"]
            out["n_photons_per_shot"] = (self.current.get("n_photons_per_shot"), n_new,
                                         f"scope integral, up minus down per pulse, +/- {p['n_photons_per_pulse_err']:.2g}"
                                         " (SRS gain etc. from the notebook, not from the run)")
        else:
            # no usable scope photon number: keep N; only std/N enters the likelihood, so the
            # std below carries the whole noise calibration in N's units
            n_new = self.current.get("n_photons_per_shot")
        if n_new is not None and np.isfinite(n_new):
            out["std_n_photons_per_shot"] = (self.current.get("std_n_photons_per_shot"),
                                             float(n_new) * p["sigma_fraction"],
                                             f"n_photons_per_shot * sigma_V / v_range = {n_new:.4g} * "
                                             f"{p['sigma_signal']*1e3:.2f} mV / {p['v_range']*1e3:.2f} mV "
                                             f"({p['sigma_signal_source']})")
        return out

    def params_block(self, date=None, sig=5):
        """Lines for expt_params_feedback.py, lab convention: old value commented out, new
        value tagged '#runs, date'.  For review; never written anywhere by this module."""
        date = date or self.date or datetime.date.today().isoformat()
        tag = f"#{_run_label(self.run_ids)}, {date}"
        lines = [f"# APD readout calibration, runs {_run_label(self.run_ids)} ({self.runs[0]['experiment']}), "
                 f"python -m kexp.analysis.apd_state_mapping"]
        if "n_photons_per_pulse" not in self.cal.proposal:
            lines.append("# n_photons_per_shot kept: no valid scope photon number for these runs; only "
                         "std_n_photons_per_shot / n_photons_per_shot enters the likelihood")
        for k, (old, new, how) in self.proposed_values().items():
            if old is not None:
                lines.append(f"# self.{k} = {old!r}")
            lines.append(f"self.{k} = {new:.{sig}g} {tag}  # {how}")
        return "\n".join(lines)

    def report(self):
        L = [self.cal.summary()]
        L.append("runs:")
        for r in self.runs:
            L.append(f"  {r['run_id']}  {r['datetime']}  {r['experiment']}  "
                     f"{'(scope missing)' if r.get('scope_missing') else ''}")
        for w in self.param_warnings:
            L.append(f"  PARAM WARNING: {w}")
        L.append("current feedback params (expt_params_feedback.py): "
                 + ", ".join(f"{k}={v!r}" for k, v in self.current.items()))
        if self.current_opx:
            L.append("OPX params (expt_params_feedback_opx.py, OPX demod volts -- NOT the ARTIQ integrator scale "
                     "this run measures; not proposed): " + ", ".join(f"{k}={v!r}" for k, v in self.current_opx.items()))
        L.append("proposed (review before applying):")
        L.append(self.params_block())
        return "\n".join(L)

    def to_dict(self):
        return dict(run_ids=list(self.run_ids), runs=[{k: (v.tolist() if isinstance(v, np.ndarray) else v)
                                                      for k, v in r.items()} for r in self.runs],
                    current=self.current, current_opx=self.current_opx, param_warnings=list(self.param_warnings),
                    proposed={k: dict(old=o, new=n, how=h) for k, (o, n, h) in self.proposed_values().items()},
                    params_block=self.params_block(), scope_chain=SCOPE_CHAIN, calibration=self.cal.to_dict())


def current_feedback_params():
    """The values the feedback params files hold now (instantiated read-only)."""
    cur, opx = {}, {}
    try:
        from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams
        p = ExptParams()
        cur = {k: float(getattr(p, k)) for k in FEEDBACK_FIELDS if hasattr(p, k)}
    except Exception as e:                       # report, do not guess
        cur = {"error": repr(e)}
    try:
        from kexp.experiments.HF_experiments.feedback.expt_params_feedback_opx import ExptParams as OPX
        q = OPX()
        opx = {k: float(getattr(q, k)) for k in ("v_apd_all_up_opx", "v_apd_all_down_opx",
                                                 "std_photon_fraction_opx") if hasattr(q, k)}
    except Exception as e:
        opx = {"error": repr(e)}
    return cur, opx


def apd_state_mapping(run_ids, *, skip_first_pulse=False, pulses=None, sz_source="fit", degree="auto",
                      with_scope=True, scope_windows=None, n_boot=2000, seed=0, date=None) -> ApdStateMapping:
    """Load the runs (read-only) and calibrate the APD readout; see the module docstring."""
    from waxa.analysis.readout import calibrate_readout, ScopePulses

    run_ids = [int(r) for r in run_ids]
    T, A, R, TS, infos, scopes, params0 = [], [], [], [], [], [], None
    for rid in run_ids:
        d, prm, sc = load_run(rid, with_scope=with_scope, scope_windows=scope_windows)
        params0 = params0 if params0 is not None else prm
        T.append(d["t"]); A.append(d["apd"]); R.append(np.full(d["t"].size, d["info"]["run_id"]))
        TS.append(d["info"]["timestamps"]); infos.append(d["info"]); scopes.append(sc)
    P = {a.shape[1] for a in A}
    if len(P) != 1:
        raise ValueError(f"runs disagree on the number of APD pulses: {sorted(P)}")
    P = P.pop()
    pw = []
    for k in CONSISTENCY_PARAMS:
        vals = [r["params"].get(k) for r in infos]
        vals_f = [v for v in vals if v is not None]
        if vals_f and not np.allclose(vals_f, vals_f[0], rtol=1e-9, atol=0, equal_nan=True):
            pw.append(f"{k} differs between runs: " + ", ".join(f"{r['run_id']}: {v}" for r, v in zip(infos, vals)))
    t = np.concatenate(T)
    apd = np.concatenate(A)
    run = np.concatenate(R)
    ts = np.concatenate(TS) if all(x is not None for x in TS) else None
    if pulses is not None:
        used = [int(p) - 1 for p in pulses]
    else:
        used = list(range(1 if (skip_first_pulse and P > 1) else 0, P))
    scope = None
    if with_scope and all(s is not None for s in scopes):
        scope = ScopePulses(integral=np.concatenate([s.integral for s in scopes]),
                            level=np.concatenate([s.level for s in scopes]),
                            baseline=np.concatenate([s.baseline for s in scopes]),
                            valid=np.concatenate([s.valid for s in scopes]),
                            pulse0_edge=scopes[0].pulse0_edge, pulse0_start=scopes[0].pulse0_start,
                            pulse0_start_auto=scopes[0].pulse0_start_auto, t_duration=scopes[0].t_duration,
                            t_between_pulses=scopes[0].t_between_pulses, windows=scopes[0].windows,
                            warnings=tuple(f"run {i['run_id']}: {w}" for i, s in zip(infos, scopes)
                                           for w in s.warnings),
                            problems=tuple(f"run {i['run_id']}: {p}" for i, s in zip(infos, scopes)
                                           for p in s.problems))
        starts = [s.pulse0_start for s in scopes]
        if np.ptp(starts) > 50e-9:
            pw.append("the detected optical start of pulse 0 differs between runs by "
                      f"{np.ptp(starts)*1e9:.0f} ns: " + ", ".join(f"{s*1e6:.3f} us" for s in starts))
    elif with_scope:
        pw.append("scope trace missing in at least one run: no photon number")
    p0 = infos[0]["params"]
    context = (f"amp_imaging {p0.get('amp_imaging')}, t_pci_pulse {p0.get('t_pci_pulse', np.nan)*1e6:.2f} us, "
               f"phase_slm_mask {p0.get('phase_slm_mask', np.nan)/np.pi:.3f} pi, "
               f"t_raman_pi_pulse {p0.get('t_raman_pi_pulse', np.nan)*1e6:.4f} us")
    cal = calibrate_readout(t, apd, run=run, run_ids=tuple(i["run_id"] for i in infos), timestamps=ts,
                            t_pi=p0.get("t_raman_pi_pulse"), t_offset=p0.get("t_raman_pulse_offset", 0.0) or 0.0,
                            sz_source=sz_source, pulses_used=used, degree=degree, scope=scope,
                            scope_to_photons=volt_seconds_to_photons() if scope is not None else None,
                            n_boot=n_boot, seed=seed, signal_name="APD", xvarname=XVAR, params=params0,
                            context=context)
    cur, opx = current_feedback_params()
    return ApdStateMapping(cal=cal, runs=infos, current=cur, current_opx=opx, param_warnings=tuple(pw),
                           date=date or datetime.date.today().isoformat())


# ------------------------------------------------------------------ CLI
def _check_out_dir(path):
    """Allow-list: outputs go only inside OUTPUT_ROOT (a relative path is taken
    relative to it)."""
    p = path if os.path.isabs(path) else os.path.join(OUTPUT_ROOT, path)
    p = os.path.realpath(p)
    root = os.path.realpath(OUTPUT_ROOT)
    if os.path.normcase(p) != os.path.normcase(root) and \
            not os.path.normcase(p).startswith(os.path.normcase(root) + os.sep):
        raise SystemExit(f"--out must be inside {OUTPUT_ROOT}: {path}")
    return p


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m kexp.analysis.apd_state_mapping",
                                 description="APD voltage -> spin state calibration from APD-vs-state runs "
                                             "(apd_voltage_vs_state_2.py). Loads read-only; writes only to --out.")
    ap.add_argument("runs", type=int, nargs="+", help="run ids (pooled; the agreement tests say whether that is fair)")
    ap.add_argument("--out", default=None,
                    help=f"directory for the JSON and PNG figures, inside {OUTPUT_ROOT} (relative paths are taken "
                         f"relative to it; default {DEFAULT_OUT})")
    ap.add_argument("--skip-first-pulse", action="store_true",
                    help="leave pulse 1 out of the pooled numbers (the notebook's SKIP_FIRST_PULSE); default: every "
                         "pulse, as the feedback reads every pulse")
    ap.add_argument("--pulses", type=int, nargs="+", default=None, help="1-based pulses to average (overrides)")
    ap.add_argument("--sz-source", default="fit", choices=["fit", "params"],
                    help="S_z per shot from the joint Rabi fit (default) or from t_raman_pi_pulse/offset")
    ap.add_argument("--degree", default="auto", choices=["auto", "1", "2"],
                    help="S_z response degree; auto = 2 only if the quadratic term is resolved")
    ap.add_argument("--no-scope", action="store_true", help="skip the scope photon number")
    ap.add_argument("--bootstrap", type=int, default=2000, help="bootstrap resamples for the noise intervals")
    ap.add_argument("--date", default=None, help="date for the params tag (default today)")
    ap.add_argument("--show", action="store_true", help="show the figures")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    out = _check_out_dir(args.out or DEFAULT_OUT)
    import matplotlib
    if not args.show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    deg = args.degree if args.degree == "auto" else int(args.degree)
    m = apd_state_mapping(args.runs, skip_first_pulse=args.skip_first_pulse, pulses=args.pulses,
                          sz_source=args.sz_source, degree=deg, with_scope=not args.no_scope,
                          n_boot=args.bootstrap, date=args.date)
    print(m.report())
    if not m.cal.ok:
        return 1
    stem = f"apd_state_mapping_{_run_label(m.run_ids).replace(',', '_')}"
    figs = [("pulses", m.cal.plot_pulses()[0]), ("summary", m.cal.plot_summary()[0])]
    if out:
        os.makedirs(out, exist_ok=True)
        jpath = os.path.join(out, stem + ".json")
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(m.to_dict(), fh, indent=1, default=lambda o: o.tolist() if isinstance(o, np.ndarray)
                      else (float(o) if isinstance(o, np.floating) else str(o)))
        print(f"json: {jpath}")
        for name, fig in figs:
            path = os.path.join(out, f"{stem}_{name}.png")
            fig.savefig(path, dpi=130, bbox_inches="tight")
            print(f"figure: {path}")
    if args.show:
        plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
