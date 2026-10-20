"""SYNTHETIC ONLY: production-grid outcome vs the alias order of the 0.25-Omega grid point.

    python alias_order_sweep.py <run_id> [n_seeds]

Same engine as alias_schedule_sim.py. The recorded gaps of the run are shifted by a
constant so that q = 0.25 * f_Rabi * T_mean takes each value in the sweep (the
per-shot pulse-time jitter of the gaps is kept). Closed loop on the 21-pt grid with
the stored photon noise, n_seeds x 105 shots per point; metrics: hit21 (MAP on the
resonant point), pm1 / pm2 (MAP on a +/-1 / +/-2 bin), P_res21, and the fine-grid
(401-pt) MAP within +/-0.04 Omega. Also q = 1.2 and 3.2 to test that only frac(q)
matters on the grid. Design calculation on the model; nothing written back.
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
Q_LIST = [2.0, 2.1, 2.2, 2.3, 2.382, 2.5, 2.618, 2.7, 2.8, 2.9, 1.2, 3.2]


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
    step_T = 1e9 / (0.25 * f_Om)

    def grids(nsh):
        off = fr._resolve_fractional_initial_offset_r(n_repeat=nsh)
        g = np.array([fr._grid_for_offset(float(o))[0] for o in off])
        return (g - fr._omega_resonance_rad_s) / fr.Omega

    results = []
    for q in Q_LIST:
        gaps = (rec + np.int64(round(q * step_T - T_rec))) & ALIGN
        fr._compute_dT_rr_mu = lambda t, _g=gaps: _g.copy()
        T = float(gaps[:, :-1].mean()) * 1e-9
        hit, pm1, pm2, pres, near = [], [], [], [], []
        for seed in range(n_seeds):
            fr.p.feedback_grid_size = m0; fr.p.feedback_guess_span_Omega = span0
            sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=100 + seed, noise_scale=1.0)
            r21 = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det0 = grids(n_shot); P21 = r21.P0_rr[:, -1, :]
            z = np.array([np.argmin(np.abs(det0[r])) for r in range(n_shot)]); am = np.argmax(P21, 1)
            hit.extend((am == z).astype(float)); pm1.extend((np.abs(am - z) == 1).astype(float)); pm2.extend((np.abs(am - z) == 2).astype(float))
            pres.extend(P21[np.arange(n_shot), z])
            fr.p.feedback_grid_size = m1
            rf = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det1 = grids(n_shot); Pf = rf.P0_rr[:, -1, :]
            fmap = np.array([det1[r, np.argmax(Pf[r])] for r in range(n_shot)])
            near.extend((np.abs(fmap) <= HALF_WIN).astype(float))

        def ms(x):
            x = np.asarray(x, float); return float(x.mean()), float(x.std(ddof=1) / np.sqrt(x.size))
        out = dict(q=q, T_mean_us=T * 1e6, f_alias_kHz=1e-3 / T, n_shots=len(hit))
        for k, v in (("hit21", hit), ("pm1", pm1), ("pm2", pm2), ("P_res21", pres), ("fine_near", near)):
            out[k], out[k + "_sem"] = ms(v)
        results.append(out)
        print(f"q {q:.3f}  T {T*1e6:6.1f} us | hit21 {out['hit21']:.3f}+/-{out['hit21_sem']:.3f}  pm1 {out['pm1']:.3f}  pm2 {out['pm2']:.3f}  "
              f"P_res21 {out['P_res21']:.3f} | fine_near {out['fine_near']:.3f}+/-{out['fine_near_sem']:.3f}", flush=True)
    fr._compute_dT_rr_mu = base_compute

    with open(os.path.join(HERE, f"order_sweep_{rid}.json"), "w") as f:
        json.dump(results, f, indent=1)

    main_pts = [r for r in results if 2.0 <= r["q"] <= 3.0]
    extra = [r for r in results if not (2.0 <= r["q"] <= 3.0)]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    for a, keys, cols, labels in ((ax[0], ("hit21", "pm1", "pm2"), ("#eb6834", "#8a8a8a", "#4a3aa7"), ("MAP on resonant point", "MAP on ±1 bin", "MAP on ±2 bin")),
                                  (ax[1], ("fine_near", "P_res21"), ("#2a78d6", "#008300"), ("fine MAP within ±0.04 Ω", "mean posterior on resonant point"))):
        for k, c, lab in zip(keys, cols, labels):
            a.errorbar([r["q"] for r in main_pts], [r[k] for r in main_pts], yerr=[r[k + "_sem"] for r in main_pts], fmt="o-", color=c, capsize=3, label=lab)
            for r in extra:
                a.errorbar([r["q"] - np.floor(r["q"]) + 2.0], [r[k]], yerr=[r[k + "_sem"]], fmt="x", color=c, ms=9, mew=2)
        a.set_xlabel("alias order of the 0.25 Ω grid point, q = 0.25 · f_Rabi · T   (× = q 1.2 and 3.2 plotted at 2.2)")
        a.grid(alpha=0.2); a.legend(fontsize=8)
    ax[0].set_ylabel("fraction of synthetic shots"); ax[1].set_ylabel("")
    for a in ax:
        a.axvline(0.25 * f_Om * T_rec * 1e-9, color="k", lw=0.8, ls=":")
    fig.suptitle(f"SYNTHETIC: 21-pt grid outcome vs comb phase of the grid, run {rid} shots (f_Rabi {f_Om/1e3:.1f} kHz, stored noise), "
                 f"{n_seeds} × {n_shot} shots per point; dotted = recorded q", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig11_order_sweep.png"), dpi=170, bbox_inches="tight")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)
