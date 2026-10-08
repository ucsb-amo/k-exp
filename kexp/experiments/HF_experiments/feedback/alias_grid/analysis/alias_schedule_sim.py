"""SYNTHETIC ONLY: pulse-start schedules vs the 1/T alias, on one run's shots.

    python alias_schedule_sim.py <run_id> [n_seeds]

Uses the run's shots (offsets, drawn pulse times, calibration, 21-pt production
grid) and re-synthesises data with the model as written (truth on the nominal
resonance), replacing only the inter-pulse gaps through a patched
_compute_dT_rr_mu (pulse areas untouched; the per-shot pulse-time jitter in
the gaps is kept where a schedule is 'recorded + constant').

Schedules (T_f = recorded gap shifted to the fast-path value, 46.9 us at this
run's pulse times; f = f_Rabi; 'order' = 0.25*f*T, the alias order of the first
off-resonant production grid point):
  std_recorded      recorded gaps (T 66.6 us, order 2.20)
  fast              T_f (order 1.55)
  anti_k1           T with order 1.5 exactly  (45.4 us)
  anti_k2           T with order 2.5 exactly  (75.7 us)
  worst_k2          T with order 2.0 exactly  (60.6 us): +/-0.25 Omega points ON the n=2 teeth
  alt_1_2           alternating T_f, 2 T_f               (mean 70 us)
  alt_std_fast      alternating 66.6, 46.9 us            (mean 56.8 us)
  geo_1p1           T_f * 1.1^i, i = gap index           (46.9 .. 196 us, total 1.49 ms)
  rand_Tf           T_f + uniform[0, T_f] per gap        (mean 70 us)

Per schedule, per seed: closed loop on the 21-pt grid with the stored photon
noise (noise_scale 1), then replay of the same synthetic shots on the 401-pt
grid. Metrics pooled over seeds (n_seeds x 105 shots):
  hit21        kernel-equivalent MAP on the resonant production point
  pm1          MAP on a +/-1 production bin
  P_res21      mean posterior on the resonant production point
  fine_near    fine MAP within +/-0.04 Omega of resonance
  mass_res     mean fine mass within +/-0.04 Omega of resonance
  mass_a1      same at +/- 1/T_mean (NaN-aware)
and, noiseless open loop on resonance: P(alias +/-1)/P(res) at 1/T_mean.
Design calculation on the model, not a measurement. Nothing written back.
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


def mass_near(det, P, center, half=HALF_WIN):
    out = np.full(P.shape[0], np.nan)
    for r in range(P.shape[0]):
        sel = np.abs(det[r] - center) <= half + 1e-9
        if sel.any() and det[r].min() <= center - half + 1e-9 and det[r].max() >= center + half - 1e-9:
            out[r] = P[r, sel].sum()
    return out


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
    rec = base_compute(t_rr).astype(np.int64)                       # recorded gaps (ns)
    T_rec = float(rec[:, :-1].mean())                                # ns
    T_fast = T_rec - (float(ad.p.t_calculation_slack_compensation_mu) - 20000.0)   # fast-path slack 20 us
    fastg = rec + np.int64(round(T_fast - T_rec))                    # recorded jitter kept
    step_T = 1e9 / (0.25 * f_Om)                                     # ns per alias order of the 0.25-Omega point
    rng = np.random.default_rng(2026)
    i_idx = np.arange(n_step)[None, :]

    def shift_to(order):
        return rec + np.int64(round(order * step_T - T_rec))

    schedules = {
        "std_recorded": rec,
        "fast": fastg,
        "anti_k1": shift_to(1.5),
        "anti_k2": shift_to(2.5),
        "worst_k2": shift_to(2.0),
        "alt_1_2": fastg + np.int64(round(T_fast)) * (i_idx % 2),
        "alt_std_fast": fastg + np.int64(round(T_rec - T_fast)) * ((i_idx + 1) % 2),
        "geo_1p1": (fastg * 1.1 ** i_idx).astype(np.int64),
        "rand_Tf": fastg + rng.integers(0, int(T_fast), size=(n_shot, n_step)).astype(np.int64),
    }
    schedules = {k: (v & ALIGN) for k, v in schedules.items()}
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
        total_ms = float(gaps[:, :-1].sum(1).mean()) * 1e-6

        # noiseless open loop on resonance -> alias ratio at 1/T_mean
        fr.p.feedback_grid_size = m0; fr.p.feedback_guess_span_Omega = span0
        sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=1, noise_scale=0.0, omega_control_rr=omega_res_rr)
        fr.p.feedback_grid_size = m1
        res = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=omega_res_rr, control_omega_source='override')
        det1 = grids(n_shot); Pf = res.P0_rr[:, -1, :]
        ratios = []
        for r in range(n_shot):
            j0 = np.argmin(np.abs(det1[r]))
            for sgn in (1, -1):
                tgt = sgn * a_Om
                if det1[r].min() - 1e-9 <= tgt <= det1[r].max() + 1e-9:
                    ratios.append(Pf[r, np.abs(det1[r] - tgt) <= HALF_WIN].max() / Pf[r, j0])
        alias_ratio = float(np.mean(ratios)) if ratios else np.nan

        hit, pm1, pres, near, mres, ma1 = [], [], [], [], [], []
        for seed in range(n_seeds):
            fr.p.feedback_grid_size = m0
            sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=100 + seed, noise_scale=1.0)
            r21 = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det0 = grids(n_shot); P21 = r21.P0_rr[:, -1, :]
            z = np.array([np.argmin(np.abs(det0[r])) for r in range(n_shot)])
            am = np.argmax(P21, 1)
            hit.extend((am == z).astype(float)); pm1.extend((np.abs(am - z) == 1).astype(float))
            pres.extend(P21[np.arange(n_shot), z])
            fr.p.feedback_grid_size = m1
            rf = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det1 = grids(n_shot); Pf = rf.P0_rr[:, -1, :]
            fmap = np.array([det1[r, np.argmax(Pf[r])] for r in range(n_shot)])
            near.extend((np.abs(fmap) <= HALF_WIN).astype(float))
            mres.extend(mass_near(det1, Pf, 0.0))
            ma1.extend(np.nanmean(np.vstack([mass_near(det1, Pf, a_Om), mass_near(det1, Pf, -a_Om)]), axis=0))
        n = len(hit)

        def ms(x):
            x = np.asarray(x, float); x = x[np.isfinite(x)]
            return float(x.mean()), float(x.std(ddof=1) / np.sqrt(x.size))
        out = dict(T_mean_us=T * 1e6, f_alias_kHz=1e-3 / T, order_of_quarter_Omega=0.25 * f_Om * T,
                   total_sequence_ms=total_ms, n_shots=n, noiseless_alias1_over_res=alias_ratio)
        for k, v in (("hit21", hit), ("pm1", pm1), ("P_res21", pres), ("fine_near", near), ("mass_res", mres), ("mass_a1", ma1)):
            out[k], out[k + "_sem"] = ms(v)
        results[name] = out
        print(f"{name:14s} T {out['T_mean_us']:6.1f} us  order {out['order_of_quarter_Omega']:.2f}  total {total_ms:.2f} ms | "
              f"alias1/res (noiseless) {alias_ratio:.3f} | hit21 {out['hit21']:.3f}+/-{out['hit21_sem']:.3f}  pm1 {out['pm1']:.3f} "
              f"P_res21 {out['P_res21']:.3f} | fine_near {out['fine_near']:.3f}+/-{out['fine_near_sem']:.3f}  mass_res {out['mass_res']:.4f} "
              f"mass_a1 {out['mass_a1']:.4f}", flush=True)
    fr._compute_dT_rr_mu = base_compute

    with open(os.path.join(HERE, f"schedule_sim_{rid}.json"), "w") as f:
        json.dump(results, f, indent=1)

    names = list(results); x = np.arange(len(names))
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.4))
    ax[0].bar(x, [results[k]["noiseless_alias1_over_res"] for k in names], color="#4a3aa7")
    ax[0].set_ylabel("P(alias ±1)/P(res), noiseless"); ax[0].set_ylim(0, 1.05)
    ax[1].errorbar(x - 0.1, [results[k]["hit21"] for k in names], yerr=[results[k]["hit21_sem"] for k in names], fmt="o", color="#eb6834", capsize=3, label="21-pt hit")
    ax[1].errorbar(x + 0.1, [results[k]["pm1"] for k in names], yerr=[results[k]["pm1_sem"] for k in names], fmt="s", color="#8a8a8a", capsize=3, label="MAP on ±1 bin")
    ax[1].set_ylabel("fraction of synthetic shots"); ax[1].legend(fontsize=8); ax[1].set_ylim(0, 0.7)
    ax[2].errorbar(x - 0.1, [results[k]["fine_near"] for k in names], yerr=[results[k]["fine_near_sem"] for k in names], fmt="o", color="#2a78d6", capsize=3, label="fine MAP within ±0.04 Ω")
    ax[2].errorbar(x + 0.1, [results[k]["mass_res"] * 2 for k in names], yerr=[results[k]["mass_res_sem"] * 2 for k in names], fmt="^", color="#008300", capsize=3, label="2 × mass within ±0.04 Ω")
    ax[2].set_ylabel("fine-grid localization"); ax[2].legend(fontsize=8)
    for a in ax:
        a.set_xticks(x); a.set_xticklabels([f"{k}\n{results[k]['T_mean_us']:.0f} µs" for k in names], rotation=45, ha="right", fontsize=8); a.grid(alpha=0.2)
    fig.suptitle(f"SYNTHETIC: pulse-start schedules on run {rid}'s shots (f_Rabi {f_Om/1e3:.1f} kHz, stored noise), "
                 f"{n_seeds} seeds × {n_shot} shots", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig10_schedules.png"), dpi=170, bbox_inches="tight")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)
