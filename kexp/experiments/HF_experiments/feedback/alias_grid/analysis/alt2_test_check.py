"""Run-only test check for the alternating-gap schedule (PLAN_gap_cycles.md section 4).

    python alt2_test_check.py <run_id>

Read-only. Every shot counted. Checks:
  gaps     every recorded gap equals the base gap (slack + pretrigger + imaging + FIFO) plus the
           drawn pulse time plus that pulse's recorded extra delay, i.e. lies in the class's expected
           range (derived from the run's own params, any extra list)
  t        data.t[i] (time of the result of pulse i) equals cumsum of the recorded gaps up to pulse i
           plus the drawn pulse time and the imaging pulse, within 8 ns
  replay   gap-aware replay (FeedbackReplayGaps) vs the kernel's recorded final posterior
           (data.probabilities): max |dP| and MAP agreement; and the STOCK replay for contrast,
           which is expected to disagree on these runs
PASS needs: alternation as above on every shot, t consistent on every shot, gap-aware max |dP|
< 1e-3 and MAP agreement 1.0.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(rid):
    from kexp import atomdata
    from kexp.analysis import FeedbackReplay
    from alias_replay_gaps import FeedbackReplayGaps

    ad = atomdata(rid, roi_id="auto", lite=False)
    p = ad.p
    n_pulses = int(p.N_pulses)
    dT = np.asarray(ad.data.dT_mu, float).reshape(-1, n_pulses) * 1e-3   # us
    t = np.asarray(ad.data.t, float).reshape(-1, n_pulses)
    tp = np.asarray(ad.data.t_raman_pulse, float).reshape(-1, n_pulses)
    n_shot = dT.shape[0]
    out = dict(run_id=rid, n_shots=n_shot, n_pulses=n_pulses,
               alt_gaps=int(np.ravel(getattr(p, "alt_gaps", 0))[0]),
               fast_path=int(np.ravel(getattr(p, "fast_path", 0))[0]),
               slack_us=float(np.ravel(p.t_calculation_slack_compensation_mu)[0]) / 1e3,
               extra_list_us=(np.asarray(p.t_gap_extra_list_mu, float) / 1e3).tolist(),
               t_between_pulses_us=float(np.ravel(p.t_between_pulses_mu)[0]) / 1e3)

    even = dT[:, 0::2]; odd = dT[:, 1::2]
    out["gap_even_us"] = [float(even.min()), float(even.mean()), float(even.max())]
    out["gap_odd_us"] = [float(odd.min()), float(odd.mean()), float(odd.max())]
    # expected: base gap (slack + pretrigger + pulse + img + fifo) + the recorded extra per pulse;
    # pulse times are drawn in [min_frac, max_frac] * t_pi, so each gap class spans that range
    base_us = (float(np.ravel(p.t_calculation_slack_compensation_mu)[0]) + float(np.ravel(p.t_raman_set_pretrigger_mu)[0])
               + float(np.ravel(p.t_img_pulse)[0]) * 1e9 + float(np.ravel(p.t_fifo_mu)[0])) / 1e3
    t_pi_us = float(np.ravel(p.t_raman_pi_pulse)[0]) * 1e6
    lo_p, hi_p = float(np.ravel(p.t_raman_pulse_min_frac_pi)[0]) * t_pi_us, float(np.ravel(p.t_raman_pulse_max_frac_pi)[0]) * t_pi_us
    extra = np.asarray(p.t_gap_extra_list_mu, float) / 1e3
    exp_lo = base_us + lo_p + extra[None, :] - 0.01; exp_hi = base_us + hi_p + extra[None, :] + 0.01
    out["expected_gap_us"] = {"even": [float(exp_lo[0, 0]), float(exp_hi[0, 0])], "odd": [float(exp_lo[0, 1]), float(exp_hi[0, 1])]}
    gaps_ok = bool(np.all((dT >= exp_lo) & (dT <= exp_hi)))
    out["gaps_ok"] = gaps_ok

    t_pred = np.concatenate([np.zeros((n_shot, 1)), np.cumsum(dT[:, :-1], axis=1)], axis=1) * 1e-6 \
        + tp + float(np.ravel(p.t_img_pulse)[0])
    dt_err = np.abs(t - t_pred)
    out["t_max_abs_err_ns"] = float(dt_err.max() * 1e9)
    out["t_ok"] = bool(dt_err.max() <= 8.5e-9)

    P = np.asarray(ad.data.probabilities, float)
    m = int(np.ravel(p.feedback_grid_size)[0])
    kernel_final = P.reshape(-1, n_pulses + 1, m)[:, -1, :]
    res = {}
    for name, cls in (("gap_aware", FeedbackReplayGaps), ("stock", FeedbackReplay)):
        fr = cls(ad)
        r = fr.replay_measured()
        final = np.asarray(r.P0_rr, float)[:, -1, :]
        res[name] = dict(max_abs_dP=float(np.max(np.abs(final - kernel_final))),
                         map_agree=float(np.mean(np.argmax(final, 1) == np.argmax(kernel_final, 1))),
                         dT_source=getattr(fr, "dT_source", "n/a"),
                         dT_first_shot_us=(np.asarray(r.dT_mu_rr[0], float) / 1e3).round(3).tolist())
    out["replay"] = res
    ok = gaps_ok and out["t_ok"] and res["gap_aware"]["max_abs_dP"] < 1e-3 and res["gap_aware"]["map_agree"] == 1.0
    out["VERDICT"] = "PASS" if ok else "FAIL"
    print(json.dumps(out, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1])))
