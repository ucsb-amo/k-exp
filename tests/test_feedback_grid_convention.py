"""The feedback hypothesis grid, feedback_grid_convention 2 (user, 2026-10-28; kexp.base.feedback,
'hypothesis grid'): the full span in Hz, the initial offset as a fraction u of the largest allowed
(full span / 2 - half a step), and a grid shift s in steps.

* the derived Omega-unit span and offset (feedback_grid_derived, ExptParams.compute_feedback_grid);
* for every allowed u and s, odd and even m: resonance inside the grid, the unshifted grid centred
  within half a step of the initial drive, resonance at fractional index j0 + s;
* an exact tie goes to the point nearer the centre (u = +-1 -> resonance one point in from the edge);
* the kernel's _initialize_frequency_grid (run as Python, @portable) equals the host copy
  feedback_hypothesis_grid, both conventions; convention 1 is the replay's construction of before;
* check_feedback_grid_params refuses out-of-range and hand-set values;
* the replay's resonance track equals a real on-resonance grid point, on and off grid.

Host only; no hardware, no device db."""
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from kexp.base.feedback import (Feedback, check_feedback_grid_params, feedback_grid_derived,
                                feedback_hypothesis_grid, feedback_offset_frac)

T_PI = 3.9229e-06
OMEGA = np.pi / T_PI
OMEGA_RES = 2.0 * np.pi * 119.4636e6


def _params(**kw):
    from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams
    p = ExptParams()
    p.t_raman_pi_pulse = T_PI
    p.frequency_raman_transition = OMEGA_RES / (2.0 * np.pi)
    for k, v in kw.items():
        setattr(p, k, v)
    p.compute_feedback_grid()
    return p


def _grid(full_span, m, u, s):
    span, offset = feedback_grid_derived(full_span, m, T_PI, u)
    return feedback_hypothesis_grid(OMEGA_RES, OMEGA, span, m, offset, grid_shift=s, convention=2), \
        span, offset


def test_derived_values():
    F, m = 100.e3, 21
    span, offset = feedback_grid_derived(F, m, T_PI, 1.0)
    omega_hz = 1.0 / (2.0 * T_PI)
    assert np.isclose(span, (F / 2) / omega_hz)
    step_hz = F / (m - 1)
    assert np.isclose(offset * omega_hz, F / 2 - step_hz / 2)
    _, offset_neg = feedback_grid_derived(F, m, T_PI, -0.5)
    assert np.isclose(offset_neg, -0.5 * offset)
    # arrays elementwise (the scanned values at the end of a run)
    spans, offsets = feedback_grid_derived(F, m, T_PI, np.array([-1., 0., 1.]))
    assert np.isclose(spans, span) and np.allclose(offsets, [-offset, 0., offset])


@pytest.mark.parametrize("m", [3, 4, 5, 15, 16, 21, 22])
def test_resonance_stays_in_grid(m):
    F = 80.e3
    step = 2.0 * np.pi * F / (m - 1)
    for u in np.r_[np.linspace(-1., 1., 41), -1., 1., 0.999999, -0.999999]:
        for s in np.linspace(-0.5, 0.5, 11):
            (grid, j0, j_res), span, offset = _grid(F, m, u, s)
            assert np.all(np.diff(grid) < 0)                      # descending, as the kernel stores it
            assert np.allclose(np.diff(grid), -step, rtol=1e-9)
            assert 0.0 <= j_res <= m - 1, (m, u, s, j_res)        # resonance inside the grid
            assert 1 <= j0 <= m - 2 or m < 3, (m, u, j0)          # never snapped onto an edge point
            assert np.isclose(j_res, j0 + s)
            # resonance is at fractional index j_res of the (descending) grid
            assert abs(grid[0] - j_res * step - OMEGA_RES) < 1e-6 * step
            # before the shift the grid is centred within half a step of the initial drive
            centre = np.mean(grid - s * step)
            drive = OMEGA_RES + OMEGA * offset
            assert abs(centre - drive) <= 0.5 * step * (1 + 1e-6), (m, u, s)


def test_tie_goes_toward_centre():
    # u = +-1 at m = 21: 9.5 steps from the drive, exactly between two points
    (_, j0_hi, _), _, _ = _grid(50.e3, 21, 1.0, 0.0)
    (_, j0_lo, _), _, _ = _grid(50.e3, 21, -1.0, 0.0)
    assert (j0_hi, j0_lo) == (19, 1)    # drive above resonance -> resonance at the low-frequency end
    (_, j0, _), _, _ = _grid(50.e3, 21, 5. / 9.5, 0.0)
    assert j0 == 15
    # feedback_offset_frac: steps -> u; the largest allowed is (m - 2) / 2 steps
    assert np.allclose(feedback_offset_frac([-9.5, 5., 9.5], 21), [-1., 5. / 9.5, 1.])
    assert np.isclose(feedback_offset_frac(6.5, 15), 1.)


def _old_replay_grid(omega_res, Omega, span, m, offset, center_exact):
    """FeedbackReplayCore._grid_for_offset before 2026-10-28, verbatim."""
    center = float(offset) if center_exact else float(np.round(float(offset)))
    grid = omega_res + Omega * (center - span * np.linspace(-1.0, 1.0, m))
    zidx = int(np.argmin(np.abs(grid - omega_res)))
    grid = grid + (omega_res - grid[zidx])
    return grid, zidx


@pytest.mark.parametrize("center_exact", [0, 1])
def test_convention1_is_the_old_replay_grid(center_exact):
    for offset in [-2.5, -0.5, 0., 0.3, 0.5, 2., 2.5, 6.]:
        old, zold = _old_replay_grid(OMEGA_RES, OMEGA, 2.5, 21, offset, center_exact)
        new, znew, jres = feedback_hypothesis_grid(OMEGA_RES, OMEGA, 2.5, 21, offset,
                                                   convention=1, center_exact=center_exact)
        assert np.array_equal(old, new) and zold == znew == jres


@pytest.mark.parametrize("m", [15, 21])
def test_kernel_grid_equals_host_copy(m):
    p = _params(feedback_grid_size=m, frequency_feedback_grid_full_span=60.e3)
    fb = Feedback(expt_params=copy.deepcopy(p))
    for u in [-1., -0.37, 0., 0.5, 1.]:
        for s in [-0.5, -0.2, 0., 0.25, 0.5]:
            fb.p.feedback_fractional_initial_offset = u
            fb.p.feedback_grid_shift = s
            fb.p.compute_feedback_grid()
            fb._initialize_frequency_grid()
            host, j0, j_res = feedback_hypothesis_grid(
                OMEGA_RES, fb.Omega, fb.p.feedback_guess_span_Omega, m,
                fb.p.feedback_initial_offset_Omega, grid_shift=s, convention=2)
            step = 2.0 * np.pi * 60.e3 / (m - 1)
            assert np.allclose(fb.omega_guess_list, host, rtol=0, atol=1e-6 * step)
            assert fb.p.feedback_resonance_grid_index == j0
            assert np.isclose(fb.p.feedback_resonance_grid_index_frac, j_res)
            assert np.isclose(fb.omega_raman, OMEGA_RES + fb.Omega * fb.p.feedback_initial_offset_Omega)


def test_kernel_convention1_unchanged():
    """Convention 1 params (an older run's): the grid is the old replay grid, and the shift
    and derived offset are ignored."""
    p = _params(feedback_grid_convention=1, feedback_guess_span_Omega=2.5,
                feedback_fractional_initial_offset=0.3, feedback_grid_center_exact_offset=1.)
    p.feedback_grid_shift = 0.4   # not a convention-1 parameter; must have no effect
    fb = Feedback(expt_params=copy.deepcopy(p))
    old, zold = _old_replay_grid(OMEGA_RES, fb.Omega, 2.5, int(p.feedback_grid_size), 0.3, 1)
    assert np.allclose(fb.omega_guess_list, old, rtol=0, atol=1e-3)
    assert fb.p.feedback_resonance_grid_index == zold
    assert np.isclose(fb.omega_raman, OMEGA_RES + fb.Omega * 0.3)


def test_compute_feedback_grid():
    p = _params(frequency_feedback_grid_full_span=40.e3, feedback_fractional_initial_offset=-0.5)
    span, offset = feedback_grid_derived(40.e3, int(p.feedback_grid_size), T_PI, -0.5)
    assert p.feedback_guess_span_Omega == span and p.feedback_initial_offset_Omega == offset
    # end of a 2-D scan whose arrays do not broadcast: NaN, not a stale value
    p.frequency_feedback_grid_full_span = np.array([1e4, 2e4, 3e4])
    p.feedback_fractional_initial_offset = np.array([0., 1.])
    p.compute_feedback_grid()
    assert np.isnan(p.feedback_guess_span_Omega) and np.isnan(p.feedback_initial_offset_Omega)
    # convention 1: the offset is already in Omega
    q = _params(feedback_grid_convention=1, feedback_fractional_initial_offset=2.)
    assert q.feedback_initial_offset_Omega == 2.


def _xv(key, values):
    return SimpleNamespace(key=key, values=np.asarray(values, dtype=float))


def test_check_feedback_grid_params():
    check_feedback_grid_params(_params())
    check_feedback_grid_params(_params(), [_xv("feedback_fractional_initial_offset", [-1., 0., 1.]),
                                           _xv("feedback_grid_shift", [-0.5, 0.5])])
    bad = [
        ([_xv("feedback_fractional_initial_offset", [0., 1.05])], {}),
        ([_xv("feedback_grid_shift", [0.6])], {}),
        ([], dict(feedback_fractional_initial_offset=-2.)),
        ([], dict(frequency_feedback_grid_full_span=0.)),
        ([], dict(feedback_grid_size=2)),
        ([_xv("feedback_guess_span_Omega", [1., 2.])], {}),
    ]
    for xvars, kw in bad:
        p = _params()
        for k, v in kw.items():
            setattr(p, k, v)
        with pytest.raises(ValueError):
            check_feedback_grid_params(p, xvars)
    # a span set by hand in Omega is refused (it would be overwritten silently)
    p = _params()
    p.feedback_guess_span_Omega = 2.5
    with pytest.raises(ValueError, match="set by hand"):
        check_feedback_grid_params(p)
    # but t_pi set in prepare() (the derived value goes stale until finish_prepare) is fine
    p = _params()
    p.t_raman_pi_pulse = 4.1e-6
    check_feedback_grid_params(p)
    # convention 1 has no shift
    with pytest.raises(ValueError):
        check_feedback_grid_params(_params(feedback_grid_convention=1, feedback_grid_shift=0.25))


def test_p_at_resonance():
    from kexp.analysis.feedback import FeedbackReplay
    P0 = np.array([[0.1, 0.2, 0.3, 0.4], [0.1, 0.2, 0.3, 0.4], [0.1, 0.2, 0.3, 0.4]])
    got = FeedbackReplay._p_at_resonance(P0, np.array([2.0, 1.3, 1.5]))
    assert np.allclose(got, [0.3, 0.2, 0.25])


def _run_with_track(fb, steps, omega_track):
    """generate_posterior over steps, the resonance track stepped alongside (as replay does).
    Returns the track and the state of grid point feedback_resonance_grid_index, per step."""
    from kexp.analysis.feedback import FeedbackReplayCore
    fb._omega_resonance_rad_s = omega_track
    fb.reset_feedback_state()
    z = int(fb.p.feedback_resonance_grid_index)
    track = (0.0, 0.0, float(fb.initial_sz))
    out, point = [], []
    for k, t, phase, drive_detuning in steps:
        fb.omega_raman = omega_track + drive_detuning * fb.Omega
        track = FeedbackReplayCore._step_resonance_track(fb, *track, t, phase)
        fb.generate_posterior(k, t, phase_raman_pulse_start=phase, update_raman_frequency=0)
        out.append(track)
        point.append((fb.state_x[z], fb.state_y[z], fb.state_z[z]))
    return np.array(out), np.array(point)


@pytest.mark.parametrize("read_model", [False, True])
def test_resonance_track_equals_grid_point(read_model):
    """With a point on resonance (s = 0) the track equals that point's state at every step.
    Not bit for bit: the grid steps its trig by recursion from point 0, the track looks it up
    directly, and the LUT interpolates linearly -- max gap 1.6e-5 at the production 4096
    entries, 8e-8 at 65536, 3e-10 at 2**20 (2026-10-28), i.e. LUT rounding only; so the test
    runs at 2**20 and a tight tolerance. With the grid shifted (s = 0.3) no point is on
    resonance -- the snapped point is 0.3 steps off and differs -- while the track, which
    does not depend on the grid, is the same as the on-grid run's."""
    kw = dict(frequency_feedback_grid_full_span=60.e3, feedback_fractional_initial_offset=0.4)
    if read_model:
        kw.update(read_twist_per_sz=1.35, back_action_coherence_slope=0.1, read_alpha_lightshift=1.19)
    else:
        kw.update(read_twist_per_sz=0.0, back_action_coherence_slope=0.0,
                  read_alpha_lightshift=float("nan"))
    rng = np.random.default_rng(3)
    steps = [(int(rng.integers(0, 600)), float(rng.uniform(1e-6, 3e-4)),
              float(rng.uniform(-np.pi, np.pi)), float(rng.uniform(-0.05, 0.05))) for _ in range(12)]

    lut = 2 ** 20
    on = Feedback(lut_size=lut, expt_params=copy.deepcopy(_params(**kw, feedback_grid_shift=0.0)))
    track_on, point_on = _run_with_track(on, steps, OMEGA_RES)
    assert np.allclose(track_on, point_on, rtol=0, atol=1e-8)

    off = Feedback(lut_size=lut, expt_params=copy.deepcopy(_params(**kw, feedback_grid_shift=0.3)))
    track_off, point_off = _run_with_track(off, steps, OMEGA_RES)
    assert np.isclose(off.p.feedback_resonance_grid_index_frac,
                      off.p.feedback_resonance_grid_index + 0.3)
    assert np.array_equal(track_off, track_on)
    assert not np.allclose(point_off, point_on, atol=1e-3)
