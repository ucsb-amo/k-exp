"""Figures for the slow / fast / alternating-delay aliasing summary (read-only; alias_<rid>.npz).

    python make_alias_summary.py

Cycle 1 of 2026-10-07: FB 85423 (slow, standard path, single gap ~66.6 us), FBF 85422 (fast path, ~46.9 us),
ALT2 85419 (alternating 46.9 / 66.6 us). Same 21-point grid (0.25 Omega), 17 pulses, 420 shots each.
Writes fig_summary_posteriors.png, fig_summary_folded.png, summary_numbers.json.
"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
STEP = 0.0125
WIN = 0.04
RUNS = [("Slow path (standard, single gap)", 85423, "#eb6834"),
        ("Fast path (single gap)", 85422, "#2a78d6"),
        ("Alternating delay (fast / slow gaps)", 85419, "#4a3aa7")]


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


def mean_post(d):
    det2, Pw = d["det2"], d["P_wide_final"]
    k = np.rint(det2 / STEP).astype(int); kmin = k.min(); n = k.max() - kmin + 1
    s = np.zeros(n); c = np.zeros(n)
    for r in range(Pw.shape[0]):
        s[k[r] - kmin] += Pw[r]; c[k[r] - kmin] += 1
    ax = (np.arange(n) + kmin) * STEP
    return ax, np.where(c > 0, s / np.maximum(c, 1), np.nan)


def fold(d, T, f_Om, nb=40):
    det2, Pw = d["det2"], d["P_wide_final"]
    u = det2 * f_Om * T; sel = np.abs(u) >= 0.5
    frac = (u[sel] + 0.5) % 1.0 - 0.5
    edges = np.linspace(-0.5, 0.5, nb + 1); idx = np.clip(np.digitize(frac, edges) - 1, 0, nb - 1)
    m = np.bincount(idx, weights=Pw[sel], minlength=nb) / np.maximum(np.bincount(idx, minlength=nb), 1)
    x = 0.5 * (edges[1:] + edges[:-1])
    return x, m / m.mean(), float(m[np.abs(x) < 0.1].mean() / m.mean())


def mass_near(d, c):
    det2, Pw = d["det2"], d["P_wide_final"]
    out = []
    for r in range(Pw.shape[0]):
        sel = np.abs(det2[r] - c) <= WIN + 1e-9
        if sel.any() and det2[r].min() <= c - WIN and det2[r].max() >= c + WIN:
            out.append(Pw[r, sel].sum())
    return float(np.mean(out))


def main():
    data = {rid: load(rid) for _, rid, _ in RUNS}
    d_fb, d_fbf, d_alt = data[85423], data[85422], data[85419]
    T_slow = float(d_fb["dT_mu_rr"][:, :-1].mean()) * 1e-9
    T_fast = float(d_fbf["dT_mu_rr"][:, :-1].mean()) * 1e-9
    f_Om = d_fb["Omega"] / (2 * np.pi)
    nums = dict(T_slow_us=T_slow * 1e6, T_fast_us=T_fast * 1e6, f_alias_slow_kHz=1e-3 / T_slow, f_alias_fast_kHz=1e-3 / T_fast,
                f_rabi_kHz=f_Om / 1e3, runs={})

    # Figure 1: mean posterior, three stacked panels, x in Omega (+/-1 Omega), kHz twin axis on top
    fig, axes = plt.subplots(3, 1, figsize=(10, 9.6), sharex=True)
    lim = 1.0                                  # Omega
    a_slow = (1.0 / T_slow) / f_Om             # comb spacing in Omega
    a_fast = (1.0 / T_fast) / f_Om
    for ax, (label, rid, col) in zip(axes, RUNS):
        d = data[rid]
        x, m = mean_post(d)
        sel = np.abs(x) <= lim + 0.02
        cx, ch, cstep = coarse_density([d], STEP)
        cs = np.abs(cx) <= lim + cstep
        ax.bar(cx[cs], ch[cs], width=cstep * 0.96, color=col, alpha=0.10, zorder=0, linewidth=0)
        ax.plot(x[sel], m[sel], color=col, lw=1.5)
        ax.fill_between(x[sel], 0, m[sel], color=col, alpha=0.12)
        show_slow = rid in (85423, 85419)   # this run's own comb(s) only
        show_fast = rid in (85422, 85419)
        for n in range(-12, 13):
            if n == 0:
                continue
            if show_slow and abs(n * a_slow) <= lim:
                ax.axvline(n * a_slow, color="#eb6834", lw=0.9, alpha=0.28)
            if show_fast and abs(n * a_fast) <= lim:
                ax.axvline(n * a_fast, color="#2a78d6", lw=0.9, alpha=0.3)
        # the experiment's hypothesis grid: every shot's grid is snapped onto resonance with this step,
        # so all hypotheses lie on k * step from resonance
        step_Om = float(np.abs(np.diff(d["det0"][0])).mean())
        for kk in range(-20, 21):
            if abs(kk * step_Om) <= lim + 1e-9:
                ax.axvline(kk * step_Om, color="black", lw=2.2, alpha=0.10, zorder=0)
        ax.axvline(0, color="#008300", lw=1.2)
        ax.set_xlim(-lim, lim); ax.set_ylim(0, None)
        ax.set_ylabel("mean posterior\nper fine point")
        _, _, f_s = fold(d, T_slow, f_Om); _, _, f_f = fold(d, T_fast, f_Om)
        near = np.array([abs(d["det2"][r, np.argmax(d["P_wide_final"][r])]) <= WIN for r in range(d["n_shot"])])
        res = mass_near(d, 0.0)
        a_s = 0.5 * (mass_near(d, (1e-3 / T_slow) * 1e3 / f_Om) + mass_near(d, -(1e-3 / T_slow) * 1e3 / f_Om))
        a_f = 0.5 * (mass_near(d, (1e-3 / T_fast) * 1e3 / f_Om) + mass_near(d, -(1e-3 / T_fast) * 1e3 / f_Om))
        nums["runs"][rid] = dict(label=label, fold_slow=f_s, fold_fast=f_f, fine_near=float(near.mean()),
                                 fine_near_sem=float(np.sqrt(near.mean() * (1 - near.mean()) / near.size)),
                                 mass_res=res, alias1_slow_over_res=a_s / res, alias1_fast_over_res=a_f / res, n_shot=int(d["n_shot"]))
        ax.set_title(f"{label}: run {rid}, {d['n_shot']} shots   |   comb at 1/T_slow: {f_s:.2f}×, at 1/T_fast: {f_f:.2f}×   |   "
                     f"localized within ±0.04 Ω: {near.mean():.2f}", fontsize=9, loc="left",
                     pad=(44 if ax is axes[0] else 6))
    sec = axes[0].secondary_xaxis("top", functions=(lambda u: u * f_Om / 1e3, lambda k: k * 1e3 / f_Om))
    sec.set_xlabel("detuning (kHz)", fontsize=9)
    axes[-1].set_xlabel("hypothesis detuning from the calibrated resonance (Ω, units of the Rabi frequency)")
    fig.text(0.5, 0.004, f"orange lines: n/T_slow = n × {a_slow:.3f} Ω ({1e-3/T_slow:.1f} kHz);  blue lines: n/T_fast = n × {a_fast:.3f} Ω "
             f"({1e-3/T_fast:.1f} kHz);  green: resonance;  wide grey: the experiment's hypothesis grid (0.25 Ω)\n"
             f"faint bars: the experiment's own posterior on that grid, averaged over shots.  Each panel marks only its own comb(s).  2026-10-07 cycle 1, 21-pt grid, 17 pulses, Ω/2π = f_Rabi = {f_Om/1e3:.0f} kHz",
             ha="center", va="bottom", fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(os.path.join(HERE, "fig_summary_posteriors.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Figure 2: folded posteriors at the two periods
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, (T, name) in zip(axes, ((T_slow, f"slow period {T_slow*1e6:.1f} µs"), (T_fast, f"fast period {T_fast*1e6:.1f} µs"))):
        for label, rid, col in RUNS:
            x, m, pk = fold(data[rid], T, f_Om)
            ax.plot(x, m, color=col, lw=1.6, label=f"{label.split(' (')[0]} ({pk:.2f}×)")
        ax.axhline(1, color="#888888", lw=0.7)
        ax.set_title(f"folded modulo 1/T at the {name}", fontsize=9)
        ax.set_xlabel("fractional alias order (detuning × T, mod 1)"); ax.grid(alpha=0.18)
        ax.legend(fontsize=7.5, loc="upper right")
    axes[0].set_ylabel("posterior / mean (resonance tooth excluded)")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig_summary_folded.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)

    json.dump(nums, open(os.path.join(HERE, "summary_numbers.json"), "w"), indent=1)
    print(json.dumps(nums, indent=1))


if __name__ == "__main__":
    main()
