"""The lean posterior (fastest_loop.LeanPosterior, the bench kernel's numerics) is the library posterior
(OverlapPosterior = Feedback.generate_posterior bit for bit) to rounding.

The two differ by design only in arithmetic (LeanPosterior's docstring): the sine table inline, the rotation
products grouped differently, the Gaussian prefactor sigma / sqrt(sigma^2) = 1 dropped, the normalisation as a
multiply, the std only when asked for. So the posterior must agree to ~1e-12 and every decision must be the
same: the MAP index, the flat and degenerate branches, the drive, the remesh. A drive may part only at a
posterior tie (two points equal to rounding), which these tests count and report rather than hide.

Host-side, no hardware, no run file, no lab env vars: the feedback params on the narrow grid of the
2026-10-29/30 overnight runs, every read model, both read-noise models, the std on and off, whole trains with
reads drawn from a hypothesis, and with the remesh on. Under fast-math the compiled kernel may round
differently again; that is the on-hardware step (the replay of a real run).
"""
import copy

import numpy as np
import pytest

from kexp.base.feedback import Feedback
from kexp.experiments.HF_experiments.feedback.fastest.fastest_loop import LeanPosterior, OverlapPosterior
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams

# One step from the same state: rounding only, ~1e-16 a term.
P_ATOL = 1e-12       # posterior entries are O(1/m) .. 1
STATE_ATOL = 1e-12   # Bloch components are O(1)
# Whole trains: the drive phase each step hands the posterior is the accumulated omega_raman * t, about 2e4 rad
# by the 11th pulse; one rounding unit of it is ~4e-12 rad, and a drive that differs by one rounding unit
# (the mean drive of a flat posterior, the tie mean) moves the next step by that much. Both posteriors do
# this; the train tolerance is that precision, not a model difference.
TRAIN_ATOL = 1e-9


class Host(Feedback, OverlapPosterior, LeanPosterior):
    def __init__(self, p, need_std=0):
        self.p = p
        Feedback.__init__(self, expt_params=p)
        self.p1_buf = np.zeros(self.m)
        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift
        self.t_raman_pulse_current = float(p.t_raman_pulse)
        self.t_raman_pulse_ideal_current = float(p.t_raman_pulse) - p.t_raman_pulse_offset
        self.omega_max = 0.
        self._posterior_std = 0.
        self.hc_lean_need_std = need_std


def narrow_params(**overrides):
    p = ExptParams()
    p.feedback_grid_size = 21
    p.frequency_feedback_grid_full_span = 8844.4
    p.N_pulses = 11
    for k, v in overrides.items():
        setattr(p, k, v)
    p.compute_feedback_grid()
    return p


READ_MODELS = {
    "as_stored": {},
    "all_off": dict(read_twist_per_sz=0., back_action_coherence_slope=0., read_alpha_lightshift=float("nan"),
                    feedback_measurement_midpoint_remap_enabled=False),
    "twist_only": dict(read_twist_per_sz=0.733, back_action_coherence_slope=0., read_alpha_lightshift=float("nan")),
    "alpha_only": dict(read_twist_per_sz=0., back_action_coherence_slope=0., read_alpha_lightshift=1.432),
    "slope_only": dict(read_twist_per_sz=0., back_action_coherence_slope=0.03, read_alpha_lightshift=float("nan")),
    "all_on": dict(read_twist_per_sz=0.733, back_action_coherence_slope=0.03, read_alpha_lightshift=1.432),
}


def lib_step(h, k, t, phase, update=1, rabi=0, noise=1):
    h.propagate_hypotheses(t, phase)
    p1 = np.array(h.p1_buf)
    return h.weigh_hypotheses(k, update_raman_frequency=update, update_rabi_frequency=rabi,
                              include_photon_noise=noise), p1


def lean_step(h, k, t, phase, update=1, rabi=0, noise=1):
    h.lean_propagate(t, phase)
    p1 = np.array(h.p1_buf)
    return h.lean_weigh(k, update_raman_frequency=update, update_rabi_frequency=rabi,
                        include_photon_noise=noise), p1


def is_tie(h, tol=1e-11):
    """Two posterior points within tol of the maximum, or a point within tol of the tie-mean floor: the
    only places rounding can change a decision."""
    P = np.asarray(h.P0)
    top = P.max()
    if np.sum(np.abs(P - top) <= tol * top) > 1:
        return True
    if h.map_tie_mean:
        floor = h.map_tie_floor * top
        # a floor of 0 (or below every point's rounding) cannot be crossed by rounding
        return bool(floor > tol * top and np.any(np.abs(P - floor) <= tol * top))
    return False


def compare(a, b, ra, rb, need_std, rabi, atol=None):
    (out_a, p1_a), (out_b, p1_b) = ra, rb
    s_atol = STATE_ATOL if atol is None else atol
    p_atol = P_ATOL if atol is None else atol
    np.testing.assert_allclose(p1_b, p1_a, rtol=0, atol=s_atol)
    for name in ("state_x", "state_y", "state_z"):
        np.testing.assert_allclose(getattr(b, name), getattr(a, name), rtol=0, atol=s_atol, err_msg=name)
    np.testing.assert_allclose(b.P0, a.P0, rtol=0, atol=p_atol)
    assert b._flat_prob_counter == a._flat_prob_counter
    assert b._degenerate_posterior_counter == a._degenerate_posterior_counter
    # the unnormalised total, in a train: the binomial read raises p to k ~ 300, which turns the train's ~1e-12
    # in p into ~1e-9 here (both posteriors alike); it only decides the all-zero branch
    assert abs(b.P0_total - a.P0_total) <= (1e-12 if atol is None else 1e-7) * abs(a.P0_total) + 1e-300
    tie = is_tie(a)
    if not tie:
        assert b.max_idx == a.max_idx
        assert b.omega_max == pytest.approx(a.omega_max, rel=1e-12, abs=1e-6)
        assert out_b[0] == pytest.approx(out_a[0], rel=1e-12, abs=1e-6)       # drive, rad/s
    assert out_b[1] == pytest.approx(out_a[1], rel=1e-12, abs=1e-6)           # posterior mean
    # the std is sqrt(<w^2> - <w>^2) of absolute frequencies, w ~ 7.5e8 rad/s (the library's formula, kept):
    # the variance carries a rounding error of a few eps * w^2, ~1e2 (rad/s)^2, whatever the width, so the
    # library's own std of a narrow posterior is good to ~1 rad/s (0.2 Hz). Compare the variances at that scale.
    var_tol = 4e-15 * float(np.max(np.square(a.omega_guess_list)))
    if need_std or rabi:
        assert abs(b._posterior_std ** 2 - a._posterior_std ** 2) <= var_tol
    else:
        assert b._posterior_std == -1.0            # not computed, never stale
    if rabi:
        assert abs(out_b[2] ** 2 - out_a[2] ** 2) <= var_tol                   # the std returned
    else:
        assert out_b[2] == out_a[2]                                            # Omega, untouched
    return tie


@pytest.mark.parametrize("model", READ_MODELS)
@pytest.mark.parametrize("noise", (1, 0))
@pytest.mark.parametrize("need_std, rabi", ((0, 0), (1, 0), (0, 1)))
def test_random_states(model, noise, need_std, rabi):
    base = Host(narrow_params(**READ_MODELS[model]), need_std=need_std)
    rng = np.random.default_rng(20261105)
    ties = 0
    for _ in range(300):
        a = copy.deepcopy(base)
        v = rng.normal(size=(3, a.m))
        v /= np.linalg.norm(v, axis=0)
        a.state_x[:], a.state_y[:], a.state_z[:] = v
        P = rng.random(a.m)
        a.P0[:] = P / P.sum()
        a.omega_raman = float(rng.choice(a.omega_guess_list) + rng.normal() * a.Omega * 0.3)
        a.t_raman_pulse_current = float(rng.uniform(0.5, 1.0) * a.p.t_raman_pi_pulse)
        a.t_raman_pulse_ideal_current = a.t_raman_pulse_current - a.p.t_raman_pulse_offset
        b = copy.deepcopy(a)
        t, phase = float(rng.uniform(0, 2e-3)), float(rng.uniform(-np.pi, np.pi))
        k = float(np.rint(rng.uniform(-0.2, 1.2) * a.N_photons_per_shot))
        ties += compare(a, b, lib_step(a, k, t, phase, rabi=rabi, noise=noise),
                        lean_step(b, k, t, phase, rabi=rabi, noise=noise), need_std, rabi)
    assert ties <= 3, ties


@pytest.mark.parametrize("model", ("as_stored", "all_off", "all_on"))
@pytest.mark.parametrize("update", (1, 0))
@pytest.mark.parametrize("noise", (1, 0))
def test_whole_trains(model, update, noise):
    """Eleven steps, each from the previous step's state and own chosen drive, reads drawn from a true
    hypothesis: the drives must not part except at a posterior tie."""
    base = Host(narrow_params(**READ_MODELS[model]))
    rng = np.random.default_rng(92603)
    dT = 26.6e-6
    parted = []
    for shot in range(40):
        a, b = copy.deepcopy(base), copy.deepcopy(base)
        truth = int(rng.integers(a.m))
        phase_a = phase_b = 0.
        for i in range(11):
            t = i * dT
            # the read: drawn from the truth hypothesis' predicted fraction (library model, state before)
            probe = copy.deepcopy(a)
            probe.propagate_hypotheses(t, phase_a)
            mean = probe.N_photons_per_shot * float(probe.p1_buf[truth])
            k = float(np.rint(rng.normal(mean, probe.std_n_photons_per_shot)))
            ra = lib_step(a, k, t, phase_a, update=update, noise=noise)
            rb = lean_step(b, k, t, phase_b, update=update, noise=noise)
            tie = compare(a, b, ra, rb, need_std=0, rabi=0, atol=TRAIN_ATOL)
            a.omega_raman, a.Omega = ra[0][0], ra[0][2]
            b.omega_raman, b.Omega = rb[0][0], rb[0][2]
            if abs(a.omega_raman - b.omega_raman) > 1e-6:
                assert tie, (shot, i)
                parted.append((shot, i))
                break
            phase_a += a.omega_raman * dT
            phase_b += b.omega_raman * dT
    print(f"{model} update {update} noise {noise}: drives parted in {len(parted)} of 40 trains {parted}")
    assert len(parted) <= 1, parted


def test_remesh_decisions_are_the_same():
    """Remesh on (the std is then computed): the same remesh at the same step, the same new grid."""
    p = narrow_params(feedback_remesh_threshold_Omega=0.6, n_initial_shots_before_remesh=2)
    base = Host(p, need_std=1)
    assert base.feedback_remesh_threshold_omega > 0.
    rng = np.random.default_rng(5)
    dT = 26.6e-6
    n_remesh = 0
    for shot in range(30):
        a, b = copy.deepcopy(base), copy.deepcopy(base)
        truth = int(rng.integers(a.m))
        phase_a = phase_b = 0.
        for i in range(11):
            t = i * dT
            probe = copy.deepcopy(a)
            probe.propagate_hypotheses(t, phase_a)
            k = float(np.rint(rng.normal(probe.N_photons_per_shot * float(probe.p1_buf[truth]),
                                         probe.std_n_photons_per_shot)))
            ra = lib_step(a, k, t, phase_a)
            rb = lean_step(b, k, t, phase_b)
            compare(a, b, ra, rb, need_std=1, rabi=0, atol=TRAIN_ATOL)
            a.omega_raman, a.Omega = ra[0][0], ra[0][2]
            b.omega_raman, b.Omega = rb[0][0], rb[0][2]
            if i > p.n_initial_shots_before_remesh - 1:
                g0 = np.array(a.omega_guess_list)
                a.maybe_remesh(a._posterior_std, omega_center=ra[0][1])
                b.maybe_remesh(b._posterior_std, omega_center=rb[0][1])
                np.testing.assert_allclose(b.omega_guess_list, a.omega_guess_list, rtol=1e-12, atol=1e-6)
                np.testing.assert_allclose(b.P0, a.P0, rtol=0, atol=TRAIN_ATOL)
                n_remesh += int(not np.array_equal(g0, np.asarray(a.omega_guess_list)))
            phase_a += a.omega_raman * dT
            phase_b += b.omega_raman * dT
    assert n_remesh > 0     # the remesh path was really exercised


def test_the_flat_posterior_branch():
    a = Host(narrow_params())
    b = copy.deepcopy(a)
    a.std_n_photons_per_shot = b.std_n_photons_per_shot = 1.e9
    compare(a, b, lib_step(a, 300., 1e-4, 0.3), lean_step(b, 300., 1e-4, 0.3), 0, 0)
    assert a._flat_prob_counter == b._flat_prob_counter == 1


def test_the_all_zero_posterior_branch():
    a = Host(narrow_params())
    b = copy.deepcopy(a)
    a.std_n_photons_per_shot = b.std_n_photons_per_shot = 1.e-3
    ra, rb = lib_step(a, 1.e9, 1e-4, 0.3), lean_step(b, 1.e9, 1e-4, 0.3)
    assert a._degenerate_posterior_counter == b._degenerate_posterior_counter == 1
    assert np.all(b.P0 == 1. / b.m) and ra[0] == rb[0]


def test_the_prefactor_the_lean_weigh_drops_is_one():
    """sigma / sqrt(sigma^2) for the read-noise values every params file has used: 1 to rounding."""
    for sigma in (112.31, 120.78, 124.0, 130.23, 151.98, 367.98):
        assert abs(sigma / np.sqrt(sigma * sigma) - 1.) <= 2.3e-16


def test_a_subnormal_total_normalises_as_the_library():
    """Found 2026-11-05 writing these tests: the bench's normalisation (multiply by 1 / total) gives inf and
    NaN when the total is subnormal (1 / total overflows); the lean weigh divides then, as the library."""
    a = Host(narrow_params())
    a.P0[:] = 1e-312 / a.m          # a subnormal prior total; the likelihoods below are O(1)
    b = copy.deepcopy(a)
    ra, rb = lib_step(a, 0.5 * a.N_photons_per_shot, 1e-4, 0.3), lean_step(b, 0.5 * b.N_photons_per_shot, 1e-4, 0.3)
    assert 0. < a.P0_total < 1e-300
    assert np.all(np.isfinite(b.P0))
    np.testing.assert_allclose(b.P0, a.P0, rtol=1e-12, atol=0)
    assert b.max_idx == a.max_idx and ra[0][0] == pytest.approx(rb[0][0], rel=1e-12)
