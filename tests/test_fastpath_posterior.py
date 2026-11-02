"""OverlapPosterior's two halves are Feedback.generate_posterior, bit for bit.

The fast path splits the posterior at the measurement (propagate_hypotheses before the ADC
read, weigh_hypotheses after it). The split is a hand-kept copy of generate_posterior
(alias_grid/base_expt_feedback_fast.py), so any edit of generate_posterior can silently
leave it behind. This replaces the session script test_overlap_equivalence.py, which tested
the timing bench's own copy on a loaded run.

Host-side, no run file and no hardware: a Feedback built from the feedback params on the
narrow grid of the 2026-10-29/30 overnight runs, every read model, both noise models, and the
two branches a random draw rarely reaches (the flat posterior, the all-zero posterior).
Bitwise on the host only: the compiled kernel may round differently under fast-math; the
kernel-against-replay check on real runs is the on-hardware step.
"""
import copy

import numpy as np
import pytest

from kexp.base.feedback import Feedback
from kexp.experiments.HF_experiments.feedback.alias_grid.base_expt_feedback_fast import OverlapPosterior
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams

STATE = ("state_x", "state_y", "state_z", "P0")
SCALARS = ("P0_total", "max_idx", "omega_max", "_posterior_std", "_flat_prob_counter",
           "_degenerate_posterior_counter")


class Host(Feedback, OverlapPosterior):
    def __init__(self, p):
        self.p = p
        Feedback.__init__(self, expt_params=p)
        self.p1_buf = np.zeros(self.m)
        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift
        self.t_raman_pulse_current = float(p.t_raman_pulse)
        self.t_raman_pulse_ideal_current = float(p.t_raman_pulse) - p.t_raman_pulse_offset
        self.omega_max = 0.
        self._posterior_std = 0.


def narrow_params(**overrides):
    p = ExptParams()
    p.feedback_grid_size = 21
    p.frequency_feedback_grid_full_span = 8844.4
    p.N_pulses = 11
    for k, v in overrides.items():
        setattr(p, k, v)
    p.compute_feedback_grid()
    return p


# the stored model (twist + alpha on), every term alone, and all off
READ_MODELS = {
    "as_stored": {},
    "all_off": dict(read_twist_per_sz=0., back_action_coherence_slope=0., read_alpha_lightshift=float("nan")),
    "twist_only": dict(read_twist_per_sz=0.733, back_action_coherence_slope=0., read_alpha_lightshift=float("nan")),
    "alpha_only": dict(read_twist_per_sz=0., back_action_coherence_slope=0., read_alpha_lightshift=1.432),
    "slope_only": dict(read_twist_per_sz=0., back_action_coherence_slope=0.03, read_alpha_lightshift=float("nan")),
    "all_on": dict(read_twist_per_sz=0.733, back_action_coherence_slope=0.03, read_alpha_lightshift=1.432),
}


def assert_same(a, b, ra, rb):
    for name in STATE:
        assert np.array_equal(getattr(a, name), getattr(b, name)), name
    for name in SCALARS:
        assert getattr(a, name) == getattr(b, name), name
    assert ra == rb


def split_step(host, k, t, phase, update=1, noise=1):
    host.propagate_hypotheses(t, phase)
    return host.weigh_hypotheses(k, update_raman_frequency=update, update_rabi_frequency=0,
                                 include_photon_noise=noise)


def full_step(host, k, t, phase, update=1, noise=1):
    return host.generate_posterior(k, t, phase_raman_pulse_start=phase, update_raman_frequency=update,
                                   update_rabi_frequency=0, include_photon_noise=noise)


@pytest.mark.parametrize("model", READ_MODELS)
@pytest.mark.parametrize("noise", (1, 0))
def test_random_states(model, noise):
    base = Host(narrow_params(**READ_MODELS[model]))
    rng = np.random.default_rng(20261030)
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
        assert_same(a, b, full_step(a, k, t, phase, noise=noise), split_step(b, k, t, phase, noise=noise))


@pytest.mark.parametrize("model", READ_MODELS)
@pytest.mark.parametrize("update", (1, 0))
def test_whole_trains(model, update):
    """Eleven steps, each from the previous step's state and chosen drive, as a shot runs."""
    base = Host(narrow_params(**READ_MODELS[model]))
    rng = np.random.default_rng(89942)
    dT = 65.7e-6
    for _ in range(30):
        a, b = copy.deepcopy(base), copy.deepcopy(base)
        phase = 0.
        for i in range(11):
            k = float(np.rint(rng.uniform(0, 1) * a.N_photons_per_shot))
            t = i * dT
            phase += a.omega_raman * dT
            ra = full_step(a, k, t, phase, update=update)
            rb = split_step(b, k, t, phase, update=update)
            assert_same(a, b, ra, rb)
            a.omega_raman, a.Omega = ra[0], ra[2]
            b.omega_raman, b.Omega = rb[0], rb[2]


def test_the_flat_posterior_branch():
    a = Host(narrow_params())
    b = copy.deepcopy(a)
    # sigma so wide every hypothesis is as likely: max_prob stays under 1.15 / m
    a.std_n_photons_per_shot = b.std_n_photons_per_shot = 1.e9
    assert_same(a, b, full_step(a, 300., 1e-4, 0.3), split_step(b, 300., 1e-4, 0.3))
    assert a._flat_prob_counter == 1


def test_the_all_zero_posterior_branch():
    a = Host(narrow_params())
    b = copy.deepcopy(a)
    a.std_n_photons_per_shot = b.std_n_photons_per_shot = 1.e-3
    k = 1.e9        # every Gaussian underflows to exactly 0
    assert_same(a, b, full_step(a, k, 1e-4, 0.3), split_step(b, k, 1e-4, 0.3))
    assert a._degenerate_posterior_counter == 1
    assert np.all(a.P0 == 1. / a.m)
