"""Figures for the overnight 2026-10-08 rule-grid cycle (read-only; alias_<rid>.npz, alt2_results.json).

    python make_overnight_summary.py

Ten ALT2 g15 (adaptive) / NAALT2 g15 (non-adaptive) pairs, 15-point grid (q = 2.4 on the long gap), 9 pulses,
alternating gaps 44.1 / 59.1 us, 195 shots each. Writes fig_overnight_posteriors.png, fig_overnight_pairs.png.
"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
STEP = 0.0125
ALT = [85441, 85443, 85445, 85448, 85450, 85454, 85456, 85458, 85462, 85464]
NA = [85442, 85444, 85447, 85449, 85451, 85455, 85457, 85461, 85463, 85465]
CAL = {85441: 41.5, 85442: 41.5, 85443: 41.5, 85444: 41.5, 85445: 41.5, 85447: 46.4, 85448: 46.4, 85449: 46.4,
       85450: 46.4, 85451: 46.4, 85454: 57.8, 85455: 57.8, 85456: 57.8, 85457: 57.8, 85458: 57.8, 85461: 64.0,
       85462: 64.0, 85463: 64.0, 85464: 64.0, 85465: 64.0}


def load(rid):
    d = dict(np.load(os.path.join(HERE, f"alias_{rid}.npz"), allow_pickle=True))
    return {k: (v.item() if isinstance(v, np.ndarray) and v.ndim == 0 else v) for k, v in d.items()}


def coarse_density(ds, fine_step):
    """Kernel's final posterior on its own grid (P_kernel_final over det0), averaged over shots per grid offset from
    resonance, converted to the fine curve's per-fine-point scale (divide by step / fine_step).
    Returns (centres in Omega, heights, coarse step in Omega)."""
    step = float(np.abs(np.diff(ds[0]["det0"][0])).mean())
    acc = {}
    for d in ds:
        for r in range(d["P_kernel_final"].shape[0]):
            k = np.rint(d["det0"][r] / step).astype(int)
            for kk, p in zip(k, d["P_kernel_final"][r]):
                a = acc.setdefault(int(kk), [0.0, 0])
                a[0] += float(p); a[1] += 1
    ks = np.array(sorted(acc))
    mean_p = np.array([acc[k][0] / acc[k][1] for k in ks])
    return ks * step, mean_p / (step / fine_step), step


def pooled_mean(ds):
    step = float(np.abs(np.diff(ds[0]["det2"][0])).mean())     # the replay's own fine step (0.0154 Omega here)
    k_all = [np.rint(d["det2"] / step).astype(int) for d in ds]
    kmin = min(k.min() for k in k_all); kmax = max(k.max() for k in k_all); n = kmax - kmin + 1
    s = np.zeros(n); c = np.zeros(n)
    for d, k in zip(ds, k_all):
        for r in range(d["P_wide_final"].shape[0]):
            s[k[r] - kmin] += d["P_wide_final"][r]; c[k[r] - kmin] += 1
    return (np.arange(n) + kmin) * step, np.where(c > 0, s / np.maximum(c, 1), np.nan)


def main():
    da = [load(r) for r in ALT]; dn = [load(r) for r in NA]
    f_Om = da[0]["Omega"] / (2 * np.pi)
    gaps = np.concatenate([d["dT_mu_rr"][:, :-1] for d in da]) * 1e-9
    T_short, T_long = float(gaps[:, 0::2].mean()), float(gaps[:, 1::2].mean())
    a_s, a_l = (1 / T_short) / f_Om, (1 / T_long) / f_Om
    step_Om = float(np.abs(np.diff(da[0]["det0"][0])).mean())
    R = json.load(open(os.path.join(HERE, "alt2_results.json")))
    folds = {s["run_id"]: (s["fold_at_T_fast"], s["fold_at_T_std"]) for arm in R["scores"].values() for s in arm}

    fig, axes = plt.subplots(2, 1, figsize=(10, 6.8), sharex=True)
    lim = 1.0
    for ax, ds, rids, col, label in ((axes[0], da, ALT, "#4a3aa7", "Adaptive loop (ALT2 g15)"),
                                     (axes[1], dn, NA, "#1baf7a", "Non-adaptive drive list (NAALT2 g15)")):
        x, m = pooled_mean(ds)
        sel = np.abs(x) <= lim + 0.02
        fine_step = float(np.abs(np.diff(ds[0]["det2"][0])).mean())
        cx, ch, cstep = coarse_density(ds, fine_step)
        cs = np.abs(cx) <= lim + cstep
        ax.bar(cx[cs], ch[cs], width=cstep * 0.96, color=col, alpha=0.10, zorder=0, linewidth=0)
        ax.plot(x[sel], m[sel], color=col, lw=1.5); ax.fill_between(x[sel], 0, m[sel], color=col, alpha=0.12)
        for n in range(-12, 13):
            if n == 0:
                continue
            if abs(n * a_l) <= lim:
                ax.axvline(n * a_l, color="#eb6834", lw=0.9, alpha=0.28)
            if abs(n * a_s) <= lim:
                ax.axvline(n * a_s, color="#2a78d6", lw=0.9, alpha=0.3)
        for kk in range(-10, 11):
            if abs(kk * step_Om) <= lim + 1e-9:
                ax.axvline(kk * step_Om, color="black", lw=2.2, alpha=0.10, zorder=0)
        ax.axvline(0, color="#008300", lw=1.2)
        ax.set_xlim(-lim, lim); ax.set_ylim(0, None)
        ax.set_ylabel("mean posterior\nper fine point")
        fl = [folds[r] for r in rids]
        near = np.concatenate([[abs(d["det2"][r, np.argmax(d["P_wide_final"][r])]) <= 0.04 for r in range(d["n_shot"])] for d in ds])
        ax.set_title(f"{label}: {len(rids)} runs, {sum(d['n_shot'] for d in ds)} shots   |   comb at long gap {min(f[1] for f in fl):.2f}–{max(f[1] for f in fl):.2f}×, "
                     f"short gap {min(f[0] for f in fl):.2f}–{max(f[0] for f in fl):.2f}×   |   localized within ±0.04 Ω: {near.mean():.2f}",
                     fontsize=9, loc="left", pad=(44 if ax is axes[0] else 6))
    sec = axes[0].secondary_xaxis("top", functions=(lambda u: u * f_Om / 1e3, lambda k: k * 1e3 / f_Om))
    sec.set_xlabel("detuning (kHz)", fontsize=9)
    axes[-1].set_xlabel("hypothesis detuning from the calibrated resonance (Ω, units of the Rabi frequency)")
    fig.text(0.5, 0.004, f"orange lines: n/T_long = n × {a_l:.3f} Ω ({1e-3/T_long:.1f} kHz, {T_long*1e6:.1f} µs gap);  blue lines: n/T_short = n × {a_s:.3f} Ω "
             f"({1e-3/T_short:.1f} kHz, {T_short*1e6:.1f} µs gap);  wide grey: the 15-point hypothesis grid ({step_Om:.3f} Ω)\n"
             f"faint bars: the experiment's own posterior on that grid.  2026-10-08 00:40–08:20, both arms alternating, 9 pulses, Ω/2π = {f_Om/1e3:.0f} kHz; posteriors pooled over all runs of each arm",
             ha="center", va="bottom", fontsize=8)
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(os.path.join(HERE, "fig_overnight_posteriors.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)

    # per-pair localization and hit
    sa = {s["run_id"]: s for s in R["scores"]["ALT2"]}; sn = {s["run_id"]: s for s in R["scores"]["NAALT2"]}
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9))
    xs = np.arange(1, len(ALT) + 1)
    for ax, key, sem, ylab in ((axes[0], "fine_near", "fine_near_sem", "shots localized within ±0.04 Ω"),
                               (axes[1], "hit21", "hit21_sem", "hit on the 15-point grid")):
        for i, (a, n) in enumerate(zip(ALT, NA)):
            ax.plot([xs[i] - 0.12, xs[i] + 0.12], [sa[a][key], sn[n][key]], color="#8a8a8a", lw=0.8, zorder=1)
        ax.errorbar(xs - 0.12, [sa[a][key] for a in ALT], yerr=[sa[a][sem] for a in ALT], fmt="o", color="#4a3aa7", capsize=2, ms=5, label="adaptive")
        ax.errorbar(xs + 0.12, [sn[n][key] for n in NA], yerr=[sn[n][sem] for n in NA], fmt="s", color="#1baf7a", capsize=2, ms=5, label="non-adaptive")
        ax.set_xticks(xs); ax.set_xticklabels([f"{i}\n{CAL[a]:.0f} mV" for i, a in zip(xs, ALT)], fontsize=7.5)
        ax.set_xlabel("pair (APD contrast in force for the adaptive run)", fontsize=9); ax.set_ylabel(ylab)
        ax.legend(fontsize=8, loc="upper right")
        ax.set_ylim(0, None)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig_overnight_pairs.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(dict(T_short_us=T_short * 1e6, T_long_us=T_long * 1e6, step_Om=step_Om, a_short=a_s, a_long=a_l))


if __name__ == "__main__":
    main()
