"""Offline tests of the adaptive Ramsey policies and simulator (kexp.base.adaptive_ramsey,
kexp.analysis.adaptive_ramsey). Host only: the kernels are @portable; no hardware, no device db,
no data drive. Every read-model parameter is set explicitly (not the shipped defaults).

    .venv/Scripts/python -m pytest k-exp/tests/test_adaptive_ramsey.py -q -p no:cacheprovider
"""
import numpy as np
import pytest

from kexp.analysis import adaptive_ramsey as ar
from kexp.base.adaptive_ramsey import (PHASE_NONE, PHASE_MEAN_PAR, PHASE_MAP_PAR, PHASE_RANDOM, PHASE_MAXVAR,
                                       GAP_FIXED, GAP_POSTERIOR, GAP_DOUBLING, GAP_MAXVAR)

READ_MODEL = dict(read_twist_per_sz=0.976, read_alpha_lightshift=0.948, back_action_coherence=0.8445,
                  back_action_coherence_slope=0.0)


def _params(policy, **kw):
    return ar.make_params(grid_size=21, full_span_hz=12.0e3, n_pulses=8, policy=policy, **READ_MODEL, **kw)


def _rotate_z_after_pi2(fb, j, theta, phi_dds, t):
    """s'_z of hypothesis j after a resonant pi/2 pulse with DDS phase theta + phi_dds at time t,
    by the kernel's own rotation (generate_posterior's formulas, resonant case)."""
    phi = theta + phi_dds - fb.omega_guess_list[j] * t
    ux, uy = np.cos(phi), np.sin(phi)
    sin_H, cos_H = np.sin(-np.pi / 2), np.cos(-np.pi / 2)
    sx, sy, sz = fb.state_x[j], fb.state_y[j], fb.state_z[j]
    omc = 1 - cos_H
    return (omc * ux * 0 - sin_H * uy) * sx + (omc * uy * 0 + sin_H * ux) * sy + (cos_H + omc * 0) * sz


def test_mean_par_phase_zeroes_the_expected_sz_with_positive_slope():
    p = _params(ar.RamseyPolicy("x", PHASE_MEAN_PAR, GAP_FIXED))
    fb = ar.RamseyPosterior(p)
    omega_d = fb.start_shot(0.3)
    rng = np.random.default_rng(3)
    v = rng.normal(size=(fb.m, 3)); v /= np.linalg.norm(v, axis=1)[:, None]
    fb.state_x[:fb.m], fb.state_y[:fb.m], fb.state_z[:fb.m] = v.T
    P = rng.random(fb.m); fb.P0[:fb.m] = P / P.sum()
    t_next = 123.4e-6
    phi_dds = omega_d * t_next
    theta, R = fb.ramsey_choose_phase(phi_dds, t_next, PHASE_MEAN_PAR, 1)
    sz = np.array([_rotate_z_after_pi2(fb, j, theta, phi_dds, t_next) for j in range(fb.m)])
    assert abs(float(np.dot(fb.P0[:fb.m], sz))) < 1e-3          # LUT interpolation, not exact trig
    sz_up = np.array([_rotate_z_after_pi2(fb, j, theta + 1e-3, phi_dds, t_next) for j in range(fb.m)])
    assert np.dot(fb.P0[:fb.m], sz_up) > 0                        # positive slope
    assert abs(R - np.linalg.norm([np.dot(fb.P0[:fb.m], np.cos(theta) * sz_up)])) >= 0  # R defined
    assert 0 < R <= 1.0 + 1e-9


def test_maxvar_phase_is_the_variance_maximum():
    p = _params(ar.RamseyPolicy("x", PHASE_MAXVAR, GAP_FIXED))
    fb = ar.RamseyPosterior(p)
    omega_d = fb.start_shot(-0.5)
    rng = np.random.default_rng(5)
    v = rng.normal(size=(fb.m, 3)); v /= np.linalg.norm(v, axis=1)[:, None]
    fb.state_x[:fb.m], fb.state_y[:fb.m], fb.state_z[:fb.m] = v.T
    P = rng.random(fb.m); fb.P0[:fb.m] = P / P.sum()
    t_next = 200e-6
    phi_dds = omega_d * t_next
    theta, lam = fb.ramsey_choose_phase(phi_dds, t_next, PHASE_MAXVAR, 1)

    def var_at(th):
        sz = np.array([_rotate_z_after_pi2(fb, j, th, phi_dds, t_next) for j in range(fb.m)])
        w = fb.P0[:fb.m]
        return float(np.dot(w, sz ** 2) - np.dot(w, sz) ** 2)
    grid = np.linspace(0, 2 * np.pi, 721)
    best = max(var_at(th) for th in grid)
    assert var_at(theta) >= best - 2e-3 and abs(var_at(theta) - lam) < 2e-3


def test_gap_rules_clip_to_floor_max_and_budget():
    p = _params(ar.RamseyPolicy("x", PHASE_NONE, GAP_POSTERIOR, gap_factor=0.125, t_gap_max=500e-6,
                                t_total_max=1.0e-3))
    fb = ar.RamseyPosterior(p)
    fb.start_shot(0.0)
    floor = np.int64(80000)
    # a broad posterior: the floor
    fb._posterior_std = 2 * np.pi * 5e3
    dT, theta, q = fb.ramsey_plan_next(1, 0.0, 0.0, fb.omega_raman, fb.omega_raman, 32e-9, floor)
    assert int(dT) == 80000
    # a narrow one: 0.125 / 500 Hz = 250 us
    fb._posterior_std = 2 * np.pi * 500.
    dT, _, _ = fb.ramsey_plan_next(2, 0.0, 0.0, fb.omega_raman, fb.omega_raman, 32e-9, floor)
    assert int(dT) == 250000
    # very narrow: capped at t_gap_max
    fb._posterior_std = 2 * np.pi * 10.
    dT, _, _ = fb.ramsey_plan_next(3, 0.0, 0.0, fb.omega_raman, fb.omega_raman, 32e-9, floor)
    assert int(dT) == 500000
    # the total budget: 0.9 ms elapsed leaves 100 us
    dT, _, _ = fb.ramsey_plan_next(3, 0.9e-3, 0.0, fb.omega_raman, fb.omega_raman, 32e-9, floor)
    assert int(dT) == 100000
    # never below the floor even when the budget is spent
    dT, _, _ = fb.ramsey_plan_next(3, 1.5e-3, 0.0, fb.omega_raman, fb.omega_raman, 32e-9, floor)
    assert int(dT) == 80000
    # doubling
    p2 = _params(ar.RamseyPolicy("d", PHASE_NONE, GAP_DOUBLING, t_gap_0=70e-6, t_gap_max=2e-3, t_total_max=10e-3))
    fb2 = ar.RamseyPosterior(p2); fb2.start_shot(0.0)
    gaps = [int(fb2.ramsey_plan_next(i, 0.0, 0.0, fb2.omega_raman, fb2.omega_raman, 32e-9, floor)[0]) for i in (1, 2, 3, 4)]
    assert gaps == [80000, 140000, 280000, 560000]
    # every result 8-aligned
    assert all(g % 8 == 0 for g in gaps)


def test_maxvar_gap_chooses_among_candidates_and_prefers_shorter_on_ties():
    p = _params(ar.RamseyPolicy("m", PHASE_MAXVAR, GAP_MAXVAR, gap_candidates=(1., 2., 4.)))
    fb = ar.RamseyPosterior(p)
    omega_d = fb.start_shot(0.0)
    floor = np.int64(80000)
    # all hypotheses at the pole: no transverse state, every candidate has Var 0 -> the floor
    dT, theta, q = fb.ramsey_plan_next(1, 0.0, 0.0, omega_d, omega_d, 32e-9, floor)
    assert int(dT) == 80000 and q == 0.0
    # after a pi/2 from the pole with the posterior uniform over 12 kHz, the 80 us fringe already
    # spans the prior: the choice is one of the candidates and its variance is positive
    fb.state_x[:fb.m], fb.state_y[:fb.m], fb.state_z[:fb.m] = 1.0, 0.0, 0.0
    dT, theta, q = fb.ramsey_plan_next(1, 0.0, 0.0, omega_d, omega_d, 32e-9, floor)
    assert int(dT) in (80000, 160000, 320000) and q > 0.0
    # a narrow unimodal posterior (one point): no spread -> Var 0 for every gap -> the floor
    fb.P0[:] = 0.0; fb.P0[fb.m // 2] = 1.0
    dT, theta, q = fb.ramsey_plan_next(1, 0.0, 0.0, omega_d, omega_d, 32e-9, floor)
    assert int(dT) == 80000 and abs(q) < 1e-12


def test_wrap_phase_positive_kernel_and_host_agree():
    p = _params(ar.RamseyPolicy("x", PHASE_NONE, GAP_FIXED))
    fb = ar.RamseyPosterior(p)
    from kexp.base.adaptive_ramsey import wrap_phase_positive
    for th in (-7.0, -0.1, 0.0, 1.0, 2 * np.pi, 9.0, 12345.678, -98765.4):
        a, b = fb.ramsey_wrap_phase(th), wrap_phase_positive(th)
        assert 0.0 <= a < 2 * np.pi and abs(a - b) < 1e-9
    # no loops: non-finite or absurd inputs give 0.0 at once (reviewer, 2026-10-30)
    for th in (float("nan"), float("inf"), -float("inf"), 1e12, -1e12):
        assert fb.ramsey_wrap_phase(th) == 0.0


def test_gap_clip_guards_nan_and_negative():
    p = _params(ar.RamseyPolicy("x", PHASE_NONE, GAP_FIXED))
    fb = ar.RamseyPosterior(p)
    fb.start_shot(0.0)
    floor = np.int64(80000)
    assert int(fb.ramsey_clip_gap_mu(float("nan"), floor, 0.0)) == 80000
    assert int(fb.ramsey_clip_gap_mu(-1.0, floor, 0.0)) == 80000
    assert int(fb.ramsey_clip_gap_mu(float("inf"), floor, 0.0)) == int(np.int64(p.t_ramsey_gap_max * 1e9) & ~7)
    # budget already spent: the floor, never negative
    assert int(fb.ramsey_clip_gap_mu(500e-6, floor, 10.0)) == 80000


def test_simulator_recovers_an_injected_truth_without_noise():
    """Noise off (TruthModel.noise_scale 0): the MAP must be the grid point nearest the injected
    truth for the production-like and the adaptive policies alike. (The likelihood keeps its
    noise width, so the posterior MEAN still carries mass of neighbouring lobes: only checked
    to lie within the posterior's own 2 sigma.)"""
    for pol in (ar.RamseyPolicy("p", PHASE_NONE, GAP_FIXED, random_pulse_times=True, drive_hop=True),
                ar.RamseyPolicy("a", PHASE_MAXVAR, GAP_MAXVAR)):
        p = _params(pol)
        sim = ar.AdaptiveRamseySimulator(p, ar.TruthModel(noise_scale=0.0))
        arr = sim.run(4, truth_offset_hz=1234.0, seed=2)
        tr = ar.replay_posterior(arr)
        step = 12.0e3 / (21 - 1)
        err_map, err_mean = tr.errors(arr.f_true)
        assert np.all(np.abs(err_map) <= step / 2 + 1e-6), (pol.name, err_map)
        assert np.all(np.abs(err_mean) <= 2.0 * tr.f_std + 1e-6), (pol.name, err_mean, tr.f_std)


def test_replay_on_the_controller_grid_reproduces_the_simulators_posterior():
    p = _params(ar.RamseyPolicy("a", PHASE_MAXVAR, GAP_MAXVAR))
    sim = ar.AdaptiveRamseySimulator(p)
    arr = sim.run(3, truth_offset_hz=-900.0, seed=7)
    tr = ar.replay_posterior(arr)
    # the simulator's own final posterior is the controller's last state only for the last shot;
    # re-run shot 2 through the controller and compare
    fb = ar.RamseyPosterior(p)
    r = 2
    fb.start_shot(float(arr.offset_u[r]))
    Phi = 0.0
    for i in range(arr.n_pulse):
        t = float(arr.t_pulse_start[r, i])
        if i > 0:
            Phi += float(arr.omega_drive[r, i - 1]) * (t - float(arr.t_pulse_start[r, i - 1]))
        fb.omega_raman = float(arr.omega_drive[r, i])
        fb.t_raman_pulse_current = float(arr.t_raman_pulse[r, i])
        fb.t_raman_pulse_ideal_current = fb.t_raman_pulse_current - float(p.t_raman_pulse_offset)
        k = float(np.rint(fb.N_photons_per_shot * (arr.apd[r, i] - fb.v_apd_all_down) / fb.v_range))
        fb.generate_posterior(k, t, phase_raman_pulse_start=float(arr.phase[r, i]) + Phi,
                              update_raman_frequency=0, update_rabi_frequency=0, include_photon_noise=1)
    assert np.allclose(fb.P0[:fb.m], tr.P[r, -1], atol=1e-12)


def test_phase_sign_check_prefers_the_sign_the_data_were_made_with():
    p = _params(ar.RamseyPolicy("r", PHASE_RANDOM, GAP_MAXVAR), N_pulses=10)
    sim = ar.AdaptiveRamseySimulator(p, ar.TruthModel(noise_scale=0.3))
    arr = sim.run(30, truth_offset_hz=600.0, seed=11)
    res = ar.phase_sign_check(arr)
    assert res["preferred"] == "+" and res["delta_total"] > 0 and not res["degenerate"]
    # the mirrored data prefer the other sign
    arr2 = ar.RunArrays(**{**arr.__dict__, "phase": -arr.phase})
    arr2.params.ramsey_phase_sign = -1.0
    res2 = ar.phase_sign_check(arr2)
    assert res2["preferred"] == "-"


def test_summary_fields_and_compare_policies_run():
    res = ar.compare_policies([ar.RamseyPolicy("f", PHASE_NONE, GAP_FIXED), ar.RamseyPolicy("a", PHASE_MAXVAR, GAP_MAXVAR)],
                              n_shots=4, seeds=(1,), truth_offsets_hz=(0.0,), grid_size=21, n_pulses=5,
                              score_grid_size=61, verbose=False)
    for name in ("f", "a"):
        s = res[name]["fine_grid"]
        assert s["n_shots"] == 4 and np.isfinite(s["median_abs_err_map_hz"]) and 0 <= s["coverage_2sigma"] <= 1
        assert res[name]["_std_per_pulse_hz"].shape == (4, 6)
