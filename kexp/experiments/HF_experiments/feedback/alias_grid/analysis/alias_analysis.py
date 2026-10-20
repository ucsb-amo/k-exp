"""Aliasing analysis of feedback runs replayed on fine hypothesis grids.

    python alias_analysis.py 85351 85352 [85213 85214]

Reads alias_<run>.npz written by alias_replay.py. Produces figures (PNG) and
results.json / results.md in this folder. Every shot is used; no exclusions.

Definitions
  T        mean gap between successive pulse starts in the run (from the recorded
           per-step gaps dT, first N_pulses-1 of each shot)
  f_alias  1/T; hypotheses omega_res + 2*pi*n*f_alias share the drive phase at every
           pulse start when the gaps are constant, so they are near-degenerate
  Omega    2*pi*f_Rabi, f_Rabi = 1/(2 t_pi)
  'near resonance'  |detuning| <= HALF_WIN (Omega units)
  'on alias n'      |detuning - n f_alias| <= HALF_WIN
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
STEP = 0.0125           # fine-grid step, Omega units
HALF_WIN = 0.04         # +/- window for 'on resonance' / 'on alias n' (Omega), ~3 fine steps
PEAK_FRACTION = 0.10    # local maximum counts when >= this fraction of the shot's max

# fixed categorical colours (reference palette): run order is fixed, never cycled
C_FAST = "#2a78d6"      # blue  : fast path (short period)
C_STD = "#eb6834"       # orange: standard path (long period)
C_RES = "#008300"       # green : resonance marker
C_ALIAS = "#8A8A8A"     # gray  : alias comb markers
C_SIM = ("#4a3aa7", "#e87ba4", "#2a78d6")  # synthetic: constant / open random / closed random


def load(rid):
    d = dict(np.load(os.path.join(HERE, f"alias_{rid}.npz"), allow_pickle=True))
    for k, v in d.items():
        if isinstance(v, np.ndarray) and v.ndim == 0:
            d[k] = v.item()
    return d


def bin_mean(det, P):
    """Mean over shots of P on a common detuning axis (exact bins of STEP)."""
    k = np.rint(det / STEP).astype(int)
    kmin, kmax = k.min(), k.max()
    n = kmax - kmin + 1
    s = np.zeros(n); c = np.zeros(n)
    for r in range(P.shape[0]):
        idx = k[r] - kmin
        s[idx] += P[r]; c[idx] += 1
    axis = (np.arange(n) + kmin) * STEP
    with np.errstate(invalid="ignore"):
        m = np.where(c > 0, s / np.maximum(c, 1), np.nan)
    return axis, m, c


def mass_near(det, P, center, half=HALF_WIN):
    """Per-shot posterior mass within +/- half of center (NaN if the grid lacks it)."""
    out = np.full(P.shape[0], np.nan)
    for r in range(P.shape[0]):
        sel = np.abs(det[r] - center) <= half + 1e-9
        if sel.any() and det[r].min() <= center - half + 1e-9 and det[r].max() >= center + half - 1e-9:
            out[r] = P[r, sel].sum()
    return out


def local_maxima(x, p, frac=PEAK_FRACTION):
    pm = p.max()
    idx = np.where((p[1:-1] > p[:-2]) & (p[1:-1] >= p[2:]) & (p[1:-1] >= frac * pm))[0] + 1
    # include edges if they are maxima
    if p.size > 1 and p[0] > p[1] and p[0] >= frac * pm:
        idx = np.r_[0, idx]
    if p.size > 1 and p[-1] > p[-2] and p[-1] >= frac * pm:
        idx = np.r_[idx, p.size - 1]
    return x[idx], p[idx]


def analyse(d):
    rid = d["run_id"]
    Omega = d["Omega"]; f_Om = Omega / (2 * np.pi)
    dT = d["dT_mu_rr"][:, :-1] * 1e-9
    T = float(dT.mean()); T_sd = float(dT.std())
    f_alias = 1.0 / T
    a_Om = f_alias / f_Om                      # alias spacing in Omega units
    n_shot = d["n_shot"]
    res = dict(run_id=rid, n_shot=n_shot, t_pi_us=d["t_pi"] * 1e6, f_rabi_kHz=f_Om / 1e3,
               T_mean_us=T * 1e6, T_sd_us=T_sd * 1e6, T_min_us=dT.min() * 1e6, T_max_us=dT.max() * 1e6,
               f_alias_kHz=f_alias / 1e3, alias_step_Omega=a_Om, grid_step_Omega=0.25,
               grid_step_kHz=0.25 * f_Om / 1e3, grid_step_in_alias_orders=0.25 / a_Om,
               fast_path=bool(d["t_slack_mu"] == 20000),
               validation_max_dP=d["max_dP_kernel_vs_replay"], validation_map_agree=d["map_agree"])
    # how far each production grid point (k*0.25 Omega) sits from the nearest alias order
    res["grid_point_alias_order"] = {f"{0.25*k:.2f}": float(0.25 * k / a_Om) for k in range(1, 5)}

    # ---- kernel (production grid) outcome per shot
    Pk = d["P_kernel_final"]; z0 = d["z0"]
    kmap = np.argmax(Pk, 1)
    coarse_err_bins = kmap - z0
    res["coarse_hit"] = float(np.mean(coarse_err_bins == 0))
    res["coarse_hit_sem"] = float(np.sqrt(res["coarse_hit"] * (1 - res["coarse_hit"]) / n_shot))
    res["coarse_err_hist"] = {str(int(b)): int(c) for b, c in zip(*np.unique(coarse_err_bins, return_counts=True))}

    # ---- fine wide grid, final posterior
    det2, Pw = d["det2"], d["P_wide_final"]
    fmap = np.array([det2[r, np.argmax(Pw[r])] for r in range(n_shot)])
    res["fine_map_detuning_Omega"] = fmap.tolist()
    n_order = fmap / a_Om                       # MAP position in alias orders
    res["fine_map_alias_order"] = n_order.tolist()
    near_res = np.abs(fmap) <= HALF_WIN
    on_alias = (~near_res) & (np.abs(n_order - np.rint(n_order)) * a_Om <= HALF_WIN) & (np.abs(np.rint(n_order)) >= 1)
    res["fine_map_near_resonance"] = float(near_res.mean())
    res["fine_map_on_alias"] = float(on_alias.mean())
    res["fine_map_elsewhere"] = float((~near_res & ~on_alias).mean())
    res["fine_map_alias_orders_hist"] = {str(int(n)): int(c) for n, c in
                                         zip(*np.unique(np.rint(n_order[on_alias]).astype(int), return_counts=True))}
    # posterior mass budget (mean over shots), within +/- HALF_WIN
    res["mass_near_resonance"] = float(np.nanmean(mass_near(det2, Pw, 0.0)))
    res["mass_near_resonance_sem"] = float(np.nanstd(mass_near(det2, Pw, 0.0), ddof=1) / np.sqrt(n_shot))
    res["mass_on_alias"] = {}
    for n in (-3, -2, -1, 1, 2, 3):
        m = mass_near(det2, Pw, n * a_Om)
        res["mass_on_alias"][str(n)] = [float(np.nanmean(m)), int(np.isfinite(m).sum())]
    res["mass_uniform_window"] = float((2 * HALF_WIN / STEP + 1) / Pw.shape[1])

    # width of the main peak (FWHM) for shots whose MAP is near resonance
    fwhm = []
    for r in np.where(near_res)[0]:
        p = Pw[r]; j = np.argmax(p); half = p[j] / 2
        lo = j
        while lo > 0 and p[lo - 1] >= half: lo -= 1
        hi = j
        while hi < p.size - 1 and p[hi + 1] >= half: hi += 1
        fwhm.append((det2[r, hi] - det2[r, lo] + STEP))
    res["main_peak_fwhm_Omega_median"] = float(np.median(fwhm)) if fwhm else np.nan
    res["main_peak_fwhm_kHz_median"] = float(np.median(fwhm) * f_Om / 1e3) if fwhm else np.nan

    # local maxima spacing
    spacings = []; n_peaks = []
    rel_pos = []   # secondary peak positions relative to the main peak, alias orders
    for r in range(n_shot):
        x, p = local_maxima(det2[r], Pw[r])
        n_peaks.append(x.size)
        if x.size > 1:
            spacings.extend(np.diff(np.sort(x)).tolist())
            main = x[np.argmax(p)]
            rel_pos.extend(((x - main) / a_Om)[x != main].tolist())
    spacings = np.array(spacings); rel_pos = np.array(rel_pos)
    res["n_local_maxima_mean"] = float(np.mean(n_peaks))
    res["n_local_maxima_hist"] = {str(int(b)): int(c) for b, c in zip(*np.unique(n_peaks, return_counts=True))}
    res["peak_spacing_kHz_median"] = float(np.median(spacings) * f_Om / 1e3) if spacings.size else np.nan
    res["peak_spacing_kHz_iqr"] = [float(np.percentile(spacings, q) * f_Om / 1e3) for q in (25, 75)] if spacings.size else []
    res["peak_spacing_n"] = int(spacings.size)
    frac_int = np.abs(rel_pos - np.rint(rel_pos))
    res["secondary_peaks_within_0.15_order_of_integer"] = float(np.mean(frac_int <= 0.15)) if rel_pos.size else np.nan
    res["secondary_peaks_n"] = int(rel_pos.size)

    # coarse +/-1-bin errors: where is the fine MAP in those shots?
    sel = np.abs(coarse_err_bins) == 1
    res["coarse_pm1_shots"] = int(sel.sum())
    res["coarse_pm1_fine_map_order"] = n_order[sel].tolist()

    # ---- pulse-by-pulse evolution (span-2.5 fine grid, all steps)
    det1, Pa = d["det1"], d["P_fine_all"].astype(float)
    n_step = Pa.shape[1]
    ev = {"res": [], "alias1": [], "alias2": [], "alias1_n": []}
    for i in range(n_step):
        ev["res"].append(float(np.nanmean(mass_near(det1, Pa[:, i, :], 0.0))))
        m1 = np.nanmean(np.vstack([mass_near(det1, Pa[:, i, :], a_Om), mass_near(det1, Pa[:, i, :], -a_Om)]), axis=0)
        ev["alias1"].append(float(np.nanmean(m1)))
        ev["alias1_n"].append(int(np.isfinite(m1).sum()))
        m2 = np.nanmean(np.vstack([mass_near(det1, Pa[:, i, :], 2 * a_Om), mass_near(det1, Pa[:, i, :], -2 * a_Om)]), axis=0)
        ev["alias2"].append(float(np.nanmean(m2)))
    res["evolution_measured"] = ev

    # ---- synthetic noiseless: alias peak height relative to the resonance peak
    syn = {}
    for key, name in (("P_sim_const_all", "constant_open"), ("P_sim_open_all", "random_open"),
                      ("P_sim_closed_all", "random_closed")):
        Ps = d[key].astype(float)
        ratios = []
        for i in range(Ps.shape[1]):
            r1 = []
            for r in range(n_shot):
                j0 = np.argmin(np.abs(det1[r]))
                for sgn in (1, -1):
                    target = sgn * a_Om
                    if det1[r].min() - 1e-9 <= target <= det1[r].max() + 1e-9:
                        # local maximum nearest the alias order within +/- HALF_WIN
                        sel = np.abs(det1[r] - target) <= HALF_WIN
                        r1.append(Ps[r, i, sel].max() / Ps[r, i, j0])
            ratios.append(float(np.mean(r1)))
        syn[name] = dict(alias1_over_res_by_step=ratios, final=ratios[-1])
        ax, mean_final, _ = bin_mean(det1, Ps[:, -1, :])
        syn[name]["axis"] = ax; syn[name]["mean_final"] = mean_final
    res["synthetic"] = {k: dict(alias1_over_res_by_step=v["alias1_over_res_by_step"], final=v["final"]) for k, v in syn.items()}
    d["_syn"] = syn
    d["_res"] = res
    d["_a_Om"] = a_Om; d["_f_Om"] = f_Om; d["_T"] = T
    return res


# ----------------------------------------------------------------- figures
def fig_synthetic(ds):
    fig, axes = plt.subplots(2, len(ds), figsize=(6.2 * len(ds), 7.6), squeeze=False)
    for c, d in enumerate(ds):
        a = d["_a_Om"]; f_Om = d["_f_Om"]
        for row, (lo, hi, logy) in enumerate(((-2.5, 2.5, True), (-0.75, 0.75, False))):
            ax = axes[row][c]
            for (name, label), col in zip((("constant_open", "constant pulse time, drive on resonance"),
                                           ("random_open", "randomized pulse time, drive on resonance"),
                                           ("random_closed", "randomized pulse time, closed loop")), C_SIM):
                s = d["_syn"][name]
                ax.plot(s["axis"], s["mean_final"], color=col, lw=1.3, label=label, alpha=0.9)
            for n in range(-25, 26):
                if n != 0 and abs(n * a) <= hi:
                    ax.axvline(n * a, color=C_ALIAS, lw=0.6, ls="--", alpha=0.7)
            ax.axvline(0, color=C_RES, lw=1.0)
            for k in range(-10, 11):
                if abs(0.25 * k) <= hi:
                    ax.plot(0.25 * k, 1.2e-6 if logy else 0, marker="|", color="k", ms=10, clip_on=not logy)
            if logy:
                ax.set_yscale("log"); ax.set_ylim(1e-6, 0.1)
            ax.set_xlim(lo, hi)
            ax.set_xlabel("hypothesis detuning from resonance (Ω)")
            ax.set_ylabel("mean final posterior per fine-grid point")
            ax.grid(alpha=0.2)
        axes[0][c].set_title(f"run {d['run_id']} schedule, NOISELESS synthetic, truth on resonance\n"
                             f"f_Rabi {f_Om/1e3:.1f} kHz, mean period {d['_T']*1e6:.1f} µs → 1/T = {1/d['_T']/1e3:.1f} kHz = {a:.3f} Ω",
                             fontsize=9)
        axes[1][c].set_title("zoom ±0.75 Ω, linear", fontsize=9)
    axes[0][0].legend(fontsize=8, loc="lower left")
    fig.text(0.5, -0.01, "dashed gray: n/T alias comb; green: resonance; black ticks: the 21 production grid points (0.25 Ω)",
             ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig1_synthetic_alias_comb.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_measured(ds):
    fig, axes = plt.subplots(2, len(ds), figsize=(6.2 * len(ds), 7.4), squeeze=False)
    for c, d in enumerate(ds):
        a = d["_a_Om"]; f_Om = d["_f_Om"]
        col = C_FAST if d["_res"]["fast_path"] else C_STD
        ax, m, cnt = bin_mean(d["det2"], d["P_wide_final"])
        for row, (lo, hi) in enumerate(((-2.5, 2.5), (-1.0, 1.0))):
            axx = axes[row][c]
            axx.plot(ax * f_Om / 1e3, m, color=col, lw=1.4)
            for n in range(-40, 41):
                if n != 0 and abs(n * a) <= hi:
                    axx.axvline(n * a * f_Om / 1e3, color=C_ALIAS, lw=0.6, ls="--", alpha=0.7)
            axx.axvline(0, color=C_RES, lw=1.0)
            for k in range(-10, 11):
                if abs(0.25 * k) <= hi:
                    axx.plot(0.25 * k * f_Om / 1e3, 0, marker="|", color="k", ms=10, clip_on=False)
            axx.set_xlim(lo * f_Om / 1e3, hi * f_Om / 1e3)
            axx.set_xlabel("hypothesis detuning from resonance (kHz)")
            axx.set_ylabel("mean final posterior per fine-grid point")
            axx.grid(alpha=0.2)
        axes[0][c].set_title(f"run {d['run_id']} ({'fast' if d['_res']['fast_path'] else 'standard'} path), measured, "
                             f"{d['n_shot']} shots\nf_Rabi {f_Om/1e3:.1f} kHz, period {d['_T']*1e6:.1f} µs → "
                             f"1/T = {1/d['_T']/1e3:.1f} kHz = {a:.3f} Ω; grid step {0.25*f_Om/1e3:.1f} kHz", fontsize=9)
        axes[1][c].set_title("zoom ±1 Ω", fontsize=9)
    fig.text(0.5, -0.01, "dashed gray: n/T alias comb from the run's own recorded gaps; green: resonance; black ticks: production grid points",
             ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig2_measured_mean_posterior.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_map_hist(ds):
    fig, axes = plt.subplots(2, 1, figsize=(10, 7))
    bins_kHz = np.arange(-200, 201, 5.0)
    bins_ord = np.arange(-6.125, 6.126, 0.25)
    for d in ds:
        r = d["_res"]; col = C_FAST if r["fast_path"] else C_STD
        f_Om = d["_f_Om"]
        fmap_kHz = np.array(r["fine_map_detuning_Omega"]) * f_Om / 1e3
        lab = f"run {d['run_id']} ({'fast' if r['fast_path'] else 'std'}; 1/T {r['f_alias_kHz']:.1f} kHz)"
        axes[0].hist(fmap_kHz, bins=bins_kHz, histtype="step", lw=1.6, color=col, label=lab, alpha=0.9)
        axes[1].hist(np.array(r["fine_map_alias_order"]), bins=bins_ord, histtype="step", lw=1.6, color=col, label=lab, alpha=0.9)
    for n in range(-6, 7):
        axes[1].axvline(n, color=C_ALIAS, lw=0.6, ls="--")
    axes[0].set_xlabel("final fine-grid MAP detuning from resonance (kHz)"); axes[0].set_ylabel("shots")
    axes[1].set_xlabel("final fine-grid MAP detuning in alias orders (detuning × T)"); axes[1].set_ylabel("shots")
    axes[0].set_title("Where the fine-grid (0.0125 Ω) posterior peaks at the end of each shot — measured runs", fontsize=10)
    axes[1].set_title("Same, scaled by each run's own period: integer values = alias of resonance", fontsize=10)
    axes[0].legend(fontsize=8); axes[0].grid(alpha=0.2); axes[1].grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig3_fine_map_histograms.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_spacing(ds):
    fig, axes = plt.subplots(1, len(ds), figsize=(5.2 * len(ds), 3.8), squeeze=False)
    for ax, d in zip(axes[0], ds):
        r = d["_res"]; col = C_FAST if r["fast_path"] else C_STD; f_Om = d["_f_Om"]
        sp = []
        for s in range(d["n_shot"]):
            x, p = local_maxima(d["det2"][s], d["P_wide_final"][s])
            if x.size > 1:
                sp.extend(np.diff(np.sort(x)).tolist())
        sp = np.array(sp) * f_Om / 1e3
        ax.hist(sp, bins=np.arange(0, 80.1, 2.0), color=col, alpha=0.85)
        for n in (1, 2, 3):
            ax.axvline(n * r["f_alias_kHz"], color=C_ALIAS, lw=0.8, ls="--")
        ax.axvline(r["grid_step_kHz"], color="k", lw=0.8, ls=":")
        ax.set_xlabel("spacing between adjacent local maxima (kHz)"); ax.set_ylabel("count")
        ax.set_title(f"run {d['run_id']}: {sp.size} spacings in {d['n_shot']} shots\n"
                     f"dashed: n/T = {r['f_alias_kHz']:.1f} kHz × n; dotted: grid step {r['grid_step_kHz']:.1f} kHz", fontsize=9)
        ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig4_local_maxima_spacing.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_evolution(ds):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for d in ds:
        r = d["_res"]; col = C_FAST if r["fast_path"] else C_STD
        ev = r["evolution_measured"]; steps = np.arange(1, len(ev["res"]) + 1)
        lab = f"run {d['run_id']} ({'fast' if r['fast_path'] else 'std'})"
        axes[0].plot(steps, ev["res"], color=col, lw=1.8, marker="o", ms=4, label=lab + " — resonance")
        axes[0].plot(steps, ev["alias1"], color=col, lw=1.2, ls="--", marker="s", ms=3, label=lab + " — alias n=±1")
        axes[0].plot(steps, ev["alias2"], color=col, lw=1.0, ls=":", marker="^", ms=3, label=lab + " — alias n=±2")
    axes[0].set_xlabel("pulse index"); axes[0].set_ylabel(f"mean posterior mass within ±{HALF_WIN} Ω")
    axes[0].set_title("MEASURED: posterior mass at resonance vs on the first aliases, pulse by pulse", fontsize=10)
    axes[0].legend(fontsize=7, ncol=2); axes[0].grid(alpha=0.2)
    for d in ds[:2]:
        r = d["_res"]; col = C_FAST if r["fast_path"] else C_STD
        for (name, ls, lab) in (("constant_open", "-", "constant pulse, open"), ("random_open", "--", "random pulse, open"),
                                ("random_closed", ":", "random pulse, closed")):
            y = r["synthetic"][name]["alias1_over_res_by_step"]
            axes[1].plot(np.arange(1, len(y) + 1), y, color=col, ls=ls, lw=1.5, label=f"run {d['run_id']} schedule — {lab}")
    axes[1].set_yscale("log"); axes[1].set_xlabel("pulse index")
    axes[1].set_ylabel("P(alias n=±1) / P(resonance)")
    axes[1].set_title("NOISELESS synthetic: how fast the model itself suppresses the first alias", fontsize=10)
    axes[1].legend(fontsize=7); axes[1].grid(alpha=0.2, which="both")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig5_alias_vs_pulse_index.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_shots(d, n_show=6):
    """A few individual shots: kernel 21-point posterior vs the fine 801-point one."""
    r = d["_res"]; f_Om = d["_f_Om"]; a = d["_a_Om"]
    fmap = np.array(r["fine_map_detuning_Omega"])
    order = np.array(r["fine_map_alias_order"])
    # pick: 2 shots with MAP on resonance, 2 on an alias, 2 elsewhere (first in each class)
    cls_res = np.where(np.abs(fmap) <= HALF_WIN)[0]
    cls_al = np.where((np.abs(fmap) > HALF_WIN) & (np.abs(order - np.rint(order)) * a <= HALF_WIN))[0]
    cls_el = np.setdiff1d(np.arange(d["n_shot"]), np.r_[cls_res, cls_al])
    picks = list(cls_res[:2]) + list(cls_al[:2]) + list(cls_el[:2])
    fig, axes = plt.subplots(2, 3, figsize=(15, 6.5))
    for ax, s in zip(axes.ravel(), picks):
        x2 = d["det2"][s] * f_Om / 1e3; p2 = d["P_wide_final"][s]
        x0 = d["det0"][s] * f_Om / 1e3; p0 = d["P_kernel_final"][s]
        ax.plot(x2, p2 / p2.max(), color=C_FAST if r["fast_path"] else C_STD, lw=1.2, label="801-pt replay (÷ max)")
        ax.plot(x0, p0 / p0.max(), "k.", ms=7, label="kernel 21-pt (÷ max)")
        for n in range(-30, 31):
            if n != 0:
                ax.axvline(n * a * f_Om / 1e3, color=C_ALIAS, lw=0.5, ls="--", alpha=0.6)
        ax.axvline(0, color=C_RES, lw=1.0)
        ax.set_xlim(-2.5 * f_Om / 1e3, 2.5 * f_Om / 1e3)
        ax.set_title(f"shot {s}, offset {d['offsets'][s]:+.2f} Ω; fine MAP {fmap[s]*f_Om/1e3:+.1f} kHz = {order[s]:+.2f} orders",
                     fontsize=8)
        ax.set_xlabel("detuning (kHz)"); ax.grid(alpha=0.2)
    axes[0][0].legend(fontsize=7)
    fig.suptitle(f"run {d['run_id']}: individual final posteriors, production grid vs fine grid "
                 f"(1/T = {r['f_alias_kHz']:.1f} kHz)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, f"fig6_shots_{d['run_id']}.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(rids):
    ds = [load(r) for r in rids]
    results = [analyse(d) for d in ds]
    fig_synthetic(ds[:2]); fig_measured(ds); fig_map_hist(ds); fig_spacing(ds); fig_evolution(ds)
    for d in ds[:2]:
        fig_shots(d)
    # strip arrays for json
    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(results, f, indent=1, default=float)
    for r in results:
        print(f"\n=== run {r['run_id']} ({'fast' if r['fast_path'] else 'standard'}) ===")
        for k in ("t_pi_us", "f_rabi_kHz", "T_mean_us", "T_sd_us", "T_min_us", "T_max_us", "f_alias_kHz", "alias_step_Omega",
                  "grid_step_kHz", "grid_step_in_alias_orders", "grid_point_alias_order", "validation_max_dP",
                  "coarse_hit", "coarse_hit_sem", "coarse_err_hist", "fine_map_near_resonance", "fine_map_on_alias",
                  "fine_map_elsewhere", "fine_map_alias_orders_hist", "mass_near_resonance", "mass_near_resonance_sem",
                  "mass_on_alias", "mass_uniform_window", "main_peak_fwhm_kHz_median", "n_local_maxima_mean",
                  "n_local_maxima_hist", "peak_spacing_kHz_median", "peak_spacing_kHz_iqr", "peak_spacing_n",
                  "secondary_peaks_within_0.15_order_of_integer", "secondary_peaks_n", "coarse_pm1_shots",
                  "coarse_pm1_fine_map_order"):
            v = r[k]
            if isinstance(v, float):
                v = f"{v:.4g}"
            elif isinstance(v, list) and v and isinstance(v[0], float):
                v = "[" + ", ".join(f"{x:.2f}" for x in v) + "]"
            print(f"  {k}: {v}")
        print("  synthetic final P(alias1)/P(res):", {k: f"{v['final']:.3g}" for k, v in r["synthetic"].items()})
        ev = r["evolution_measured"]
        print("  measured mass res by step:", " ".join(f"{x:.2f}" for x in ev["res"]))
        print("  measured mass alias1 by step:", " ".join(f"{x:.2f}" for x in ev["alias1"]))
        print("  measured mass alias2 by step:", " ".join(f"{x:.2f}" for x in ev["alias2"]))


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
