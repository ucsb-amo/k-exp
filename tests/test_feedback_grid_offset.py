"""The feedback hypothesis grid for a fractional initial offset (2026-09-27).

Until 2026-09-27 the kernel placed the grid on round(offset) while the drive
started at the exact offset, so a fractional offset left the grid centre away
from the initial drive (0.5 -> 0, half-to-even). feedback_grid_center_exact_offset
= 1 (the ExptParams default since) centres it on the exact offset; 0, or a
params object without the key (every earlier run file), keeps the old
placement so replay reproduces those runs.

Checked here, on the kernel's own @portable code run on the host (Feedback
builds the grid in __init__), its numpy mirror feedback_grid_omega (OPX tables,
OPX replay) and the ARTIQ replay's FeedbackReplayCore._grid_for_offset:
  - exact mode: grid centre within half a step of the offset, one grid point
    exactly on resonance, step 2*span/(m-1) in Omega, all three agree;
  - whole-number offsets: exact and old placement give the identical grid;
  - old placement (key absent or 0): centre at round(offset), half-to-even.
No hardware, no server, no files.
"""
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from kexp.base.feedback import Feedback, feedback_grid_omega
from kexp.analysis.feedback import FeedbackReplayCore
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams


def _params(m=21, span=2.5, offset=0.0, exact=1):
    p = ExptParams()
    p.feedback_grid_size = m
    p.feedback_guess_span_Omega = span
    p.feedback_fractional_initial_offset = offset
    if exact is None:
        del p.feedback_grid_center_exact_offset       # a run file from before the key
    else:
        p.feedback_grid_center_exact_offset = exact
    return p


def _kernel_grid(p):
    fb = Feedback(expt_params=copy.copy(p))            # runs _initialize_frequency_grid
    return np.asarray(fb.omega_guess_list, dtype=float), int(fb.p.feedback_resonance_grid_index), fb


def _replay_grid(p, offset):
    stub = SimpleNamespace(p=p, m=int(p.feedback_grid_size), Omega=np.pi / p.t_raman_pi_pulse,
                           _omega_resonance_rad_s=2 * np.pi * p.frequency_raman_transition)
    return FeedbackReplayCore._grid_for_offset(stub, offset)


def _centre_in_Omega(grid, p):
    return (0.5 * (grid[0] + grid[-1]) - 2 * np.pi * p.frequency_raman_transition) / (np.pi / p.t_raman_pi_pulse)


def test_params_default_is_exact():
    assert ExptParams().feedback_grid_center_exact_offset == 1


@pytest.mark.parametrize("offset", [0.5, 1.25, -2.5, 2.5, 0.3, -1.7, 1.0, 0.0, -2.0])
@pytest.mark.parametrize("m, span", [(21, 2.5), (21, 3.0), (17, 2.0)])
def test_exact_offset_grid(m, span, offset):
    if abs(offset) > span:
        pytest.skip("resonance outside the grid: see test_offset_beyond_span_drags_grid_to_resonance")
    p = _params(m=m, span=span, offset=offset, exact=1)
    grid, zidx, fb = _kernel_grid(p)
    step = 2 * span / (m - 1)
    Omega = np.pi / p.t_raman_pi_pulse
    omega_res = 2 * np.pi * p.frequency_raman_transition
    # one hypothesis exactly on resonance, uniform step, descending
    assert grid[zidx] == omega_res
    assert np.allclose(-np.diff(grid) / Omega, step)
    # centred on the exact offset, up to the snap (at most half a step)
    assert abs(_centre_in_Omega(grid, p) - offset) <= step / 2 + 1e-9
    # the initial drive is the exact offset
    assert np.isclose((fb.omega_raman - omega_res) / Omega, offset)
    # the numpy mirror and the ARTIQ replay give the kernel's grid
    g_host, z_host = feedback_grid_omega(p)
    np.testing.assert_allclose(g_host, grid, rtol=0, atol=1e-6)
    assert z_host == zidx
    g_rep, z_rep = _replay_grid(p, offset)
    np.testing.assert_allclose(g_rep, grid, rtol=0, atol=1e-6)
    assert z_rep == zidx


@pytest.mark.parametrize("offset", [2.5, -2.5, 3.0])
def test_offset_beyond_span_drags_grid_to_resonance(offset):
    """|offset| > span puts the resonance outside the grid; the snap (unchanged
    by the 2026-09-27 fix) then moves the whole grid until its edge point is
    on resonance, so the centre ends at +/-span, not at the offset."""
    p = _params(m=17, span=2.0, offset=offset, exact=1)
    grid, zidx, _ = _kernel_grid(p)
    assert zidx in (0, 16)
    assert grid[zidx] == 2 * np.pi * p.frequency_raman_transition
    assert np.isclose(abs(_centre_in_Omega(grid, p)), 2.0)


@pytest.mark.parametrize("offset", [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0])
def test_whole_number_offsets_unchanged(offset):
    g_new, z_new, _ = _kernel_grid(_params(offset=offset, exact=1))
    g_old, z_old, _ = _kernel_grid(_params(offset=offset, exact=0))
    np.testing.assert_array_equal(g_new, g_old)
    assert z_new == z_old


@pytest.mark.parametrize("exact", [0, None])
@pytest.mark.parametrize("offset, rounded", [(0.5, 0.0), (1.5, 2.0), (2.5, 2.0), (-0.5, 0.0), (1.7, 2.0)])
def test_old_placement_is_kept_for_old_runs(exact, offset, rounded):
    p = _params(m=21, span=2.5, offset=offset, exact=exact)
    step = 2 * 2.5 / 20
    grid, zidx, _ = _kernel_grid(p)
    assert abs(_centre_in_Omega(grid, p) - rounded) <= step / 2 + 1e-9
    g_host, z_host = feedback_grid_omega(p)
    np.testing.assert_allclose(g_host, grid, rtol=0, atol=1e-6)
    assert z_host == zidx
    g_rep, z_rep = _replay_grid(p, offset)
    np.testing.assert_allclose(g_rep, grid, rtol=0, atol=1e-6)
    assert z_rep == zidx


def test_helper_explicit_argument_overrides_params():
    p = _params(offset=0.5, exact=1)
    g_old, _ = feedback_grid_omega(p, grid_center_exact_offset=0)
    g_old_ref, _ = feedback_grid_omega(_params(offset=0.5, exact=0))
    np.testing.assert_array_equal(g_old, g_old_ref)
    # p = None (the OPX builder passes every value explicitly): old placement by default
    g_none, _ = feedback_grid_omega(None, fractional_initial_offset=0.5, guess_span_Omega=2.5,
                                    frequency_raman_transition=p.frequency_raman_transition,
                                    t_raman_pi_pulse=p.t_raman_pi_pulse, feedback_grid_size=21)
    np.testing.assert_array_equal(g_none, g_old_ref)
