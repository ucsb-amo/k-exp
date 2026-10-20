"""Tweezer PID2-vs-PID1 photodiode calibration -> kexp.calibrations.tweezer.

The experiment (kexp/experiments/calibration/tweezer_pid2_vs_pid1.py) holds
the tweezer on the PID1 (high-power) servo with PID2 disabled and reads both
servo photodiodes on the Sampler (ch0 = PID1 PD, ch1 = PID2 PD). It first
steps the PID1 setpoint up to find the highest setpoint at which the PID2 PD
does not saturate, then sweeps the setpoint from there down to the minimum.

This module fits the sweep: PID2 PD voltage = slope * PID1 setpoint +
intercept, which is ``tweezer_vpd1_to_vpd2`` (vpd2_per_vpd1_slope,
v_pd2_y_intercept). Every shot is a point (repeats are not averaged first);
the uncertainties are the least-squares covariance scaled by the residual
variance. Shots left out are listed with their reason:

- no setpoint recorded (the shot was not taken);
- a non-finite reading;
- any PID2 PD sample of the shot at or above the saturation threshold
  (``ad.p.v_pid2_pd_saturation``, 10 V).

Nothing else is excluded. The write-back into kexp/calibrations/tweezer.py
happens only when no flag is raised (``FLAG_RULES``); a flagged result is
printed and never written. The edit follows the calibration convention: the
old line is commented out in place and the new one goes directly below it,
tagged ``#<run_id>, <date>``. Digits follow waxx.calibration.precision (the
uncertainty's second significant digit, never fewer significant figures than
the line replaced). ``revert`` is by hand: uncomment the old line, delete the
new one.

Use from a notebook::

    from kexp.analysis.tweezer_pid_calibration import calibrate_run, plot_tweezer_pid_cal
    cal = calibrate_run(run_id, write_back=False)   # fit + report only
    plot_tweezer_pid_cal(cal)
"""

from __future__ import annotations

import ast
import datetime
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

SLOPE_NAME = "vpd2_per_vpd1_slope"
INTERCEPT_NAME = "v_pd2_y_intercept"

#: Fewer used shots than this -> flagged (a line through a handful of points
#: says little about linearity).
MIN_POINTS = 5

#: The rules that block a write-back, stated before any data is seen.
FLAG_RULES = (
    f"fewer than {MIN_POINTS} shots used",
    "slope / intercept or their uncertainties not finite, or an uncertainty <= 0",
    "the PID2 PD was saturated already at the minimum setpoint",
    "the search trace differs between shots",
    "kexp/calibrations/tweezer.py changed since the run started",
)


def calibration_file() -> Path:
    import kexp.calibrations.tweezer as tw
    return Path(tw.__file__)


@dataclass
class TweezerPidCal:
    run_id: int
    slope: float = math.nan
    slope_unc: float = math.nan
    intercept: float = math.nan
    intercept_unc: float = math.nan
    corr_slope_intercept: float = math.nan
    n_shots: int = 0
    n_used: int = 0
    # [{"shot": i, "v_pid1": setpoint, "reason": ...}]
    excluded: list = field(default_factory=list)
    v_pid1_used: np.ndarray = field(default_factory=lambda: np.zeros(0))
    v_pid2_used: np.ndarray = field(default_factory=lambda: np.zeros(0))
    v_pid2_std_used: np.ndarray = field(default_factory=lambda: np.zeros(0))
    v_pid1_pd_used: np.ndarray = field(default_factory=lambda: np.zeros(0))
    v_pid1_excluded: np.ndarray = field(default_factory=lambda: np.zeros(0))
    v_pid2_excluded: np.ndarray = field(default_factory=lambda: np.zeros(0))
    residual_rms: float = math.nan
    residual_max: float = math.nan
    # PID1 PD vs PID1 setpoint (does the PID1 servo hold its setpoint?)
    pid1_tracking_slope: float = math.nan
    pid1_tracking_offset: float = math.nan
    v_pid2_saturation: float = math.nan
    v_pid1_top: float = math.nan
    saturation_found: bool = False
    saturated_at_min: bool = False
    # the search trace: setpoint, PID1 PD mean, PID2 PD mean, PID2 PD max
    search: dict = field(default_factory=dict)
    # the values the run started with (its params) and the file's now
    slope_at_start: float = math.nan
    intercept_at_start: float = math.nan
    slope_in_file: float = math.nan
    intercept_in_file: float = math.nan
    flags: list = field(default_factory=list)
    writeback: Optional[dict] = None

    @property
    def flagged(self) -> bool:
        return bool(self.flags)

    @property
    def v_pid1_at_saturation(self) -> float:
        """PID1 setpoint at which the fit reaches the saturation threshold."""
        return (self.v_pid2_saturation - self.intercept) / self.slope

    def report(self) -> str:
        def pm(v, u):
            return f"{v:.6g} +/- {u:.2g}"

        def change(new, old):
            if not (math.isfinite(old) and old != 0 and math.isfinite(new)):
                return ""
            return f" (was {old:.6g}, {100. * (new - old) / abs(old):+.2f} %)"

        lines = [f"[tweezer pid cal] run {self.run_id}: PID2 PD vs PID1 setpoint, "
                 f"{self.n_used} of {self.n_shots} shots used, {len(self.excluded)} excluded"]
        reasons = {}
        for e in self.excluded:
            reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
        for r, n in reasons.items():
            lines.append(f"  excluded {n}: {r}")
        if self.search:
            n_steps = int(np.sum(np.asarray(self.search["v_pid1"]) >= 0))
            if self.saturated_at_min:
                lines.append(f"  search ({n_steps} steps): PID2 PD saturated already at the "
                             f"minimum setpoint {self.v_pid1_top:.4f} V")
            elif self.saturation_found:
                lines.append(f"  search ({n_steps} steps): highest setpoint with every PID2 sample "
                             f"< {self.v_pid2_saturation:g} V: {self.v_pid1_top:.4f} V")
            else:
                lines.append(f"  search ({n_steps} steps): no PID2 saturation up to the cap; "
                             f"sweep top = cap = {self.v_pid1_top:.4f} V")
        lines.append(f"  {SLOPE_NAME} = {pm(self.slope, self.slope_unc)} V/V"
                     f"{change(self.slope, self.slope_in_file)}")
        lines.append(f"  {INTERCEPT_NAME} = {pm(self.intercept, self.intercept_unc)} V"
                     f"{change(self.intercept, self.intercept_in_file)}")
        lines.append(f"  corr(slope, intercept) = {self.corr_slope_intercept:.3f}; residuals rms "
                     f"{self.residual_rms * 1e3:.3g} mV, max |r| {self.residual_max * 1e3:.3g} mV")
        if np.size(self.v_pid2_std_used):
            lines.append(f"  within-shot PID2 PD std (median over shots): "
                         f"{np.median(self.v_pid2_std_used) * 1e3:.3g} mV")
        lines.append(f"  fit reaches {self.v_pid2_saturation:g} V at PID1 = "
                     f"{self.v_pid1_at_saturation:.4f} V")
        lines.append(f"  PID1 PD vs setpoint: slope {self.pid1_tracking_slope:.4f}, offset "
                     f"{self.pid1_tracking_offset * 1e3:+.2f} mV (servo tracking, not used in the fit)")
        if self.flags:
            lines.append("  FLAGGED -- not written back:")
            lines += [f"    - {f}" for f in self.flags]
        if self.writeback is not None:
            wb = self.writeback
            if wb.get("written"):
                lines.append(f"  written to {wb['file']}:")
                lines += [f"    {ln}" for ln in wb["new_lines"]]
            else:
                lines.append(f"  not written: {wb.get('reason', '')}")
        return "\n".join(lines)


# ---- the fit -----------------------------------------------------------------

def _linfit(x, y):
    """OLS y = m x + b. Returns (m, b, sm, sb, corr, residuals); the
    covariance is scaled by the residual variance (N - 2 dof)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    n = x.size
    if n < 3:
        return (math.nan,) * 5 + (np.full(n, math.nan),)
    A = np.vstack([x, np.ones(n)]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ coef
    s2 = float(res @ res) / (n - 2)
    cov = s2 * np.linalg.inv(A.T @ A)
    sm, sb = math.sqrt(cov[0, 0]), math.sqrt(cov[1, 1])
    corr = cov[0, 1] / (sm * sb) if sm > 0 and sb > 0 else math.nan
    return float(coef[0]), float(coef[1]), sm, sb, float(corr), res


def _flat(ad, key):
    return np.asarray(getattr(ad.data, key), dtype=float).reshape(-1)


def fit_pid2_vs_pid1(ad) -> TweezerPidCal:
    """Fit a run of tweezer_pid2_vs_pid1.py (atomdata, loaded without images)."""
    cal = TweezerPidCal(run_id=int(ad.run_info.run_id))
    v_sat = float(ad.p.v_pid2_pd_saturation)
    cal.v_pid2_saturation = v_sat

    x = _flat(ad, "v_pid1_setpoint")
    y = _flat(ad, "v_pid2_pd")
    y_std = _flat(ad, "v_pid2_pd_std")
    y_max = _flat(ad, "v_pid2_pd_max")
    pd1 = _flat(ad, "v_pid1_pd")
    cal.n_shots = x.size

    keep = np.ones(x.size, bool)
    for i in range(x.size):
        reason = None
        if not np.isfinite(x[i]) or x[i] <= 0.:
            reason = "no setpoint recorded (shot not taken)"
        elif not (np.isfinite(y[i]) and np.isfinite(y_max[i]) and np.isfinite(pd1[i])):
            reason = "non-finite photodiode reading"
        elif y_max[i] >= v_sat:
            reason = f"PID2 PD saturated (a sample >= {v_sat:g} V)"
        if reason is not None:
            keep[i] = False
            cal.excluded.append({"shot": i, "v_pid1": float(x[i]), "reason": reason})

    cal.v_pid1_used, cal.v_pid2_used = x[keep], y[keep]
    cal.v_pid2_std_used, cal.v_pid1_pd_used = y_std[keep], pd1[keep]
    taken = np.isfinite(x) & (x > 0.) & np.isfinite(y)
    cal.v_pid1_excluded, cal.v_pid2_excluded = x[~keep & taken], y[~keep & taken]
    cal.n_used = int(keep.sum())

    m, b, sm, sb, corr, res = _linfit(cal.v_pid1_used, cal.v_pid2_used)
    cal.slope, cal.intercept, cal.slope_unc, cal.intercept_unc = m, b, sm, sb
    cal.corr_slope_intercept = corr
    if res.size:
        cal.residual_rms = float(np.sqrt(np.mean(res ** 2)))
        cal.residual_max = float(np.max(np.abs(res)))
    tm, tb, *_ = _linfit(cal.v_pid1_used, cal.v_pid1_pd_used)
    cal.pid1_tracking_slope, cal.pid1_tracking_offset = tm, tb

    # the search: one trace, carried by every shot taken
    taken_idx = np.flatnonzero(taken)
    traces_differ = False
    if taken_idx.size:
        i0 = taken_idx[0]
        cal.v_pid1_top = float(_flat(ad, "v_pid1_top")[i0])
        cal.saturation_found = bool(_flat(ad, "pid2_saturation_found")[i0])
        cal.saturated_at_min = bool(_flat(ad, "pid2_saturated_at_min")[i0])
        search_keys = {"v_pid1": "search_v_pid1", "v_pid1_pd": "search_v_pid1_pd",
                       "v_pid2_pd": "search_v_pid2_pd", "v_pid2_pd_max": "search_v_pid2_pd_max"}
        for name, key in search_keys.items():
            arr = np.asarray(getattr(ad.data, key), dtype=float)
            arr = arr.reshape(-1, arr.shape[-1])[taken_idx]
            cal.search[name] = arr[0]
            if not all(np.array_equal(arr[0], row, equal_nan=True) for row in arr[1:]):
                traces_differ = True

    cal.slope_at_start = float(getattr(ad.p, "vpd2_per_vpd1_slope_at_start", math.nan))
    cal.intercept_at_start = float(getattr(ad.p, "v_pd2_y_intercept_at_start", math.nan))
    try:
        lits = read_calibration_literals()
        cal.slope_in_file = float(lits[SLOPE_NAME][1])
        cal.intercept_in_file = float(lits[INTERCEPT_NAME][1])
    except Exception as e:
        cal.flags.append(f"could not read {calibration_file().name}: {e}")

    # FLAG_RULES, in order
    if cal.n_used < MIN_POINTS:
        cal.flags.append(f"only {cal.n_used} shots used (< {MIN_POINTS})")
    vals = (cal.slope, cal.intercept, cal.slope_unc, cal.intercept_unc)
    if not all(math.isfinite(v) for v in vals) or cal.slope_unc <= 0 or cal.intercept_unc <= 0:
        cal.flags.append("fit not finite, or an uncertainty <= 0")
    # PID2 need not saturate: with no saturation up to the cap, the sweep
    # simply tops out at the cap
    if cal.saturated_at_min:
        cal.flags.append("PID2 PD saturated already at the minimum setpoint")
    if traces_differ:
        cal.flags.append("the search trace differs between shots")
    if math.isfinite(cal.slope_in_file) and (
            cal.slope_in_file != cal.slope_at_start or cal.intercept_in_file != cal.intercept_at_start):
        cal.flags.append(f"{calibration_file().name} changed since the run started (run: "
                         f"{cal.slope_at_start!r}, {cal.intercept_at_start!r}; file: "
                         f"{cal.slope_in_file!r}, {cal.intercept_in_file!r})")
    return cal


# ---- the file edit -------------------------------------------------------------

def _line_re(name):
    from waxx.calibration.precision import NUM_RE
    return re.compile(rf"^{name}\s*=\s*(?P<lit>{NUM_RE})\s*(?:#.*)?$")


def read_calibration_literals(text: Optional[str] = None) -> dict:
    """{name: (line index, literal text)} for the one active module-level
    assignment of each constant. Raises ValueError when there is not exactly one."""
    if text is None:
        text = calibration_file().read_bytes().decode("utf-8")
    lines = text.splitlines()
    out = {}
    for name in (SLOPE_NAME, INTERCEPT_NAME):
        pat = _line_re(name)
        hits = [(i, m.group("lit")) for i, ln in enumerate(lines) if (m := pat.match(ln))]
        if len(hits) != 1:
            raise ValueError(f"{len(hits)} active '{name} = <number>' lines (need exactly one)")
        out[name] = hits[0]
    return out


def _module_values(text) -> dict:
    """The value each constant ends up with when the module runs (last
    module-level assignment), from the source text."""
    vals = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in (SLOPE_NAME, INTERCEPT_NAME):
            vals[node.targets[0].id] = ast.literal_eval(node.value)
    return vals


def write_calibration(cal: TweezerPidCal, *, date: Optional[str] = None,
                      dry_run: bool = False) -> dict:
    """Write cal's slope and intercept into kexp/calibrations/tweezer.py (old
    lines commented out in place, new lines below them, tagged #run, date).
    Refuses a flagged result. Returns {written, file, old_lines, new_lines,
    reason}."""
    from waxx.calibration._lock import file_lock, replace_bytes
    from waxx.calibration.precision import format_value

    path = calibration_file()
    rep = {"written": False, "file": str(path), "old_lines": [], "new_lines": [], "reason": ""}
    if cal.flagged:
        rep["reason"] = "the result is flagged: " + "; ".join(cal.flags)
        return rep
    date = date or datetime.date.today().isoformat()
    with file_lock(path):
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        eol = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(eol)
        try:
            found = read_calibration_literals(text)
        except ValueError as e:
            rep["reason"] = str(e)
            return rep
        new = {SLOPE_NAME: (cal.slope, cal.slope_unc), INTERCEPT_NAME: (cal.intercept, cal.intercept_unc)}
        lits = {}
        # bottom-up, so an insert does not move the other line
        for name, (idx, old_lit) in sorted(found.items(), key=lambda kv: -kv[1][0]):
            value, unc = new[name]
            lit = format_value(value, unc, old_lit)
            lits[name] = lit
            old_line = lines[idx]
            new_line = f"{name} = {lit} #{cal.run_id}, {date}"
            lines[idx] = "# " + old_line
            lines.insert(idx + 1, new_line)
            rep["old_lines"].insert(0, old_line)
            rep["new_lines"].insert(0, new_line)
        new_text = eol.join(lines)
        got = _module_values(new_text)
        for name, lit in lits.items():
            if got.get(name) != float(lit):
                rep["reason"] = f"verification failed: {name} would be {got.get(name)!r}, not {lit}"
                return rep
        if dry_run:
            rep["reason"] = "dry run"
            return rep
        new_raw = new_text.encode("utf-8")
        replace_bytes(path, new_raw)
        if path.read_bytes() != new_raw:
            replace_bytes(path, raw)
            rep["reason"] = "the file did not read back as written; original restored"
            return rep
    rep["written"] = True
    return rep


# ---- entry points ----------------------------------------------------------------

def calibrate_run(run_id: int, *, write_back: bool = False, out=print) -> TweezerPidCal:
    """Load the run (read-only, no images), fit, print the report, and write
    the calibration when write_back and nothing is flagged and the submitter
    did not veto ($WAXX_CAL_NO_WRITE_BACK)."""
    from kexp.config.calibration import CALIBRATION_CONFIG
    from waxx.calibration.emit import vetoed

    ad = CALIBRATION_CONFIG.load_run(int(run_id), needs_images=False)
    cal = fit_pid2_vs_pid1(ad)
    if write_back:
        if vetoed():
            cal.writeback = {"written": False, "reason": "vetoed ($WAXX_CAL_NO_WRITE_BACK)"}
        else:
            cal.writeback = write_calibration(cal)
    out(cal.report())
    return cal


def plot_tweezer_pid_cal(cal: TweezerPidCal):
    """PID2 PD vs PID1 setpoint with the fit, the excluded shots and the
    search trace; residuals below."""
    import matplotlib.pyplot as plt
    fig, (ax, axr) = plt.subplots(2, 1, figsize=(6, 6), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1]})
    s = cal.search
    if s:
        took = np.asarray(s["v_pid1"]) >= 0
        ax.plot(s["v_pid1"][took], s["v_pid2_pd"][took], ".", color="0.6", label="search (mean)")
    ax.errorbar(cal.v_pid1_used, cal.v_pid2_used, yerr=cal.v_pid2_std_used, fmt="o", ms=4,
                capsize=2, label=f"used ({cal.n_used}; bars: within-shot std)")
    if cal.v_pid1_excluded.size:
        ax.plot(cal.v_pid1_excluded, cal.v_pid2_excluded, "x", color="C3",
                label=f"excluded ({cal.v_pid1_excluded.size}, saturated / bad)")
    if cal.n_used:
        xx = np.linspace(min(cal.v_pid1_used.min(), cal.v_pid1_top), cal.v_pid1_top, 50)
        ax.plot(xx, cal.slope * xx + cal.intercept, "-", color="C1",
                label=f"fit: {cal.slope:.4g} V/V, {cal.intercept:+.4g} V")
        if math.isfinite(cal.slope_in_file):
            ax.plot(xx, cal.slope_in_file * xx + cal.intercept_in_file, "--", color="0.4",
                    label="calibration in file")
        axr.plot(cal.v_pid1_used, (cal.v_pid2_used - (cal.slope * cal.v_pid1_used + cal.intercept)) * 1e3,
                 "o", ms=4)
    ax.axhline(cal.v_pid2_saturation, color="C3", lw=0.8, ls=":")
    axr.axhline(0., color="0.5", lw=0.8)
    ax.set_ylabel("PID2 PD (V)")
    axr.set_ylabel("residual (mV)")
    axr.set_xlabel("PID1 setpoint (V)")
    ax.legend(fontsize=7)
    ax.set_title(f"run {cal.run_id}  |  tweezer PID2 PD vs PID1 setpoint")
    fig.tight_layout()
    return fig
