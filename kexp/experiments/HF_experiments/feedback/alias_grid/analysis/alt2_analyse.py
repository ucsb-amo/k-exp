"""P1-P4 scorer for the ALT2 / FBF / FB cycles (PLAN_gap_cycles.md section 6). Pre-registered
2026-10-07 before any ALT2 data existed; dry-run on 85351 (FBF) / 85352 (FB).

    python alt2_analyse.py ALT2:<rid>,<rid>,... FBF:<rid>,... FB:<rid>,...

Read-only. Every shot of every run is used. Each run is first replayed with alias_replay.py
(gap-aware engine; alias_<rid>.npz is reused if present). Per run:
  q        alias order of the 0.25-Omega grid point, 0.25 * f_Rabi * T, for each distinct gap
           class in the run (one value for FBF/FB, two for ALT2: even and odd gaps)
  P1       folded-comb peak/mean of the 801-pt final posterior (|order| >= 0.5, resonance tooth
           excluded) at T_fast = 46.9 us and at T_std = 66.6 us (the two production periods;
           taken from the FBF / FB runs' own recorded gaps when available), and at T_fast + T_std
  P2       fine-grid MAP within +/-0.04 Omega of resonance; mean posterior mass within +/-0.04 Omega
  P3       21-pt production hit (kernel posterior), with +/-1 and +/-2-bin error rates (P4)
Then paired per-cycle differences ALT2 - FB and ALT2 - FBF (cycle k = k-th run of each arm) with
SEM over cycles, and the pre-registered verdicts:
  P1 confirmed  : every ALT2 run folds < 1.2 at BOTH production periods and every FBF/FB run >= 1.4
                  at its own period
  P2 useful     : pooled paired MAP-fraction difference > 3 sigma in the predicted (positive) direction
                  with >= 4 cycles
Output: alt2_results.json, alt2_results.md, fig13_alt2_cycles.png (in this folder).
"""
import json
import os
import subprocess
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, HERE)
HALF_WIN = 0.04
T_FAST_US, T_STD_US = 46.9, 66.6     # defaults; replaced by the arms' recorded means when present
COL = {"ALT2": "#4a3aa7", "FBF": "#2a78d6", "FB": "#eb6834", "NAF": "#1baf7a", "NAALT2": "#e87ba4"}


def ensure_npz(rid):
    path = os.path.join(HERE, f"alias_{rid}.npz")
    if not os.path.exists(path):
        subprocess.run([sys.executable, os.path.join(HERE, "alias_replay.py"), str(rid)], check=True)
    d = dict(np.load(path, allow_pickle=True))
    return {k: (v.item() if isinstance(v, np.ndarray) and v.ndim == 0 else v) for k, v in d.items()}


def fold_peak(det_Om, P, f_Om, T_s, u_min=0.5, nb=40):
    u = det_Om * f_Om * T_s
    sel = np.abs(u) >= u_min
    frac = (u[sel] + 0.5) % 1.0 - 0.5
    edges = np.linspace(-0.5, 0.5, nb + 1)
    idx = np.clip(np.digitize(frac, edges) - 1, 0, nb - 1)
    s = np.bincount(idx, weights=P[sel], minlength=nb); c = np.bincount(idx, minlength=nb)
    m = s / np.maximum(c, 1); x = 0.5 * (edges[1:] + edges[:-1])
    return float(m[np.abs(x) < 0.1].mean() / m.mean())


def mass_near(det, P, center, half=HALF_WIN):
    out = np.full(P.shape[0], np.nan)
    for r in range(P.shape[0]):
        sel = np.abs(det[r] - center) <= half + 1e-9
        if sel.any() and det[r].min() <= center - half + 1e-9 and det[r].max() >= center + half - 1e-9:
            out[r] = P[r, sel].sum()
    return out


def score_run(d, arm, T_fast_s, T_std_s):
    f_Om = d["Omega"] / (2 * np.pi)
    gaps = d["dT_mu_rr"][:, :-1] * 1e-9
    n_shot = d["n_shot"]
    # gap classes: even/odd positions
    even, odd = gaps[:, 0::2].mean(), gaps[:, 1::2].mean()
    classes = {"all": float(gaps.mean())} if abs(even - odd) < 2e-6 else {"even": float(even), "odd": float(odd)}
    step_Om = float(np.abs(np.diff(d['det0'][0])).mean())   # the run's own grid step (Omega)
    q = {k: float(step_Om * f_Om * T) for k, T in classes.items()}
    det2, Pw = d["det2"], d["P_wide_final"]
    fmap = np.array([det2[r, np.argmax(Pw[r])] for r in range(n_shot)])
    near = (np.abs(fmap) <= HALF_WIN).astype(float)
    mres = mass_near(det2, Pw, 0.0)
    Pk, z0 = d["P_kernel_final"], d["z0"]
    err = np.argmax(Pk, 1) - z0
    out = dict(run_id=d["run_id"], arm=arm, n_shot=n_shot, f_rabi_kHz=f_Om / 1e3, t_pi_us=d["t_pi"] * 1e6,
               gap_means_us={k: v * 1e6 for k, v in classes.items()}, q=q,
               fold_at_T_fast=fold_peak(det2, Pw, f_Om, T_fast_s), fold_at_T_std=fold_peak(det2, Pw, f_Om, T_std_s),
               fold_at_T_sum=fold_peak(det2, Pw, f_Om, T_fast_s + T_std_s),
               fine_near=float(near.mean()), fine_near_sem=float(np.sqrt(near.mean() * (1 - near.mean()) / n_shot)),
               mass_res=float(np.nanmean(mres)), mass_res_sem=float(np.nanstd(mres, ddof=1) / np.sqrt(n_shot)),
               hit21=float(np.mean(err == 0)), hit21_sem=float(np.sqrt(np.mean(err == 0) * (1 - np.mean(err == 0)) / n_shot)),
               pm1=float(np.mean(np.abs(err) == 1)), pm2=float(np.mean(np.abs(err) == 2)),
               per_shot=dict(near=near.tolist(), mres=np.nan_to_num(mres).tolist(), hit=(err == 0).astype(float).tolist()))
    return out


def paired(a_runs, b_runs, key):
    n = min(len(a_runs), len(b_runs))
    if n == 0:
        return None
    diffs = []
    for k in range(n):
        a = np.array(a_runs[k]["per_shot"][key]); b = np.array(b_runs[k]["per_shot"][key])
        diffs.append(a.mean() - b.mean())
    diffs = np.array(diffs)
    sem = float(diffs.std(ddof=1) / np.sqrt(n)) if n > 1 else float(np.sqrt(
        np.var(np.array(a_runs[0]["per_shot"][key])) / len(a_runs[0]["per_shot"][key])
        + np.var(np.array(b_runs[0]["per_shot"][key])) / len(b_runs[0]["per_shot"][key])))
    return dict(n_cycles=n, mean=float(diffs.mean()), sem=sem, per_cycle=diffs.tolist(),
                sigma=float(diffs.mean() / sem) if sem > 0 else np.nan)


def main(argv):
    arms = {}
    for a in argv:
        name, rids = a.split(":")
        arms[name] = [int(x) for x in rids.split(",") if x]
    data = {arm: [ensure_npz(r) for r in rids] for arm, rids in arms.items()}
    if data.get("FBF"):
        T_fast_s = np.mean([d["dT_mu_rr"][:, :-1].mean() * 1e-9 for d in data["FBF"]])
    elif data.get("ALT2"):   # no single-gap arms: the alternating runs' own short-gap class
        T_fast_s = np.mean([d["dT_mu_rr"][:, 0:-1:2].mean() * 1e-9 for d in data["ALT2"]])
    else:
        T_fast_s = T_FAST_US * 1e-6
    if data.get("FB"):
        T_std_s = np.mean([d["dT_mu_rr"][:, :-1].mean() * 1e-9 for d in data["FB"]])
    elif data.get("ALT2"):   # the alternating runs' own long-gap class
        T_std_s = np.mean([d["dT_mu_rr"][:, 1:-1:2].mean() * 1e-9 for d in data["ALT2"]])
    else:
        T_std_s = T_STD_US * 1e-6
    scores = {arm: [score_run(d, arm, T_fast_s, T_std_s) for d in ds] for arm, ds in data.items()}

    lines = [f"# ALT2 / FBF / FB scorer -- T_fast {T_fast_s*1e6:.2f} us, T_std {T_std_s*1e6:.2f} us (from the arms' recorded gaps)", "",
             "| arm | run | q (per gap class) | fold@T_fast | fold@T_std | fold@T_f+T_s | fine MAP ±0.04 Ω | mass ±0.04 Ω | hit21 | ±1 | ±2 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm in [a for a in ("ALT2", "FBF", "FB", "NAF", "NAALT2") if a in scores] + [a for a in scores if a not in ("ALT2", "FBF", "FB", "NAF", "NAALT2")]:
        for s in scores.get(arm, []):
            qtxt = ", ".join(f"{k} {v:.2f}" for k, v in s["q"].items())
            lines.append(f"| {arm} | {s['run_id']} | {qtxt} | {s['fold_at_T_fast']:.2f} | {s['fold_at_T_std']:.2f} | {s['fold_at_T_sum']:.2f} | "
                         f"{s['fine_near']:.3f} ± {s['fine_near_sem']:.3f} | {s['mass_res']:.4f} ± {s['mass_res_sem']:.4f} | "
                         f"{s['hit21']:.3f} ± {s['hit21_sem']:.3f} | {s['pm1']:.3f} | {s['pm2']:.3f} |")
    verdict = {}
    alt = scores.get("ALT2", [])
    base_ok = all(s["fold_at_T_fast"] >= 1.4 for s in scores.get("FBF", [])) and all(s["fold_at_T_std"] >= 1.4 for s in scores.get("FB", []))
    alt_ok = bool(alt) and all(s["fold_at_T_fast"] < 1.2 and s["fold_at_T_std"] < 1.2 for s in alt)
    verdict["P1_comb_removed"] = ("confirmed" if (alt_ok and base_ok) else ("not confirmed" if alt else "no ALT2 runs yet"),
                                  dict(baselines_fold_ok=base_ok, alt2_fold_ok=alt_ok))
    pairs = {}
    for ref in [a for a in ("FB", "FBF", "NAALT2", "NAF") if a in scores]:
        for key, label in (("near", "fine_MAP_fraction"), ("mres", "mass_res"), ("hit", "hit21")):
            p = paired(alt, scores.get(ref, []), key)
            if p:
                pairs[f"ALT2-{ref}:{label}"] = p
    p2 = pairs.get("ALT2-FB:fine_MAP_fraction")
    verdict["P2_useful"] = ("useful" if (p2 and p2["n_cycles"] >= 4 and p2["sigma"] > 3) else
                            ("not established" if p2 else "no pairs yet"), p2)
    lines += ["", "## Paired per-cycle differences (ALT2 minus reference)", ""]
    for k, p in pairs.items():
        lines.append(f"- {k}: {p['mean']:+.4f} ± {p['sem']:.4f} ({p['sigma']:+.1f} σ) over {p['n_cycles']} cycles; per cycle "
                     + ", ".join(f"{x:+.3f}" for x in p["per_cycle"]))
    lines += ["", "## Verdicts (pre-registered rules)", "",
              f"- P1 comb removed: **{verdict['P1_comb_removed'][0]}** ({verdict['P1_comb_removed'][1]})",
              f"- P2 useful: **{verdict['P2_useful'][0]}**"]
    md = "\n".join(lines)
    open(os.path.join(HERE, "alt2_results.md"), "w", encoding="utf-8").write(md + "\n")
    slim = {arm: [{k: v for k, v in s.items() if k != "per_shot"} for s in ss] for arm, ss in scores.items()}
    json.dump(dict(T_fast_us=T_fast_s * 1e6, T_std_us=T_std_s * 1e6, scores=slim, pairs=pairs, verdict=verdict),
              open(os.path.join(HERE, "alt2_results.json"), "w"), indent=1, default=str)
    print(md)

    # figure: per-run metrics by arm in cycle order
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    for arm, ss in scores.items():
        x = np.arange(len(ss)) + {"ALT2": -0.15, "FBF": 0.0, "FB": 0.15}.get(arm, 0)
        ax[0].errorbar(x, [s["fold_at_T_std" if arm == "FB" else "fold_at_T_fast"] for s in ss], fmt="o", color=COL.get(arm, "k"), label=f"{arm} at its production period" if arm != "ALT2" else "ALT2 at T_fast")
        if arm == "ALT2":
            ax[0].plot(x, [s["fold_at_T_std"] for s in ss], "s", color=COL[arm], mfc="none", label="ALT2 at T_std")
            ax[0].plot(x, [s["fold_at_T_sum"] for s in ss], "^", color=COL[arm], mfc="none", label="ALT2 at T_f+T_s")
        ax[1].errorbar(x, [s["fine_near"] for s in ss], yerr=[s["fine_near_sem"] for s in ss], fmt="o", color=COL.get(arm, "k"), capsize=3, label=arm)
        ax[2].errorbar(x, [s["hit21"] for s in ss], yerr=[s["hit21_sem"] for s in ss], fmt="o", color=COL.get(arm, "k"), capsize=3, label=arm)
    ax[0].axhline(1.2, color="#8a8a8a", lw=0.8, ls="--"); ax[0].axhline(1.4, color="#8a8a8a", lw=0.8, ls=":")
    ax[0].set_ylabel("folded-comb peak / mean (P1)"); ax[1].set_ylabel("fine MAP within ±0.04 Ω (P2)"); ax[2].set_ylabel("21-pt hit (P3)")
    for a in ax:
        a.set_xlabel("cycle"); a.grid(alpha=0.2); a.legend(fontsize=7)
    fig.suptitle("ALT2 / FBF / FB cycles — measured; dashed 1.2 = ALT2 threshold, dotted 1.4 = baseline threshold", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "fig13_alt2_cycles.png"), dpi=170, bbox_inches="tight")


if __name__ == "__main__":
    main(sys.argv[1:])
