"""The interleaved readout calibration of a feedback run, on the host: the
record and evaluation of the sub-scan's up / down points (phase 1).

The run's sub-scan (``FeedbackExpt._declare_readout_calibration``, waxx
``SubScan``) takes a pair of readout points -- the prepared state
(``t_raman_pulse`` 0, all up) and after a resonant pi (all down) -- before
the first data shot and every ``cal_every_n_shots`` data shots, the readout
mode (the data shot's, the calibration run's) alternating between events.
This object hangs off the sub-scan's host hooks:

* ``on_point(i, ok)`` after every point: when a pair is complete, its
  per-kind means and contrast go into the log (``cal_scan['log']['pairs']``);
* ``finish_run()`` at the end of the run (the kernel is done): for every
  readout mode, the same estimator the calibration runs use
  (``waxa.analysis.readout.calibrate_readout``, ``sz_source='params'``,
  linear) on all the mode's points, then the drivers' sanity rules and the
  "suspicious against the constants in force" rules, into
  ``cal_scan['log']['windows']``. The decision is always ``evaluated_only``:
  nothing here changes a constant the kernel uses, and nothing is written
  back; the driver does that between runs from ``ad.cal``
  (``apd_state_mapping --part cal``).

Nothing in here raises into the run: the hooks are called from the
sub-scan, which logs an exception and goes on; an evaluation that fails
leaves a window with ``status: failed`` and the traceback text.
"""
import inspect
import re
import time
import traceback

import numpy as np

# the constants the readout uses (expt_params_feedback.py), with t_pi / offset
FIELDS = ("v_apd_all_up", "v_apd_all_down", "n_photons_per_shot", "std_n_photons_per_shot",
          "feedback_measurement_midpoint_fraction", "t_raman_pi_pulse", "t_raman_pulse_offset")

# the rules the night drivers apply to a calibration run (fb_driver.calibrate,
# 2026-10-06/07, user-set): sanity, then "suspicious" against the stored values
RULES = dict(
    min_contrast_v=0.015, max_endpoint_err_v=0.010, n_photons_range=(200.0, 2000.0),
    std_over_n_range=(0.05, 0.6), suspicious_dv_v=0.005, suspicious_dc_frac=0.15,
    sigma_factor=2.5 * np.sqrt(2.0),
)


def _tags_from_params_file(params_obj, keys):
    """The active line's tag (``#<run>, <date> ...``) of each key in the
    params file that defines ``params_obj``'s class, or '' when not found."""
    out = {k: "" for k in keys}
    try:
        path = inspect.getsourcefile(type(params_obj))
        text = open(path, encoding="utf-8").read()
    except Exception:
        return out
    for k in keys:
        m = re.findall(r"^[ \t]*self\." + re.escape(k) + r"[ \t]*=[ \t]*[^#\n]*#(.*)$", text, re.M)
        if len(m) == 1:
            out[k] = m[0].strip()
    return out


def _err_text(exc):
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-1500:]


class ReadoutCalibrationRecord:

    def __init__(self, expt, sub, n_boot=200, min_pairs=3):
        self.expt = expt
        self.sub = sub
        self.n_boot = int(n_boot)
        self.min_pairs = int(min_pairs)
        self.start = self._start_constants()
        self.pairs = []
        sub.log["start"] = self.start
        sub.log["rules"] = {k: (list(v) if isinstance(v, tuple) else float(v)) for k, v in RULES.items()}
        sub.log["pairs"] = self.pairs
        sub.log["windows"] = []
        sub.log["decision_policy"] = "evaluated_only (phase 1: nothing applied in the run)"

    # ---------------------------------------------------------------- start

    def _start_constants(self):
        p = self.expt.p
        values = {}
        for k in FIELDS:
            try:
                values[k] = float(np.ravel(getattr(p, k))[0])
            except Exception:
                values[k] = None
        return {"values": values, "source": _tags_from_params_file(p, FIELDS), "t": time.time()}

    # ----------------------------------------------------------------- data

    def _arrays(self):
        d = self.sub.data
        apd = np.asarray(d.apd._run_data, dtype=float)
        if apd.ndim == 1:
            apd = apd[:, None]
        t = np.asarray(self.sub.scan_xvars[0].values, dtype=float).ravel()
        status = np.asarray(d.status._run_data).ravel()
        tm = np.asarray(d.time._run_data, dtype=float).ravel()
        mode_dc = vars(d).get("cal_readout_mode")
        mode = (np.asarray(mode_dc._run_data, dtype=float).ravel() if mode_dc is not None
                else np.zeros(t.size))
        return t, apd, status, tm, mode

    @staticmethod
    def _is_up(t):
        return np.isclose(t, 0.0)

    # ------------------------------------------------------------ per point

    def on_point(self, i, ok):
        """After point ``i``: when it completes an event (a pair), log the
        pair's per-kind means (all reads), its contrast and time."""
        npe = int(self.sub.n_points_per_event or 1)
        if (int(i) + 1) % npe != 0:
            return
        t, apd, status, tm, mode = self._arrays()
        slots = list(range(int(i) + 1 - npe, int(i) + 1))
        good = [s for s in slots if status[s] == 1 and np.all(np.isfinite(apd[s]))]
        up = [s for s in good if self._is_up(t[s])]
        down = [s for s in good if not self._is_up(t[s])]
        v_up = float(np.mean(apd[up])) if up else None
        v_down = float(np.mean(apd[down])) if down else None
        entry = {"event": int(i) // npe, "slots": slots, "n_ok": len(good),
                 "mode": float(mode[slots[0]]), "v_up": v_up, "v_down": v_down,
                 "contrast": (v_up - v_down) if (v_up is not None and v_down is not None) else None,
                 "t": float(np.nanmax(tm[slots])) if np.any(np.isfinite(tm[slots])) else None,
                 "order": "up_first" if (slots and self._is_up(t[slots[0]])) else "down_first"}
        self.pairs.append(entry)

    # -------------------------------------------------------------- the end

    def finish_run(self):
        """One window per readout mode over all its usable points: the
        estimator, the rules, the derived constants -- logged, not applied."""
        t, apd, status, tm, mode = self._arrays()
        modes = sorted({float(m) for m in np.unique(mode)}) or [0.0]
        for m in modes:
            try:
                self.sub.log["windows"].append(self._evaluate(m, t, apd, status, tm, mode))
            except Exception as e:
                self.sub.log["windows"].append({"mode": m, "status": "failed", "error": _err_text(e)})
                print(f"[readout cal] !! evaluation of mode {m:g} failed (logged): {e!r}")
        done = [w for w in self.sub.log["windows"] if w.get("status") == "evaluated_only"]
        self.sub.log["eval_summary"] = {
            "n_pairs_logged": len(self.pairs), "n_windows": len(self.sub.log["windows"]),
            "n_evaluated": len(done),
            "n_failed": sum(1 for w in self.sub.log["windows"] if w.get("status") == "failed"),
            "n_too_few": sum(1 for w in self.sub.log["windows"] if w.get("status") == "too_few_points"),
            "n_sane": sum(1 for w in done if w.get("sane")),
            "n_suspicious": sum(1 for w in done if w.get("suspicious")),
        }

    def _evaluate(self, m, t, apd, status, tm, mode):
        from waxa.analysis.readout import calibrate_readout, endpoint_groups
        sel = (status == 1) & np.all(np.isfinite(apd), axis=1) & np.isclose(mode, m)
        n_up, n_down = int(np.sum(sel & self._is_up(t))), int(np.sum(sel & ~self._is_up(t)))
        base = {"mode": float(m), "slots": np.flatnonzero(sel).tolist(), "n_up": n_up, "n_down": n_down,
                "n_left_out": int(np.sum(~sel & (status != 0))), "t_eval": time.time()}
        if min(n_up, n_down) < self.min_pairs:
            return dict(base, status="too_few_points", min_pairs=self.min_pairs)
        s = self.start["values"]
        cal = calibrate_readout(t[sel], apd[sel], run=None,
                                timestamps=tm[sel] if np.all(np.isfinite(tm[sel])) else None,
                                t_pi=s.get("t_raman_pi_pulse"), t_offset=s.get("t_raman_pulse_offset") or 0.0,
                                sz_source="params", degree=1, n_boot=self.n_boot, signal_name="APD",
                                xvarname="t_raman_pulse", context=f"in-run sub-scan, readout mode {m:g}")
        if not cal.ok:
            return dict(base, status="failed", error=f"calibrate_readout: {cal.reason}")
        pooled = cal.pooled
        prop = cal.proposal or {}
        est = {"v_up": float(pooled.v_up), "v_up_err": float(pooled.v_up_err),
               "v_down": float(pooled.v_down), "v_down_err": float(pooled.v_down_err),
               "contrast": float(pooled.contrast), "contrast_err": float(pooled.contrast_err),
               "sigma_v": float(prop.get("sigma_signal", np.nan)),
               "midpoint": 0.5, "pulses_used": list(cal.pulses_used)}
        c, c0 = est["contrast"], None
        if s.get("v_apd_all_up") is not None and s.get("v_apd_all_down") is not None:
            c0 = s["v_apd_all_up"] - s["v_apd_all_down"]
        n0 = s.get("n_photons_per_shot")
        est["n_photons_new"] = float(n0 * c / c0) if (n0 and c0) else None
        est["std_n_new"] = (float(est["n_photons_new"] * est["sigma_v"] / c)
                            if (est["n_photons_new"] and c and np.isfinite(est["sigma_v"])) else None)
        # the drivers' sanity rules
        R = RULES
        checks = []
        if not (abs(c) >= R["min_contrast_v"]):
            checks.append(f"contrast {c * 1e3:.2f} mV below {R['min_contrast_v'] * 1e3:.0f} mV")
        for k in ("v_up_err", "v_down_err"):
            if not (est[k] <= R["max_endpoint_err_v"]):
                checks.append(f"{k} {est[k] * 1e3:.2f} mV > {R['max_endpoint_err_v'] * 1e3:.0f} mV")
        n_new = est["n_photons_new"]
        if n_new is not None and not (R["n_photons_range"][0] <= n_new <= R["n_photons_range"][1]):
            checks.append(f"n_photons {n_new:.1f} outside {R['n_photons_range']}")
        if n_new and est["std_n_new"] and not (R["std_over_n_range"][0] <= est["std_n_new"] / n_new
                                                <= R["std_over_n_range"][1]):
            checks.append(f"std/n {est['std_n_new'] / n_new:.3f} outside {R['std_over_n_range']}")
        groups = {}
        per_shot = np.mean(apd[sel], axis=1)
        for name, mask in (("up", self._is_up(t[sel])), ("down", ~self._is_up(t[sel]))):
            flag, detail = endpoint_groups(per_shot[mask], c)
            groups[name] = dict(detail, flag=bool(flag))
            if flag:
                checks.append(f"{name} shots split into two groups ({detail['n_beyond']} beyond "
                              f"{detail['limit'] * 1e3:.1f} mV)")
        # suspicious against the constants in force (the run-start values)
        susp = []
        if c0:
            f = R["sigma_factor"]
            du = (est["v_up"] - s["v_apd_all_up"]) * 1e3
            dd = (est["v_down"] - s["v_apd_all_down"]) * 1e3
            lim_u = max(R["suspicious_dv_v"] * 1e3, f * est["v_up_err"] * 1e3)
            lim_d = max(R["suspicious_dv_v"] * 1e3, f * est["v_down_err"] * 1e3)
            rc = (c - c0) / c0
            lim_c = max(R["suspicious_dc_frac"], f * est["contrast_err"] / abs(c)) if c else R["suspicious_dc_frac"]
            if abs(du) > lim_u:
                susp.append(f"V_up moved {du:+.2f} mV (limit {lim_u:.1f})")
            if abs(dd) > lim_d:
                susp.append(f"V_down moved {dd:+.2f} mV (limit {lim_d:.1f})")
            if not abs(rc) <= lim_c:
                susp.append(f"contrast changed {rc * 100:+.1f} % (limit {lim_c * 100:.0f} %)")
            est["d_v_up_mv"], est["d_v_down_mv"], est["d_contrast_frac"] = float(du), float(dd), float(rc)
        return dict(base, status="evaluated_only", decision="evaluated_only", estimate=est,
                    sane=not checks, sanity_failures=checks, suspicious=bool(susp),
                    suspicious_reasons=susp, groups=groups, warnings=list(cal.warnings),
                    constants_in_force=dict(s))
