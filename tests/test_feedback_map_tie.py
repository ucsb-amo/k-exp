"""A tie for the posterior maximum gives the mean of the tied points (user, 2026-10-30).

Host-side, no run file and no hardware. First-maximum settles a tie by grid order or by
rounding; that rule is kept only for run files without p.feedback_map_tie_mean, which ran
that way.
"""
import copy

import numpy as np
import pytest

from kexp.base.feedback import Feedback, map_estimate, MAP_TIE_REL_TOL
from kexp.experiments.HF_experiments.feedback.alias_grid.base_expt_feedback_fast import OverlapPosterior
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams


PAIR = 3


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


def host(tie_mean=1):
    p = ExptParams()
    p.feedback_grid_size = 21
    p.frequency_feedback_grid_full_span = 8844.4
    p.N_pulses = 11
    p.compute_feedback_grid()
    if tie_mean is None:
        del p.feedback_map_tie_mean      # as a run file from before the rule
    else:
        p.feedback_map_tie_mean = tie_mean
    return Host(p)


def set_p0(h, idx_values):
    h.P0[:] = 1.e-6
    for i, v in idx_values.items():
        h.P0[i] = v


def frequency_of(h):
    max_idx = int(np.argmax(h.P0))
    return h.map_frequency(max_idx, h.P0[max_idx])


def test_two_points_tied_give_their_mean():
    h = host()
    set_p0(h, {6: .4, 14: .4})
    assert frequency_of(h) == pytest.approx(.5 * (h.omega_guess_list[6] + h.omega_guess_list[14]), abs=1e-6)


def test_three_points_tied_give_their_mean():
    h = host()
    set_p0(h, {2: .3, 3: .3, 17: .3})
    expected = (h.omega_guess_list[2] + h.omega_guess_list[3] + h.omega_guess_list[17]) / 3
    assert frequency_of(h) == pytest.approx(expected, abs=1e-6)


def test_near_tie_from_rounding_is_a_tie():
    h = host()
    set_p0(h, {6: .4, 14: .4 * (1 + 3e-14)})
    assert frequency_of(h) == pytest.approx(.5 * (h.omega_guess_list[6] + h.omega_guess_list[14]), abs=1e-6)


def test_clear_maximum_is_the_grid_point_exactly():
    h = host()
    set_p0(h, {6: .4, 14: .4 * (1 - 100 * MAP_TIE_REL_TOL)})
    assert frequency_of(h) == h.omega_guess_list[6]


@pytest.mark.parametrize("tie_mean", [0, None])
def test_off_and_old_run_files_keep_the_first_maximum(tie_mean):
    h = host(tie_mean)
    assert h.map_tie_mean == 0
    set_p0(h, {6: .4, 14: .4})
    assert frequency_of(h) == h.omega_guess_list[6]


def run_tied_step(h, posterior):
    """One read at the drive, spin at the pole, no z rotation: S_z is even in the detuning, so
    each pair of points about the drive ties. A narrow likelihood centred on one pair peaks the
    posterior there, away from the "flat -> posterior mean" branch."""
    centre = h.omega_guess_list[(h.m - 1) // 2]
    h.omega_raman = centre
    h.omega_z_lightshift = 0.
    h.read_alpha_lightshift_on = 0
    h.read_twist_on = 0
    h.std_n_photons_per_shot = 0.02
    probe = copy.deepcopy(h)
    probe.propagate_hypotheses(0.)
    k = int(h.N_photons_per_shot) * probe.p1_buf[PAIR]
    return centre, posterior(k)


def full_step(h):
    return lambda k: h.generate_posterior(k, 0.)


def split_step(h):
    def go(k):
        h.propagate_hypotheses(0.)
        return h.weigh_hypotheses(k)
    return go


def assert_real_mirror_tie(h):
    assert h.P0[PAIR] == pytest.approx(h.P0[h.m - 1 - PAIR], rel=1e-9)
    assert h.P0[PAIR] > 1.15 / h.m, "peaked, or the flat branch answers instead of the tie rule"
    assert h._flat_prob_counter == 0


@pytest.mark.parametrize("step", [full_step, split_step], ids=["production", "fast_path"])
def test_mirror_tie_stays_at_the_drive_on_both_paths(step):
    h = host()
    centre, (omega_out, _, _) = run_tied_step(h, step(h))
    assert_real_mirror_tie(h)
    assert omega_out == pytest.approx(centre, abs=1e-3)
    assert h.omega_max == omega_out


def test_first_maximum_on_a_mirror_tie_leaves_the_drive_for_one_side():
    h = host(0)
    centre, (omega_out, _, _) = run_tied_step(h, full_step(h))
    assert_real_mirror_tie(h)
    # which side is down to rounding (the 2026-10-08 coin flip); not the mean either way
    assert omega_out in (h.omega_guess_list[PAIR], h.omega_guess_list[h.m - 1 - PAIR])


def test_map_estimate_is_the_same_rule():
    grid = np.array([5., 4., 3., 2., 1.])
    P = np.array([[.1, .4, .1, .4, 0.], [.1, .6, .1, .2, 0.], [.2, .2, .2, .2, .2]])
    assert map_estimate(P, grid) == pytest.approx([3., 4., 3.])
    per_row = np.tile(grid, (3, 1))
    assert map_estimate(P, per_row) == pytest.approx([3., 4., 3.])
