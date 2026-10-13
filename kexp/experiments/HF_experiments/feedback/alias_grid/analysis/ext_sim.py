"""SYNTHETIC ONLY: ways to extend the alternating-delay sequence, and whether coherence limits them.

    python ext_sim.py <run_id> [n_seeds]

Engine as alias_cycle_sim.py, on one 15-point, 9-pulse rule-grid run's shots (offsets, grid, calibration). The grid is kept as
recorded (its step was set for the 59.1 us long gap); gaps and pulse durations are replaced consistently (gap = fast base
+ drawn pulse duration + extra delay). Scenarios vary: the long gap (extra delay), the pulse-area range, a third gap value,
and back_action_coherence C (applied to both the synthetic truth and the posterior, i.e. "if the real coherence were C").
Metrics: noiseless, open loop on resonance -- largest secondary peak of the fine posterior (|delta| > 0.05 Omega) relative to
the resonance peak, and where it is; with the run's stored photon noise, closed loop -- 15-pt hit and fine MAP within
+/-0.04 Omega (n_seeds x shots). Design calculation on the model only.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HALF_WIN = 0.04

SCEN = [  # name, extra delays (us, cycle), pulse area range (x t_pi), C
    ("current: gaps 44.6/59.6, areas 0.5-1", [0., 15.], (0.5, 1.0), None),
    ("long gap 52 us", [0., 7.4], (0.5, 1.0), None),
    ("long gap 56 us", [0., 11.4], (0.5, 1.0), None),
    ("long gap 64.5 us", [0., 19.9], (0.5, 1.0), None),
    ("long gap 72 us (ratio ~ golden)", [0., 27.4], (0.5, 1.0), None),
    ("areas 0.5-2 t_pi", [0., 15.], (0.5, 2.0), None),
    ("areas 0.5-3 t_pi", [0., 15.], (0.5, 3.0), None),
    ("three gaps 0/15/35 us", [0., 15., 35.], (0.5, 1.0), None),
    ("C 0.85, current sequence", [0., 15.], (0.5, 1.0), 0.85),
    ("C 0.95, current sequence", [0., 15.], (0.5, 1.0), 0.95),
    ("C 0.95, three gaps 0/15/35", [0., 15., 35.], (0.5, 1.0), 0.95),
    ("C 0.95, areas 0.5-2", [0., 15.], (0.5, 2.0), 0.95),
]


def local_max_mask(p):
    m = np.zeros(p.size, bool)
    m[1:-1] = (p[1:-1] > p[:-2]) & (p[1:-1] >= p[2:])
    return m


def main(rid, n_seeds=4):
    from kexp import atomdata
    from kexp.analysis import FeedbackReplay
    ad = atomdata(rid, roi_id='auto', lite=False)
    fr = FeedbackReplay(ad)
    m0 = int(fr.m); span0 = float(np.ravel(ad.p.feedback_guess_span_Omega)[0]); m1 = 20 * (m0 - 1) + 1
    t_rec = np.asarray(ad.data.t_raman_pulse, float).reshape(-1, int(ad.p.N_pulses))
    n_shot, n_step = t_rec.shape
    f_Om = fr.Omega / (2 * np.pi); t_pi = float(np.ravel(ad.p.t_raman_pi_pulse)[0])
    base_mu = int(fr._t_between_base_mu)            # slack + pretrigger + img + fifo (ns)
    C0 = float(fr.back_action_coherence)
    omega_res_rr = np.full((n_shot, n_step), fr._omega_resonance_rad_s)
    i_idx = np.arange(n_step)

    def grids(nsh):
        off = fr._resolve_fractional_initial_offset_r(n_repeat=nsh)
        g = np.array([fr._grid_for_offset(float(o))[0] for o in off])
        return (g - fr._omega_resonance_rad_s) / fr.Omega

    out = []
    for name, extra, (a_lo, a_hi), C in SCEN:
        rng = np.random.default_rng(4242)
        t_pulse = np.round(rng.uniform(a_lo * t_pi, a_hi * t_pi, size=(n_shot, n_step)) * 1e9) * 1e-9 \
            if (a_lo, a_hi) != (0.5, 1.0) else t_rec.copy()
        e = np.array(extra) * 1e3
        gaps = ((base_mu + (t_pulse * 1e9).astype(np.int64) + e[i_idx % len(e)].astype(np.int64)[None, :]) & ~np.int64(7))
        fr._t_raman_pulse_rr_cached = t_pulse
        fr._compute_dT_rr_mu = lambda t, _g=gaps: _g.copy()
        fr.p.back_action_coherence = float(C if C is not None else C0)
        # noiseless open loop on resonance
        fr.p.feedback_grid_size = m0; fr.p.feedback_guess_span_Omega = span0
        sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=1, noise_scale=0.0, omega_control_rr=omega_res_rr)
        fr.p.feedback_grid_size = m1
        res = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=omega_res_rr, control_omega_source='override')
        det1 = grids(n_shot); Pf = res.P0_rr[:, -1, :]
        ratios, where = [], []
        for r in range(n_shot):
            j0 = np.argmin(np.abs(det1[r]))
            lm = local_max_mask(Pf[r]) & (np.abs(det1[r]) > 0.05)
            if lm.any():
                j = np.argmax(np.where(lm, Pf[r], -1)); ratios.append(Pf[r, j] / Pf[r, j0]); where.append(abs(det1[r, j]))
        # noisy closed loop
        hit, near = [], []
        for seed in range(n_seeds):
            fr.p.feedback_grid_size = m0
            sim = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=100 + seed, noise_scale=1.0)
            r15 = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det0 = grids(n_shot); P15 = r15.P0_rr[:, -1, :]
            z = np.array([np.argmin(np.abs(det0[r])) for r in range(n_shot)])
            hit.extend((np.argmax(P15, 1) == z).astype(float))
            fr.p.feedback_grid_size = m1
            rf = fr.simulate_counterfactual(apd_input_rr=sim['apd_rr'], omega_control_rr=sim['omega_control_rr'], control_omega_source='override')
            det1 = grids(n_shot); Pf = rf.P0_rr[:, -1, :]
            fmap = np.array([det1[r, np.argmax(Pf[r])] for r in range(n_shot)])
            near.extend((np.abs(fmap) <= HALF_WIN).astype(float))
        hit, near = np.array(hit), np.array(near)
        row = dict(name=name, mean_gap_us=float(gaps[:, :-1].mean()) / 1e3, seq_ms=float(gaps[:, :-1].sum(1).mean()) / 1e6,
                   C=float(fr.p.back_action_coherence), sec_over_res=float(np.mean(ratios)), sec_at_Omega=float(np.median(where)),
                   hit=float(hit.mean()), hit_sem=float(hit.std(ddof=1) / np.sqrt(hit.size)),
                   fine_near=float(near.mean()), fine_near_sem=float(near.std(ddof=1) / np.sqrt(near.size)))
        out.append(row)
        print(f"{name:38s} gap {row['mean_gap_us']:5.1f} us  seq {row['seq_ms']:.2f} ms  C {row['C']:.2f} | sec/res {row['sec_over_res']:.2f} at {row['sec_at_Omega']:.2f} Om | "
              f"hit {row['hit']:.3f}±{row['hit_sem']:.3f}  fine {row['fine_near']:.3f}±{row['fine_near_sem']:.3f}", flush=True)
    json.dump(out, open(os.path.join(HERE, f"ext_sim_{rid}.json"), "w"), indent=1)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 4)
