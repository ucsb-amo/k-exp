"""SYNTHETIC ONLY: how should the alternation extra delay X be chosen for the rule grid?

    python alias_altspacing_sim.py <run_id> [n_seeds]

Grid: m = 15, step from the rule q_long = n + 0.4 on the LONG gap (T_fast + X), n auto (nearest to
0.25 Omega); N_pulses = 9 (the run's first 9 drawn pulse times); fast-path base gap (46.9 us at this
run's pulse times). For each X in us: q_short = q_long * T_fast / (T_fast + X) (its fractional part is
what the short-gap comb sees), the noiseless alias ratios at 1/T_fast, 1/T_long and 1/T_mean, and
the noisy closed-loop metrics (stored noise, truth on resonance, offsets = the run's initial offsets
clipped to the grid span): 15-pt hit, fine MAP within +/-0.04 Omega, mass within +/-0.04 Omega.
Design calculation on the model; nothing written back.
"""
import json
import os
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
HALF_WIN = 0.04
ALIGN = ~np.int64(7)
X_US = [float(x) for x in os.environ.get("X_LIST", "0 10 15 20 23.4 25 30 35 40").split()]
M = 15
N_PULSES = 9
FRAC = 0.4


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
    # truncate to N_PULSES pulses
    fr._apd_rr_cached = np.asarray(fr._apd_rr_cached)[:, :N_PULSES]
    fr._t_raman_pulse_rr_cached = np.asarray(fr._t_raman_pulse_rr_cached)[:, :N_PULSES]
    if fr._omega_rr_cached is not None:
        fr._omega_rr_cached = np.asarray(fr._omega_rr_cached)[:, :N_PULSES]
    fr.p.N_pulses = N_PULSES
    t_rr = np.asarray(fr._t_raman_pulse_rr_cached, float)
    n_shot, n_step = t_rr.shape
    f_Om = fr.Omega / (2 * np.pi)
    base_compute = fr._compute_dT_rr_mu
    rec = base_compute(t_rr).astype(np.int64)
    T_rec = float(rec[:, :-1].mean())
    T_f = T_rec - (float(ad.p.t_calculation_slack_compensation_mu) - 20000.0)
    fastg = rec + np.int64(round(T_f - T_rec))
    i_idx = np.arange(n_step)
    m1 = 20 * (M - 1) + 1
    offs_all = fr._resolve_fractional_initial_offset_r(n_repeat=n_shot)
    omega_res_rr_full = np.full((n_shot, n_step), fr._omega_resonance_rad_s)

    def grids(F, nsh):
        off = F._resolve_fractional_initial_offset_r(n_repeat=nsh)
        g = np.array([F._grid_for_offset(float(o))[0] for o in off])
        return (g - F._omega_resonance_rad_s) / F.Omega

    results = []
    for X in X_US:
        gaps = (fastg + np.int64(round(X * 1e3)) * (i_idx % 2)[None, :]) & ALIGN
        fr._compute_dT_rr_mu = lambda t, _g=gaps: _g.copy()
        T_long = (T_f + X * 1e3) * 1e-9; T_short = T_f * 1e-9; T_mean = float(gaps[:, :-1].mean()) * 1e-9
        n = max(0, int(round(0.25 * f_Om * T_long - FRAC)))
        q_long = n + FRAC; step_hz = q_long / T_long; step_Om = step_hz / f_Om; span = step_Om * (M - 1) / 2
        q_short = step_hz * T_short
        # offsets must lie inside the grid: clip the run's offsets to the span
        fr._fractional_initial_offset_source = np.clip(offs_all, -span, span)
        fr.p.feedback_fractional_initial_offset = float(fr._fractional_initial_offset_source[0])
        fr.p.feedback_grid_size = M; fr.p.feedback_guess_span_Omega = float(span)
        # noiseless open loop
        sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=1, noise_scale=0.0, omega_control_rr=omega_res_rr_full)
        fr.p.feedback_grid_size = m1
        res = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=omega_res_rr_full, control_omega_source='override')
        det1 = grids(fr, n_shot); Pf = res.P0_rr[:, -1, :]
        ratios = {}
        for name, T in (("fast", T_short), ("long", T_long), ("mean", T_mean)):
            a = (1.0 / T) / f_Om; rr = []
            for r in range(n_shot):
                j0 = np.argmin(np.abs(det1[r]))
                for sgn in (1, -1):
                    tgt = sgn * a
                    if det1[r].min() - 1e-9 <= tgt <= det1[r].max() + 1e-9:
                        rr.append(Pf[r, np.abs(det1[r] - tgt) <= HALF_WIN].max() / Pf[r, j0])
            ratios[name] = float(np.mean(rr)) if rr else np.nan
        # noisy closed loop
        hit, near, mres = [], [], []
        for seed in range(n_seeds):
            fr.p.feedback_grid_size = M
            sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=100 + seed, noise_scale=1.0)
            r15 = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det0 = grids(fr, n_shot); P15 = r15.P0_rr[:, -1, :]
            z = np.array([np.argmin(np.abs(det0[r])) for r in range(n_shot)])
            hit.extend((np.argmax(P15, 1) == z).astype(float))
            fr.p.feedback_grid_size = m1
            rf = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det1 = grids(fr, n_shot); Pf = rf.P0_rr[:, -1, :]
            fmap = np.array([det1[r, np.argmax(Pf[r])] for r in range(n_shot)])
            near.extend((np.abs(fmap) <= HALF_WIN).astype(float)); mres.extend(mass_near(det1, Pf, 0.0))

        def ms(x):
            x = np.asarray(x, float); x = x[np.isfinite(x)]; return float(x.mean()), float(x.std(ddof=1) / np.sqrt(x.size))
        out = dict(X_us=X, T_short_us=T_short * 1e6, T_long_us=T_long * 1e6, T_mean_us=T_mean * 1e6, n=n, q_long=q_long, q_short=q_short,
                   step_kHz=step_hz / 1e3, step_Omega=step_Om, span_Omega=span, alias=ratios, total_ms=float(gaps[:, :-1].sum(1).mean()) * 1e-6)
        for k, v in (("hit15", hit), ("fine_near", near), ("mass_res", mres)):
            out[k], out[k + "_sem"] = ms(v)
        results.append(out)
        print(f"X {X:5.1f} us: T {T_short*1e6:.1f}/{T_long*1e6:.1f} us, n {n}, q_long {q_long:.2f}, q_short {q_short:.2f} (frac {q_short%1:.2f}), "
              f"step {step_hz/1e3:.1f} kHz span ±{span:.2f} Ω | alias fast {ratios['fast']:.2f} long {ratios['long']:.2f} mean {ratios['mean']:.2f} | "
              f"hit15 {out['hit15']:.3f}±{out['hit15_sem']:.3f} fine_near {out['fine_near']:.3f}±{out['fine_near_sem']:.3f} mass {out['mass_res']:.4f} | "
              f"{out['total_ms']:.2f} ms", flush=True)
    fr._compute_dT_rr_mu = base_compute
    json.dump(results, open(os.path.join(HERE, f"altspacing_sim_{rid}" + os.environ.get("X_TAG", "") + ".json"), "w"), indent=1)
    x = [r["X_us"] for r in results]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    for k, c, lab in (("fast", "#2a78d6", "at 1/T_short"), ("long", "#eb6834", "at 1/T_long"), ("mean", "#8a8a8a", "at 1/T_mean")):
        ax[0].plot(x, [r["alias"][k] for r in results], "o-", color=c, label=lab)
    ax[0].set_ylabel("P(alias ±1)/P(res), noiseless"); ax[0].legend(fontsize=8); ax[0].set_ylim(0, 1.05)
    ax[1].errorbar(x, [r["hit15"] for r in results], yerr=[r["hit15_sem"] for r in results], fmt="o-", color="#eb6834", label="15-pt hit")
    ax[1].errorbar(x, [r["fine_near"] for r in results], yerr=[r["fine_near_sem"] for r in results], fmt="s--", color="#2a78d6", label="fine MAP within ±0.04 Ω")
    ax[1].legend(fontsize=8); ax[1].set_ylim(0, 0.6)
    ax[2].plot(x, [r["q_short"] % 1 for r in results], "o-", color="#4a3aa7", label="frac(q_short)")
    ax[2].plot(x, [r["q_long"] % 1 for r in results], "s--", color="#8a8a8a", label="frac(q_long) = 0.4")
    ax[2].axhspan(0.1, 0.4, color="#008300", alpha=0.1); ax[2].axhspan(0.6, 0.85, color="#008300", alpha=0.1)
    ax[2].set_ylabel("fractional alias order"); ax[2].legend(fontsize=8)
    for a in ax:
        a.set_xlabel("extra delay X on alternate gaps (µs)"); a.grid(alpha=0.2)
    fig.suptitle(f"SYNTHETIC: alternation spacing vs the rule grid (m {M}, N_pulses {N_PULSES}, frac {FRAC}, run {rid} calibration), {n_seeds} × {n_shot} shots", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "fig15_altspacing" + os.environ.get("X_TAG", "") + ".png"), dpi=170, bbox_inches="tight")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 4)
