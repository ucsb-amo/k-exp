"""Replay feedback runs on finer hypothesis grids (read-only).

    python alias_replay.py <run_id> [<run_id> ...]

For each run writes alias_<run>.npz next to this file, holding:
  * the kernel's recorded final posterior and the host replay on the run's own
    21-point grid (validation: max |dP|),
  * measured-mode replays (recorded APD voltages, recorded drive frequencies) on
    a 401-point grid over the run's own span (step 0.0125 Omega) -- every pulse
    step kept -- and on an 801-point grid over twice the span,
  * noiseless synthetic data (simulate_feedback_run_apd, noise_scale 0, truth on
    the nominal resonance) replayed on the 401 grid, for three schedules:
      closed loop with the run's own randomized pulse times,
      closed loop with a constant pulse time (the nominal p.t_raman_pulse),
      open loop, drive held on resonance, randomized pulse times,
  * per-shot detuning axes (Omega units), per-step inter-pulse gaps, timing.
Nothing is excluded; every shot of every run is replayed.
"""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def grids_for(fr, n_shot):
    off = fr._resolve_fractional_initial_offset_r(n_repeat=n_shot)
    g = np.array([fr._grid_for_offset(float(o))[0] for o in off])
    z = np.array([fr._grid_for_offset(float(o))[1] for o in off])
    return off, g, z


def replay(fr, m, span, **kw):
    fr.p.feedback_grid_size = int(m)
    fr.p.feedback_guess_span_Omega = float(span)
    t0 = time.perf_counter()
    res = fr.replay_measured(**kw) if 'apd_input_rr' not in kw else fr.simulate_counterfactual(**kw)
    dt = time.perf_counter() - t0
    n_shot = res.P0_rr.shape[0]
    off, g, z = grids_for(fr, n_shot)
    det = (g - fr._omega_resonance_rad_s) / fr.Omega
    print(f"  m={m} span={span}: {dt:.1f} s, zidx unique {np.unique(z)}", flush=True)
    return res, det, z


def main(rid):
    from kexp import atomdata
    import sys as _s; _s.path.insert(0, HERE)
    from alias_replay_gaps import FeedbackReplayGaps as FeedbackReplay  # gap-aware: reads data.dT_mu when present, stock otherwise

    ad = atomdata(rid, roi_id='auto', lite=False)
    p = ad.p
    fr = FeedbackReplay(ad)
    m0 = int(fr.m)
    span0 = float(np.ravel(p.feedback_guess_span_Omega)[0])
    P_kernel = np.asarray(ad.data.probabilities, float).reshape(-1, int(p.N_pulses) + 1, m0)
    n_shot = P_kernel.shape[0]
    print(f"run {rid}: {n_shot} shots, m0 {m0}, span {span0}, t_pi {float(p.t_raman_pi_pulse):.4e}, "
          f"t_between {int(p.t_between_pulses_mu)} mu, base_valid {fr._t_between_base_valid}", flush=True)

    out = dict(run_id=rid, n_shot=n_shot, m0=m0, span0=span0,
               t_pi=float(p.t_raman_pi_pulse), Omega=float(fr.Omega),
               f_res=float(p.frequency_raman_transition),
               t_between_pulses_mu=int(p.t_between_pulses_mu),
               t_slack_mu=int(p.t_calculation_slack_compensation_mu),
               t_raman_pulse_rr=np.asarray(ad.data.t_raman_pulse, float).reshape(n_shot, -1),
               omega_rr=np.asarray(ad.data.omega_raman, float).reshape(n_shot, -1),
               apd_rr=np.asarray(ad.data.apd, float).reshape(n_shot, -1),
               offsets=np.asarray(fr._resolve_fractional_initial_offset_r(n_repeat=n_shot), float),
               P_kernel_final=P_kernel[:, -1, :], P_kernel_all=P_kernel)

    # 1) validation on the run's own grid
    res0, det0, z0 = replay(fr, m0, span0)
    out.update(P_rep0_final=res0.P0_rr[:, -1, :], det0=det0, z0=z0,
               dT_mu_rr=np.asarray(res0.dT_mu_rr, np.int64),
               max_dP_kernel_vs_replay=float(np.max(np.abs(res0.P0_rr[:, -1, :] - P_kernel[:, -1, :]))),
               map_agree=float(np.mean(np.argmax(res0.P0_rr[:, -1, :], 1) == np.argmax(P_kernel[:, -1, :], 1))))
    print(f"  validation: max|dP| {out['max_dP_kernel_vs_replay']:.2e}, MAP agree {out['map_agree']:.3f}", flush=True)

    # 2) fine grid, same span, all steps
    m1 = 20 * (m0 - 1) + 1          # 401: the 21 production points are a subset
    res1, det1, z1 = replay(fr, m1, span0)
    out.update(m1=m1, P_fine_all=res1.P0_rr.astype(np.float32), det1=det1, z1=z1)

    # 3) fine grid, double span
    m2 = 2 * (m1 - 1) + 1           # 801 at the same step
    res2, det2, z2 = replay(fr, m2, 2.0 * span0)
    out.update(m2=m2, span2=2.0 * span0, P_wide_final=res2.P0_rr[:, -1, :], det2=det2, z2=z2)

    # 4) noiseless synthetic data, truth on resonance, replayed on the fine grid
    fr.p.feedback_grid_size = m0
    fr.p.feedback_guess_span_Omega = span0
    sim_cl = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=1, noise_scale=0.0)
    r, d, z = replay(fr, m1, span0, apd_input_rr=sim_cl['apd_rr'],
                     omega_control_rr=sim_cl['omega_control_rr'], control_omega_source='override')
    out.update(P_sim_closed_final=r.P0_rr[:, -1, :], P_sim_closed_all=r.P0_rr.astype(np.float32),
               sim_closed_omega_rr=sim_cl['omega_control_rr'])

    # open loop, drive on resonance
    fr.p.feedback_grid_size = m0
    omega_res_rr = np.full(out['apd_rr'].shape, fr._omega_resonance_rad_s)
    sim_ol = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=1, noise_scale=0.0,
                                          omega_control_rr=omega_res_rr)
    r, d, z = replay(fr, m1, span0, apd_input_rr=sim_ol['apd_rr'],
                     omega_control_rr=omega_res_rr, control_omega_source='override')
    out.update(P_sim_open_final=r.P0_rr[:, -1, :], P_sim_open_all=r.P0_rr.astype(np.float32))

    # constant pulse time (nominal), open loop on resonance -- the pure fixed-period case
    saved = fr._t_raman_pulse_rr_cached
    fr._t_raman_pulse_rr_cached = np.full_like(np.asarray(saved, float), float(fr._t_raman_pulse_nominal_recorded))
    fr.p.feedback_grid_size = m0
    sim_const = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.0, seed=1, noise_scale=0.0,
                                             omega_control_rr=omega_res_rr)
    r, d, z = replay(fr, m1, span0, apd_input_rr=sim_const['apd_rr'],
                     omega_control_rr=omega_res_rr, control_omega_source='override')
    out.update(P_sim_const_final=r.P0_rr[:, -1, :], P_sim_const_all=r.P0_rr.astype(np.float32),
               dT_const_mu=np.asarray(r.dT_mu_rr, np.int64)[0])
    fr._t_raman_pulse_rr_cached = saved

    path = os.path.join(HERE, f"alias_{rid}.npz")
    np.savez_compressed(path, **out)
    print(f"  wrote {path}", flush=True)


if __name__ == '__main__':
    for a in sys.argv[1:]:
        main(int(a))
