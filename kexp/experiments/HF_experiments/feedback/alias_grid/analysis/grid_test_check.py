"""Check a run taken with FeedbackExptGrid (grid from the pulse period).

    python grid_test_check.py <run_id>

Read-only. Reports the recorded rule params (q, n, frac, T_ref, step, span, q per gap class), rebuilds the
kernel's prepare-time grid (data.omega_raman_mesh row 0 of shot 0, the only row the kernel writes) and
checks: step(Hz) * T_ref == q (1e-6), 15 points, span == step * (m-1)/2, resonance on a grid point, and the
initial offsets (xvar) are multiples of the step. Then runs the gap check and the gap-aware replay
agreement (alt2_test_check) so one call covers the run-only test. PASS needs all of it.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(rid):
    from kexp import atomdata
    ad = atomdata(rid, roi_id="auto", lite=False)
    p = ad.p
    m = int(np.ravel(p.feedback_grid_size)[0])
    f_rabi = 1.0 / (2.0 * float(np.ravel(p.t_raman_pi_pulse)[0]))
    q = float(np.ravel(p.feedback_grid_q)[0]); T_ref = float(np.ravel(p.feedback_grid_T_ref_s)[0])
    step_hz = float(np.ravel(p.feedback_grid_step_hz)[0]); span = float(np.ravel(p.feedback_guess_span_Omega)[0])
    qc = np.asarray(p.feedback_grid_q_classes, float).ravel(); Tc = np.asarray(p.feedback_grid_T_classes_s, float).ravel()
    out = dict(run_id=rid, m=m, frac=float(np.ravel(p.feedback_grid_alias_frac)[0]), n=int(np.ravel(p.feedback_grid_alias_order)[0]),
               T_ref_us=T_ref * 1e6, q=q, step_kHz=step_hz / 1e3, step_Omega=step_hz / f_rabi, span_Omega=span,
               gap_classes_us=(Tc * 1e6).tolist(), q_classes=qc.tolist(), N_pulses=int(np.ravel(p.N_pulses)[0]),
               remesh_threshold=float(np.ravel(p.feedback_remesh_threshold_Omega)[0]))
    out["rule_ok"] = bool(abs(step_hz * T_ref - q) < 1e-6 and abs(span - step_hz / f_rabi * (m - 1) / 2) < 1e-9)
    mesh = np.asarray(ad.data.omega_raman_mesh, float)
    g0 = mesh.reshape(-1, mesh.shape[-2], mesh.shape[-1])[0, 0, :] / (2 * np.pi)   # Hz, shot 0 prepare-time grid
    steps = np.diff(g0)
    f_res = float(np.ravel(p.frequency_raman_transition)[0])
    out["kernel_grid"] = dict(n_points=int(g0.size), step_kHz=[float(abs(steps).min()) / 1e3, float(abs(steps).max()) / 1e3],
                              resonance_on_grid_Hz=float(np.min(np.abs(g0 - f_res))))
    out["kernel_grid_ok"] = bool(g0.size == m and abs(abs(steps).mean() - step_hz) < 1.0 and np.min(np.abs(g0 - f_res)) < 1.0)
    xv = np.asarray(ad.xvars[0], float) if ad.xvarnames else np.array([float(np.ravel(p.feedback_fractional_initial_offset)[0])])
    k = xv / (step_hz / f_rabi)
    out["offsets_in_steps"] = sorted(set(np.round(k, 3).tolist()))
    out["offsets_ok"] = bool(np.all(np.abs(k - np.round(k)) < 1e-6))
    from alt2_test_check import main as gap_main
    print("--- gap / replay check ---")
    rc = gap_main(rid)
    out["gap_replay_pass"] = (rc == 0)
    out["VERDICT"] = "PASS" if (out["rule_ok"] and out["kernel_grid_ok"] and out["offsets_ok"] and rc == 0) else "FAIL"
    print(json.dumps(out, indent=1))
    return 0 if out["VERDICT"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1])))
