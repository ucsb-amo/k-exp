"""SYNTHETIC ONLY: two-, three- and four-gap cycles vs the alias comb, on one run's shots.

    python alias_cycle_sim.py <run_id> [n_seeds]

Same engine as alias_schedule_sim.py (85352 shots, model as written, truth on
resonance, gaps replaced via a patched _compute_dT_rr_mu, pulse areas untouched).
All cycles are built on the fast-path gap T_f (recorded gap shifted to slack 20 us,
46.9 us at this run's pulse times) plus a repeating list of extra delays:

  fast          [0]
  std           [20]                      (the standard gap, 66.6 us)
  alt2_0_20     [0, 20]                   mean 56.9 us  (fast / standard)
  alt3_0_10_20  [0, 10, 20]               mean 56.9 us  (same mean time as alt2)
  alt3_0_20_40  [0, 20, 40]               mean 66.9 us  (same mean time as std)
  alt3_phi      [0, 29, 76]               T_f x (1, phi, phi^2), mean 81.9 us
  alt4_0_10_20_30 [0, 10, 20, 30]         mean 61.9 us
  rand_0_20     uniform [0, 20] per gap   mean 56.9 us  (random control at alt2's mean)
  rand_0_40     uniform [0, 40] per gap   mean 66.9 us

Metrics:
  noiseless open loop, drive on resonance, 401-pt fine grid over +/-2.5 Omega:
     sec/res  = mean over shots of (largest local maximum with |detuning| > 0.05 Omega) / P(resonance)
     sec_kHz  = median |detuning| of that largest secondary peak
     a1/res   = P at +/- 1/T_mean over P(resonance)  (the old first alias)
  with the stored photon noise, closed loop on the 21-pt grid, n_seeds x 105 shots:
     hit21, MAP on +/-1 bin, fine MAP within +/-0.04 Omega, mass within +/-0.04 Omega
Design calculation on the model. Nothing written back.
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
HALF_WIN = 0.04
ALIGN = ~np.int64(7)
PHI = (1 + 5 ** 0.5) / 2


def mass_near(det, P, center, half=HALF_WIN):
    out = np.full(P.shape[0], np.nan)
    for r in range(P.shape[0]):
        sel = np.abs(det[r] - center) <= half + 1e-9
        if sel.any() and det[r].min() <= center - half + 1e-9 and det[r].max() >= center + half - 1e-9:
            out[r] = P[r, sel].sum()
    return out


def local_max_mask(p):
    m = np.zeros(p.size, bool)
    m[1:-1] = (p[1:-1] > p[:-2]) & (p[1:-1] >= p[2:])
    return m


def main(rid, n_seeds=5):
    from kexp import atomdata
    from kexp.analysis import FeedbackReplay

    ad = atomdata(rid, roi_id='auto', lite=False)
    fr = FeedbackReplay(ad)
    m0 = int(fr.m); span0 = float(np.ravel(ad.p.feedback_guess_span_Omega)[0]); m1 = 20 * (m0 - 1) + 1
    t_rr = np.asarray(ad.data.t_raman_pulse, float).reshape(-1, int(ad.p.N_pulses))
    n_shot, n_step = t_rr.shape
    f_Om = fr.Omega / (2 * np.pi)
    base_compute = fr._compute_dT_rr_mu
    rec = base_compute(t_rr).astype(np.int64)
    T_rec = float(rec[:, :-1].mean())
    T_f = T_rec - (float(ad.p.t_calculation_slack_compensation_mu) - 20000.0)
    fastg = rec + np.int64(round(T_f - T_rec))
    rng = np.random.default_rng(777)
    i_idx = np.arange(n_step)

    def cyc(extra_us):
        e = np.array(extra_us, float) * 1e3
        return (fastg + e[i_idx % len(e)].astype(np.int64)[None, :]) & ALIGN

    schedules = {
        "fast": cyc([0]),
        "std": cyc([20]),
        "alt2_0_20": cyc([0, 20]),
        "alt3_0_10_20": cyc([0, 10, 20]),
        "alt3_0_20_40": cyc([0, 20, 40]),
        "alt3_phi": cyc([0, T_f * (PHI - 1) * 1e-3, T_f * (PHI ** 2 - 1) * 1e-3]),
        "alt4_0_10_20_30": cyc([0, 10, 20, 30]),
        "rand_0_20": (fastg + rng.integers(0, 20000, size=(n_shot, n_step))) & ALIGN,
        "rand_0_40": (fastg + rng.integers(0, 40000, size=(n_shot, n_step))) & ALIGN,
    }
    omega_res_rr = np.full((n_shot, n_step), fr._omega_resonance_rad_s)

    def grids(nsh):
        off = fr._resolve_fractional_initial_offset_r(n_repeat=nsh)
        g = np.array([fr._grid_for_offset(float(o))[0] for o in off])
        return (g - fr._omega_resonance_rad_s) / fr.Omega

    results = {}
    for name, gaps in schedules.items():
        fr._compute_dT_rr_mu = lambda t, _g=gaps: _g.copy()
        T = float(gaps[:, :-1].mean()) * 1e-9
        a_Om = (1.0 / T) / f_Om

        fr.p.feedback_grid_size = m0; fr.p.feedback_guess_span_Omega = span0
        sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=1, noise_scale=0.0, omega_control_rr=omega_res_rr)
        fr.p.feedback_grid_size = m1
        res = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=omega_res_rr, control_omega_source='override')
        det1 = grids(n_shot); Pf = res.P0_rr[:, -1, :]
        sec, sec_pos, a1 = [], [], []
        for r in range(n_shot):
            j0 = np.argmin(np.abs(det1[r])); p0 = Pf[r, j0]
            lm = local_max_mask(Pf[r]) & (np.abs(det1[r]) > 0.05)
            if lm.any():
                j = np.argmax(np.where(lm, Pf[r], -1)); sec.append(Pf[r, j] / p0); sec_pos.append(abs(det1[r, j]) * f_Om / 1e3)
            for sgn in (1, -1):
                tgt = sgn * a_Om
                if det1[r].min() - 1e-9 <= tgt <= det1[r].max() + 1e-9:
                    a1.append(Pf[r, np.abs(det1[r] - tgt) <= HALF_WIN].max() / p0)

        hit, pm1, near, mres = [], [], [], []
        for seed in range(n_seeds):
            fr.p.feedback_grid_size = m0
            sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=100 + seed, noise_scale=1.0)
            r21 = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det0 = grids(n_shot); P21 = r21.P0_rr[:, -1, :]
            z = np.array([np.argmin(np.abs(det0[r])) for r in range(n_shot)]); am = np.argmax(P21, 1)
            hit.extend((am == z).astype(float)); pm1.extend((np.abs(am - z) == 1).astype(float))
            fr.p.feedback_grid_size = m1
            rf = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det1 = grids(n_shot); Pf = rf.P0_rr[:, -1, :]
            fmap = np.array([det1[r, np.argmax(Pf[r])] for r in range(n_shot)])
            near.extend((np.abs(fmap) <= HALF_WIN).astype(float)); mres.extend(mass_near(det1, Pf, 0.0))

        def ms(x):
            x = np.asarray(x, float); x = x[np.isfinite(x)]; return float(x.mean()), float(x.std(ddof=1) / np.sqrt(x.size))
        out = dict(T_mean_us=T * 1e6, total_sequence_ms=float(gaps[:, :-1].sum(1).mean()) * 1e-6,
                   sec_over_res=float(np.mean(sec)), sec_kHz_median=float(np.median(sec_pos)),
                   a1_over_res=float(np.mean(a1)) if a1 else np.nan, n_shots=len(hit))
        for k, v in (("hit21", hit), ("pm1", pm1), ("fine_near", near), ("mass_res", mres)):
            out[k], out[k + "_sem"] = ms(v)
        results[name] = out
        print(f"{name:16s} T {out['T_mean_us']:5.1f} us total {out['total_sequence_ms']:.2f} ms | sec/res {out['sec_over_res']:.3f} at {out['sec_kHz_median']:5.1f} kHz, "
              f"a1/res {out['a1_over_res']:.3f} | hit21 {out['hit21']:.3f}+/-{out['hit21_sem']:.3f} pm1 {out['pm1']:.3f} | "
              f"fine_near {out['fine_near']:.3f}+/-{out['fine_near_sem']:.3f} mass_res {out['mass_res']:.4f}+/-{out['mass_res_sem']:.4f}", flush=True)
    fr._compute_dT_rr_mu = base_compute

    with open(os.path.join(HERE, f"cycle_sim_{rid}.json"), "w") as f:
        json.dump(results, f, indent=1)
    names = list(results); x = np.arange(len(names))
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.4))
    ax[0].bar(x - 0.2, [results[k]["a1_over_res"] for k in names], width=0.4, color="#8a8a8a", label="P at ±1/T_mean / P(res)")
    ax[0].bar(x + 0.2, [results[k]["sec_over_res"] for k in names], width=0.4, color="#4a3aa7", label="largest secondary peak / P(res)")
    ax[0].set_ylabel("noiseless, open loop"); ax[0].set_ylim(0, 1.05); ax[0].legend(fontsize=8)
    ax[1].errorbar(x - 0.1, [results[k]["hit21"] for k in names], yerr=[results[k]["hit21_sem"] for k in names], fmt="o", color="#eb6834", capsize=3, label="21-pt hit")
    ax[1].errorbar(x + 0.1, [results[k]["pm1"] for k in names], yerr=[results[k]["pm1_sem"] for k in names], fmt="s", color="#8a8a8a", capsize=3, label="MAP on ±1 bin")
    ax[1].set_ylim(0, 0.7); ax[1].legend(fontsize=8); ax[1].set_ylabel("fraction of synthetic shots")
    ax[2].errorbar(x - 0.1, [results[k]["fine_near"] for k in names], yerr=[results[k]["fine_near_sem"] for k in names], fmt="o", color="#2a78d6", capsize=3, label="fine MAP within ±0.04 Ω")
    ax[2].errorbar(x + 0.1, [2 * results[k]["mass_res"] for k in names], yerr=[2 * results[k]["mass_res_sem"] for k in names], fmt="^", color="#008300", capsize=3, label="2 × mass within ±0.04 Ω")
    ax[2].legend(fontsize=8); ax[2].set_ylabel("fine-grid localization")
    for a in ax:
        a.set_xticks(x); a.set_xticklabels([f"{k}\n{results[k]['T_mean_us']:.0f} µs" for k in names], rotation=45, ha="right", fontsize=8); a.grid(alpha=0.2)
    fig.suptitle(f"SYNTHETIC: gap cycles on run {rid}'s shots (f_Rabi {f_Om/1e3:.1f} kHz, stored noise), {n_seeds} × {n_shot} shots; extras in µs on the fast-path gap", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "fig12_gap_cycles.png"), dpi=170, bbox_inches="tight")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)
