"""Folded-comb tests of inter-pulse-time aliasing (read-only; uses alias_<run>.npz).

    python alias_folded.py 85351 85352 85213 85214

1. FOLDED FINE POSTERIOR. Each shot's final 801-point posterior (span 5 Omega) is
   expressed in alias orders u = detuning * T (T = the run's mean pulse-start
   period). Points with |u| < 0.5 (the resonance peak itself) are dropped; the rest
   are folded to frac(u) in [-0.5, 0.5) and the mean posterior per fold bin is
   shown. Aliasing of resonance => a peak at 0; no aliasing => flat.
   Control: the same fold with a wrong period (T * 0.8).
2. RAYLEIGH TEST on the fine-grid MAP positions away from resonance: angle
   2*pi*frac(u_MAP); R = |mean(exp(i*angle))|, p = exp(-n R^2) (large-n approx).
3. PRODUCTION-GRID ERRORS VS ALIAS PROXIMITY. For every shot and every production
   grid point k (0.25 Omega steps) other than the resonant one: its alias order
   u_k = 0.25*k*f_Rabi*T, the distance |u_k - round(u_k)|, the kernel's recorded
   final posterior there, and whether the kernel's MAP sat there. Pooled over
   runs, binned by distance to the nearest integer order.
Every shot counted; nothing excluded.
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
COL = {True: "#2a78d6", False: "#eb6834"}


def load(rid):
    d = dict(np.load(os.path.join(HERE, f"alias_{rid}.npz"), allow_pickle=True))
    return {k: (v.item() if isinstance(v, np.ndarray) and v.ndim == 0 else v) for k, v in d.items()}


def fold(det_Om, P, f_Om, T, u_min=0.5, nb=40, scale=1.0):
    u = det_Om * f_Om * T * scale
    sel = np.abs(u) >= u_min
    frac = (u[sel] + 0.5) % 1.0 - 0.5
    edges = np.linspace(-0.5, 0.5, nb + 1)
    idx = np.clip(np.digitize(frac, edges) - 1, 0, nb - 1)
    s = np.bincount(idx, weights=P[sel], minlength=nb)
    c = np.bincount(idx, minlength=nb)
    return 0.5 * (edges[1:] + edges[:-1]), s / np.maximum(c, 1), c


def main(rids):
    ds = [load(r) for r in rids]
    out = []
    fig, axes = plt.subplots(1, len(ds), figsize=(4.8 * len(ds), 3.8), squeeze=False)
    pooled = []  # (run, k, dist_to_int, mean_P, n_map)
    for ax, d in zip(axes[0], ds):
        rid = d["run_id"]; f_Om = d["Omega"] / (2 * np.pi)
        T = float((d["dT_mu_rr"][:, :-1] * 1e-9).mean())
        fast = d["t_slack_mu"] == 20000
        det2, P = d["det2"], d["P_wide_final"]
        x, m, c = fold(det2, P, f_Om, T)
        x8, m8, _ = fold(det2, P, f_Om, T, scale=0.8)
        ax.plot(x, m / m.mean(), color=COL[fast], lw=1.8, label=f"folded at T = {T*1e6:.1f} µs")
        ax.plot(x8, m8 / m8.mean(), color="#8a8a8a", lw=1.2, ls="--", label="control: folded at 0.8 T")
        ax.axhline(1, color="k", lw=0.5)
        ax.set_xlabel("fractional alias order  (detuning × T, mod 1)")
        ax.set_ylabel("mean posterior / overall mean")
        ax.set_title(f"run {rid} ({'fast' if fast else 'standard'}), |order| ≥ 0.5 only", fontsize=9)
        ax.grid(alpha=0.2); ax.legend(fontsize=7)
        peak = float(m[np.abs(x) < 0.1].mean() / m.mean())
        trough = float(m[np.abs(np.abs(x) - 0.5) < 0.1].mean() / m.mean())
        peak8 = float(m8[np.abs(x8) < 0.1].mean() / m8.mean())

        # Rayleigh on MAP positions away from resonance
        fmap = np.array([det2[r, np.argmax(P[r])] for r in range(P.shape[0])]) * f_Om * T
        far = np.abs(fmap) >= 0.5
        ang = 2 * np.pi * fmap[far]
        R = float(np.abs(np.mean(np.exp(1j * ang)))); n = int(far.sum())
        p_ray = float(np.exp(-n * R * R))
        ang8 = 2 * np.pi * fmap[far] * 0.8
        R8 = float(np.abs(np.mean(np.exp(1j * ang8)))); p8 = float(np.exp(-n * R8 * R8))

        # production grid: posterior and MAP at each non-resonant grid point vs alias proximity
        Pk, z0, det0 = d["P_kernel_final"], d["z0"], d["det0"]
        kmap = np.argmax(Pk, 1)
        rows = []
        for r in range(Pk.shape[0]):
            for j in range(Pk.shape[1]):
                if j == z0[r]:
                    continue
                u = det0[r, j] * f_Om * T
                rows.append((u, abs(u - round(u)), Pk[r, j], int(kmap[r] == j), det0[r, j]))
        rows = np.array(rows)
        pooled.append((rid, rows))
        # per grid offset k: distance to integer, mean P, MAP count
        per_k = {}
        for k in range(-6, 7):
            if k == 0:
                continue
            sel = np.isclose(rows[:, 4], 0.25 * k, atol=1e-6)
            if sel.any():
                per_k[k] = dict(alias_order=float(0.25 * k * f_Om * T), dist=float(rows[sel, 1][0]),
                                mean_P=float(rows[sel, 2].mean()), n_shots_with_point=int(sel.sum()),
                                n_map=int(rows[sel, 3].sum()))
        out.append(dict(run_id=rid, fast=bool(fast), T_us=T * 1e6, f_alias_kHz=1e-3 / T,
                        fold_peak_over_mean=peak, fold_trough_over_mean=trough, fold_control_peak_over_mean=peak8,
                        rayleigh_n=n, rayleigh_R=R, rayleigh_p=p_ray, rayleigh_control_R=R8, rayleigh_control_p=p8,
                        per_k=per_k))
    fig.suptitle("Fine-grid posterior folded modulo the alias period 1/T (resonance peak excluded)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig7_folded_comb.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    # pooled production-grid test
    allrows = np.vstack([r for _, r in pooled])
    edges = np.array([0, 0.1, 0.2, 0.3, 0.4, 0.5])
    idx = np.digitize(allrows[:, 1], edges) - 1
    tab = []
    for b in range(5):
        sel = idx == b
        tab.append(dict(dist_bin=[float(edges[b]), float(edges[b + 1])], n_points=int(sel.sum()),
                        mean_kernel_P=float(allrows[sel, 2].mean()) if sel.any() else np.nan,
                        sem=float(allrows[sel, 2].std(ddof=1) / np.sqrt(sel.sum())) if sel.sum() > 1 else np.nan,
                        map_rate=float(allrows[sel, 3].mean()) if sel.any() else np.nan,
                        n_map=int(allrows[sel, 3].sum())))
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    xb = [0.5 * (t["dist_bin"][0] + t["dist_bin"][1]) for t in tab]
    ax[0].errorbar(xb, [t["mean_kernel_P"] for t in tab], yerr=[t["sem"] for t in tab], fmt="o-", color="#4a3aa7", capsize=3)
    ax[0].set_xlabel("distance of the grid point from the nearest integer alias order"); ax[0].set_ylabel("mean kernel posterior at that grid point")
    ax[0].set_title("Production 21-pt grid, non-resonant points, 4 runs pooled", fontsize=9); ax[0].grid(alpha=0.2)
    ax[1].bar(xb, [t["map_rate"] for t in tab], width=0.08, color="#4a3aa7")
    ax[1].set_xlabel("distance of the grid point from the nearest integer alias order"); ax[1].set_ylabel("fraction of shots whose kernel MAP sat there")
    ax[1].set_title("Wrong-bin MAP rate vs alias proximity", fontsize=9); ax[1].grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig8_coarse_grid_vs_alias_proximity.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    with open(os.path.join(HERE, "results_folded.json"), "w") as f:
        json.dump(dict(runs=out, pooled_grid=tab), f, indent=1, default=float)
    for o in out:
        print(f"run {o['run_id']} ({'fast' if o['fast'] else 'std'}): T {o['T_us']:.2f} us, 1/T {o['f_alias_kHz']:.2f} kHz | "
              f"fold peak/mean {o['fold_peak_over_mean']:.3f}, trough/mean {o['fold_trough_over_mean']:.3f}, "
              f"control(0.8T) peak/mean {o['fold_control_peak_over_mean']:.3f} | Rayleigh n {o['rayleigh_n']} R {o['rayleigh_R']:.3f} "
              f"p {o['rayleigh_p']:.2e} (control R {o['rayleigh_control_R']:.3f} p {o['rayleigh_control_p']:.2f})")
        for k, v in sorted(o["per_k"].items()):
            print(f"    k {k:+d} ({0.25*k:+.2f} Om): order {v['alias_order']:.2f} dist {v['dist']:.2f} meanP {v['mean_P']:.4f} "
                  f"MAP {v['n_map']}/{v['n_shots_with_point']}")
    print("pooled production grid by distance to integer alias order:")
    for t in tab:
        print(f"   {t['dist_bin']}: n {t['n_points']} meanP {t['mean_kernel_P']:.4f} +/- {t['sem']:.4f}  MAP rate {t['map_rate']:.4f} ({t['n_map']})")


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
