"""Score a one-period-grid run (feedback_narrow_test.py): does a shot localize inside one comb period?

    python narrow_check.py <run_id>

Read-only, every shot counted. The grid spans one comb period 1/T around the initial drive (15 points,
step 1/(14 T)); the resonance is a grid point. Reports per run: grid params; kernel posterior at the
end of each shot: hit (MAP on the resonant point), MAP error in kHz (median, mean |.|), posterior mass
on the resonant point and within +/-1 point, posterior std in kHz, flat-posterior fraction; the same
after pulse 1, 3, 5, 9 (convergence); gap-aware replay agreement with the kernel (max |dP|, MAP agreement).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(rid):
    from kexp import atomdata
    from alias_replay_gaps import FeedbackReplayGaps
    ad = atomdata(rid, roi_id="auto", lite=False)
    p = ad.p
    m = int(np.ravel(p.feedback_grid_size)[0]); n_p = int(np.ravel(p.N_pulses)[0])
    f_rabi = 1.0 / (2.0 * float(np.ravel(p.t_raman_pi_pulse)[0]))
    step_hz = float(np.ravel(p.feedback_grid_step_hz)[0]); T_ref = float(np.ravel(p.feedback_grid_T_ref_s)[0])
    P = np.asarray(ad.data.probabilities, float).reshape(-1, n_p + 1, m)
    n_shot = P.shape[0]
    fr = FeedbackReplayGaps(ad)
    off = fr._resolve_fractional_initial_offset_r(n_repeat=n_shot)
    grids = np.array([fr._grid_for_offset(float(o))[0] for o in off]); z = np.array([fr._grid_for_offset(float(o))[1] for o in off])
    det_hz = (grids - fr._omega_resonance_rad_s) / (2 * np.pi)
    out = dict(run_id=rid, n_shots=n_shot, N_pulses=n_p, m=m, step_kHz=step_hz / 1e3, T_ref_us=T_ref * 1e6,
               period_kHz=1e-3 / T_ref, span_kHz=step_hz * (m - 1) / 2 / 1e3, q=float(np.ravel(p.feedback_grid_q)[0]),
               offsets_kHz=sorted(set(np.round(np.asarray(ad.xvars[0], float) * f_rabi / 1e3, 2).tolist())))
    by_step = {}
    for s in (1, 3, 5, n_p):
        Ps = P[:, s, :]
        am = np.argmax(Ps, 1); err = det_hz[np.arange(n_shot), am]
        mu = np.sum(Ps * det_hz, 1); sd = np.sqrt(np.maximum(np.sum(Ps * det_hz ** 2, 1) - mu ** 2, 0))
        hit = (am == z).astype(float)
        near1 = np.array([Ps[r, max(z[r]-1, 0):z[r]+2].sum() for r in range(n_shot)])
        by_step[f"after_pulse_{s}"] = dict(hit=float(hit.mean()), hit_sem=float(np.sqrt(hit.mean() * (1 - hit.mean()) / n_shot)),
                                           map_err_kHz_median_abs=float(np.median(np.abs(err)) / 1e3), map_err_kHz_mean=float(err.mean() / 1e3),
                                           mass_res=float(Ps[np.arange(n_shot), z].mean()), mass_res_pm1=float(near1.mean()),
                                           post_std_kHz_mean=float(sd.mean() / 1e3), flat_fraction=float(np.mean(Ps.max(1) < 1.15 / m)))
    out["kernel_posterior"] = by_step
    # per-offset hit at the end
    xv = np.asarray(ad.xvars[0], float) * f_rabi / 1e3
    fin = P[:, -1, :]; am = np.argmax(fin, 1)
    out["hit_by_offset_kHz"] = {f"{k:+.2f}": float(np.mean(am[np.isclose(xv, k, atol=0.01)] == z[np.isclose(xv, k, atol=0.01)])) for k in sorted(set(np.round(xv, 2)))}
    res = fr.replay_measured(); rep = np.asarray(res.P0_rr, float)[:, -1, :]
    out["replay"] = dict(max_abs_dP=float(np.max(np.abs(rep - fin))), map_agree=float(np.mean(np.argmax(rep, 1) == am)), dT_source=getattr(fr, "dT_source", "n/a"))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]))
