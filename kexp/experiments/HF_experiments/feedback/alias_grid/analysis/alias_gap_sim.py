"""SYNTHETIC ONLY: how much inter-pulse gap randomization breaks the 1/T alias?

    python alias_gap_sim.py <run_id>

Takes the run's schedule (shots, offsets, drawn pulse times, calibration) and
re-synthesises data with FeedbackReplay.simulate_feedback_run_apd, truth on the
nominal resonance, while each inter-pulse gap gets an extra random delay drawn
uniformly in [0, extra_max] (per gap, per shot; rounded to 8 ns). The replay of
the synthetic data uses the same randomized gaps (both go through
_compute_dT_rr_mu, which is patched for the duration of the test). The recorded
pulse areas are untouched. Two measures per extra_max:

  noiseless, open loop, drive on resonance:   P(alias n=+/-1) / P(resonance), final step
  with the run's photon noise, closed loop on the 21-pt production grid, replayed
  on the 401-pt fine grid: fraction of shots whose fine MAP is within +/-0.04 Omega
  of resonance; mean posterior mass within +/-0.04 Omega of resonance and of n=+/-1;
  and the 21-pt production 'hit' of the same synthetic shots.

This is a design calculation on the model, not a measurement. Nothing is written
back; results go to gap_sim_<run>.json and fig9_gap_randomization.png.
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
EXTRA_US = [0.0, 5.0, 10.0, 20.0, 35.0, 70.0]


def mass_near(det, P, center, half=HALF_WIN):
    out = np.full(P.shape[0], np.nan)
    for r in range(P.shape[0]):
        sel = np.abs(det[r] - center) <= half + 1e-9
        if sel.any() and det[r].min() <= center - half + 1e-9 and det[r].max() >= center + half - 1e-9:
            out[r] = P[r, sel].sum()
    return out


def main(rid):
    from kexp import atomdata
    from kexp.analysis import FeedbackReplay

    ad = atomdata(rid, roi_id='auto', lite=False)
    fr = FeedbackReplay(ad)
    m0 = int(fr.m); span0 = float(np.ravel(ad.p.feedback_guess_span_Omega)[0])
    m1 = 20 * (m0 - 1) + 1
    n_shot, n_step = np.asarray(ad.data.apd).reshape(-1, int(ad.p.N_pulses)).shape
    f_Om = fr.Omega / (2 * np.pi)
    base_compute = fr._compute_dT_rr_mu
    rng = np.random.default_rng(12345)
    omega_res_rr = np.full((n_shot, n_step), fr._omega_resonance_rad_s)

    def grids(nsh):
        off = fr._resolve_fractional_initial_offset_r(n_repeat=nsh)
        g = np.array([fr._grid_for_offset(float(o))[0] for o in off])
        return (g - fr._omega_resonance_rad_s) / fr.Omega

    results = []
    for extra_us in EXTRA_US:
        extra = np.int64(np.round(rng.uniform(0.0, extra_us * 1e3, size=(n_shot, n_step)))) & ~np.int64(7)

        def patched(t_rr, _extra=extra):
            return base_compute(t_rr) + _extra
        fr._compute_dT_rr_mu = patched
        T = float(np.mean((base_compute(np.asarray(ad.data.t_raman_pulse, float).reshape(n_shot, -1)) + extra)[:, :-1]) * 1e-9)

        # (a) noiseless, open loop on resonance
        fr.p.feedback_grid_size = m0; fr.p.feedback_guess_span_Omega = span0
        sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=1, noise_scale=0.0, omega_control_rr=omega_res_rr)
        fr.p.feedback_grid_size = m1
        res = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=omega_res_rr, control_omega_source='override')
        det1 = grids(n_shot); Pf = res.P0_rr[:, -1, :]
        a_Om = (1.0 / T) / f_Om
        ratios = []
        for r in range(n_shot):
            j0 = np.argmin(np.abs(det1[r]))
            for sgn in (1, -1):
                target = sgn * a_Om
                if det1[r].min() - 1e-9 <= target <= det1[r].max() + 1e-9:
                    sel = np.abs(det1[r] - target) <= HALF_WIN
                    ratios.append(Pf[r, sel].max() / Pf[r, j0])
        ratio_noiseless = float(np.mean(ratios))

        # (b) with photon noise, closed loop on the production grid, replayed on the fine grid
        fr.p.feedback_grid_size = m0
        sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=7, noise_scale=1.0)
        res21 = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
        det0 = grids(n_shot)
        hit21 = float(np.mean([np.argmax(res21.P0_rr[r, -1]) == np.argmin(np.abs(det0[r])) for r in range(n_shot)]))
        fr.p.feedback_grid_size = m1
        res = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
        det1 = grids(n_shot); Pf = res.P0_rr[:, -1, :]
        fmap = np.array([det1[r, np.argmax(Pf[r])] for r in range(n_shot)])
        near = float(np.mean(np.abs(fmap) <= HALF_WIN))
        m_res = mass_near(det1, Pf, 0.0)
        m_a1 = np.nanmean(np.vstack([mass_near(det1, Pf, a_Om), mass_near(det1, Pf, -a_Om)]), axis=0)
        out = dict(extra_max_us=extra_us, T_mean_us=T * 1e6, f_alias_kHz=1e-3 / T, alias_step_Omega=a_Om,
                   noiseless_alias1_over_res=ratio_noiseless,
                   noisy_fine_map_near_res=near, noisy_fine_map_near_res_sem=float(np.sqrt(near * (1 - near) / n_shot)),
                   noisy_mass_res=float(np.nanmean(m_res)), noisy_mass_res_sem=float(np.nanstd(m_res, ddof=1) / np.sqrt(n_shot)),
                   noisy_mass_alias1=float(np.nanmean(m_a1)), noisy_hit_21pt=hit21,
                   noisy_hit_21pt_sem=float(np.sqrt(hit21 * (1 - hit21) / n_shot)))
        results.append(out)
        print(json.dumps(out), flush=True)
    fr._compute_dT_rr_mu = base_compute

    with open(os.path.join(HERE, f"gap_sim_{rid}.json"), "w") as f:
        json.dump(results, f, indent=1)

    x = [r["extra_max_us"] for r in results]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    ax[0].plot(x, [r["noiseless_alias1_over_res"] for r in results], "o-", color="#4a3aa7")
    ax[0].set_ylabel("P(alias ±1) / P(resonance), noiseless"); ax[0].set_ylim(0, 1.05)
    ax[1].errorbar(x, [r["noisy_fine_map_near_res"] for r in results], yerr=[r["noisy_fine_map_near_res_sem"] for r in results],
                   fmt="o-", color="#2a78d6", capsize=3, label="fine-grid MAP within ±0.04 Ω of resonance")
    ax[1].errorbar(x, [r["noisy_hit_21pt"] for r in results], yerr=[r["noisy_hit_21pt_sem"] for r in results],
                   fmt="s--", color="#eb6834", capsize=3, label="21-pt production grid hit")
    ax[1].set_ylabel("fraction of synthetic shots"); ax[1].legend(fontsize=8); ax[1].set_ylim(0, 1)
    ax[2].errorbar(x, [r["noisy_mass_res"] for r in results], yerr=[r["noisy_mass_res_sem"] for r in results], fmt="o-",
                   color="#008300", capsize=3, label="mass within ±0.04 Ω of resonance")
    ax[2].plot(x, [r["noisy_mass_alias1"] for r in results], "s--", color="#8a8a8a", label="mass within ±0.04 Ω of alias ±1 (at the new mean T)")
    ax[2].set_ylabel("mean fine-grid posterior mass"); ax[2].legend(fontsize=8)
    for a in ax:
        a.set_xlabel("max extra random delay per gap (µs)"); a.grid(alpha=0.2)
    fig.suptitle(f"SYNTHETIC design check on run {rid}'s schedule (f_Rabi {f_Om/1e3:.1f} kHz, base period "
                 f"{results[0]['T_mean_us']:.1f} µs): random extra inter-pulse delay vs alias strength", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig9_gap_randomization.png"), dpi=170, bbox_inches="tight")


if __name__ == "__main__":
    main(int(sys.argv[1]))
