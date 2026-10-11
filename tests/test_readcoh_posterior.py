"""The state-dependent read model in the feedback posterior (2026-10-11, EXPLORATORY):
p.read_twist_per_sz (a z twist d = READ_TWIST_SIGN * kappa * hz at the read) and
p.back_action_coherence_slope (coherence c0 + slope * hz).

* off (the defaults) the kernel is bit for bit the one on k-exp main (loaded from git);
* the fast path's propagate + weigh and feedback_reinit's propagate equal generate_posterior
  bit for bit with the model ON;
* on, each grid point's transverse state is the constant model's, rotated by the polynomial
  twist and scaled by the state-dependent coherence (an independent reference);
* the replay reads the two params from a run's params (0 when absent) and takes overrides.

Host only (the kernels are @portable); no hardware, no device db."""
import copy
import importlib.util
import os
import subprocess

import numpy as np
import pytest

from kexp.base import feedback as fbmod
from kexp.base.feedback import Feedback

HERE = os.path.dirname(os.path.abspath(__file__))


def _params(**kw):
    from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams
    p = ExptParams()
    p.feedback_grid_size = 21
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _scramble(fb, seed=1):
    """Hypotheses spread over the Bloch sphere (so hz differs per grid point)."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=(fb.m, 3))
    v /= np.linalg.norm(v, axis=1)[:, None]
    fb.state_x[:fb.m], fb.state_y[:fb.m], fb.state_z[:fb.m] = v[:, 0], v[:, 1], v[:, 2]


def _copy_state(dst, src):
    for name in ("state_x", "state_y", "state_z", "P0"):
        getattr(dst, name)[:] = getattr(src, name)
    for name in ("omega_raman", "Omega", "t_raman_pulse_current", "t_raman_pulse_ideal_current",
                 "N_photons_per_shot", "std_n_photons_per_shot"):
        setattr(dst, name, getattr(src, name))


def _steps(n=12, seed=7, n_photons=400):
    rng = np.random.default_rng(seed)
    return [(int(rng.integers(0, n_photons)), float(rng.uniform(1e-6, 3e-4)),
             float(rng.uniform(-np.pi, np.pi)), float(rng.uniform(0.9, 1.1)))
            for _ in range(n)]


def _bits(a):
    return np.asarray(a, dtype=np.float64).view(np.int64)


def _same(a, b):
    return np.array_equal(_bits(a), _bits(b))


def _main_feedback_module(tmp_path):
    """kexp/base/feedback.py as it is on k-exp main (before the read model)."""
    src = subprocess.run(["git", "show", "main:kexp/base/feedback.py"], cwd=HERE,
                         capture_output=True, text=True, encoding="utf-8")
    if src.returncode != 0:
        pytest.skip("k-exp main's feedback.py not readable from git here")
    assert "read_twist" not in src.stdout
    path = tmp_path / "feedback_main_ref.py"
    path.write_text(src.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("feedback_main_ref", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(fb, steps, dt_nominal):
    out = []
    for k, t, phase, scale in steps:
        fb.t_raman_pulse_current = dt_nominal * scale
        fb.t_raman_pulse_ideal_current = dt_nominal * scale * 0.97
        r = fb.generate_posterior(k, t, phase_raman_pulse_start=phase,
                                  update_raman_frequency=1, include_photon_noise=1)
        out.append(r)
        fb.omega_raman = r[0]
    return out


# -- off: bit for bit k-exp main -------------------------------------------------------------

def test_off_is_bit_for_bit_the_kernel_on_main(tmp_path):
    ref_mod = _main_feedback_module(tmp_path)
    p = _params()
    new = Feedback(expt_params=copy.deepcopy(p))
    old = ref_mod.Feedback(expt_params=copy.deepcopy(p))
    assert not new.read_twist_on and not new.read_coherence_slope_on
    _scramble(new)
    _copy_state(old, new)
    steps = _steps()
    dt = new.t_raman_pulse_current
    r_new, r_old = _run(new, steps, dt), _run(old, steps, dt)
    for name in ("state_x", "state_y", "state_z", "P0"):
        assert _same(getattr(new, name), getattr(old, name)), name
    assert _same(np.array(r_new), np.array(r_old))


# -- on: the copies agree bit for bit ---------------------------------------------------------

ON = dict(read_twist_per_sz=0.869, back_action_coherence_slope=0.193, read_alpha_lightshift=1.432)


def test_the_lightshift_angle_override_at_todays_value_is_bit_for_bit_off():
    off = Feedback(expt_params=copy.deepcopy(_params()))
    a_ls = off.omega_z_lightshift * off.p.t_img_pulse
    on = Feedback(expt_params=copy.deepcopy(_params(read_alpha_lightshift=a_ls)))
    assert on.read_alpha_lightshift_on and not off.read_alpha_lightshift_on
    _scramble(off)
    _copy_state(on, off)
    dt = off.t_raman_pulse_current
    r_off, r_on = _run(off, _steps(), dt), _run(on, _steps(), dt)
    for name in ("state_x", "state_y", "state_z", "P0"):
        assert _same(getattr(off, name), getattr(on, name)), name
    assert _same(np.array(r_off), np.array(r_on))
    # and another value does change the posterior
    other = Feedback(expt_params=copy.deepcopy(_params(read_alpha_lightshift=a_ls + 0.3)))
    _scramble(other)
    _run(other, _steps(), dt)
    assert not _same(other.state_x, off.state_x)


def _overlap_class():
    from kexp.experiments.HF_experiments.feedback.alias_grid.base_expt_feedback_fast import (
        OverlapPosterior)

    class Both(OverlapPosterior, Feedback):
        pass
    return Both


@pytest.mark.parametrize("params", [ON, dict(read_twist_per_sz=-0.5), dict(back_action_coherence_slope=0.3),
                                    {}])
def test_fast_path_equals_generate_posterior(params):
    Both = _overlap_class()
    p = _params(**params)
    a = Feedback(expt_params=copy.deepcopy(p))
    b = Both(expt_params=copy.deepcopy(p))
    b.p1_buf = np.zeros(b.m)
    _scramble(a)
    _copy_state(b, a)
    dt = a.t_raman_pulse_current
    for k, t, phase, scale in _steps():
        for fb in (a, b):
            fb.t_raman_pulse_current = dt * scale
            fb.t_raman_pulse_ideal_current = dt * scale * 0.97
        ra = a.generate_posterior(k, t, phase_raman_pulse_start=phase)
        b.propagate_hypotheses(t, phase_raman_pulse_start=phase)
        rb = b.weigh_hypotheses(k)
        assert _same(np.array(ra), np.array(rb))
        a.omega_raman = b.omega_raman = ra[0]
    for name in ("state_x", "state_y", "state_z", "P0"):
        assert _same(getattr(a, name), getattr(b, name)), name


def test_feedback_reinit_propagate_equals_the_fast_path():
    from kexp.experiments.HF_experiments.feedback.feedback_reinit import feedback_reinit
    Both = _overlap_class()
    p = _params(**ON)
    a = Both(expt_params=copy.deepcopy(p))
    b = Both(expt_params=copy.deepcopy(p))
    a.p1_buf = np.zeros(a.m)
    b.p1_scratch = np.zeros(b.m)
    _scramble(a)
    _copy_state(b, a)
    for k, t, phase, scale in _steps(6):
        a.propagate_hypotheses(t, phase_raman_pulse_start=phase)
        feedback_reinit.propagate_hypotheses(b, t, phase_raman_pulse_start=phase)
        for name in ("state_x", "state_y", "state_z"):
            assert _same(getattr(a, name), getattr(b, name)), name
        assert _same(a.p1_buf, b.p1_scratch)


# -- on: what it does ---------------------------------------------------------------------------

TWIST_SLOPE = dict(read_twist_per_sz=0.869, back_action_coherence_slope=0.193)


def test_twist_and_slope_match_an_independent_reference():
    p_off, p_on = _params(), _params(**TWIST_SLOPE)
    off = Feedback(expt_params=copy.deepcopy(p_off))
    on = Feedback(expt_params=copy.deepcopy(p_on))
    _scramble(off)
    _copy_state(on, off)
    k, t, phase, _ = _steps(1)[0]
    off.generate_posterior(k, t, phase_raman_pulse_start=phase)
    on.generate_posterior(k, t, phase_raman_pulse_start=phase)
    c0 = off.back_action_coherence
    hz = off.state_z[:off.m].copy()
    assert np.array_equal(hz, on.state_z[:on.m])                    # z is never touched
    nx, ny = off.state_x[:off.m] / c0, off.state_y[:off.m] / c0      # the rotated, undamped x, y
    d = fbmod.READ_TWIST_SIGN * TWIST_SLOPE["read_twist_per_sz"] * hz
    sin_d, cos_d = d, 1.0 - d * d * 0.5                             # second order (M1-p2)
    coh = np.clip(c0 + TWIST_SLOPE["back_action_coherence_slope"] * hz, 0.0, 1.0)
    want_x = (cos_d * nx + sin_d * ny) * coh
    want_y = (-sin_d * nx + cos_d * ny) * coh
    assert np.allclose(on.state_x[:on.m], want_x, rtol=0, atol=1e-12)
    assert np.allclose(on.state_y[:on.m], want_y, rtol=0, atol=1e-12)
    # second order, not renormalised: the transverse length grows by hypot(d, 1 - d^2/2)
    # (+6.9 % at |d| = 0.87, as mr0's G4 says) and the angle is within 80 mrad of d
    grow = np.hypot(on.state_x[:on.m], on.state_y[:on.m]) / (np.hypot(nx, ny) * coh)
    assert np.allclose(grow, np.hypot(sin_d, cos_d), atol=1e-12)
    assert np.max(np.hypot(sin_d, cos_d)) < 1.07


def test_the_twist_adds_to_the_z_rotation_in_its_own_sense():
    """With every hypothesis at the same hz the twist is a constant angle; it must equal
    lowering the light-shift term's angle (alpha_z = ... - omega_ls * t_img) by that angle."""
    p_on = _params(read_twist_per_sz=0.2)
    on = Feedback(expt_params=copy.deepcopy(p_on))
    m = on.m
    on.Omega = 0.0                      # no pulse rotation: hz stays what it is
    on.state_x[:m], on.state_y[:m], on.state_z[:m] = 0.6, 0.0, 0.8
    ref = Feedback(expt_params=copy.deepcopy(_params()))
    _copy_state(ref, on)
    d = fbmod.READ_TWIST_SIGN * 0.2 * 0.8
    ref.omega_z_lightshift = on.omega_z_lightshift - d / on.p.t_img_pulse
    on.generate_posterior(10, 1e-5)
    ref.generate_posterior(10, 1e-5)
    # (the kernel's twist is a polynomial, the reference's angle goes through the LUT)
    assert np.allclose(on.state_x[:m], ref.state_x[:m], atol=2e-3)
    assert np.allclose(on.state_y[:m], ref.state_y[:m], atol=2e-3)
    assert np.max(np.abs(on.state_y[:m])) > 0.1                       # it did rotate


def test_coherence_is_clipped_to_one():
    on = Feedback(expt_params=copy.deepcopy(_params(back_action_coherence_slope=5.0)))
    m = on.m
    on.Omega = 0.0
    on.state_x[:m], on.state_y[:m], on.state_z[:m] = 0.6, 0.0, 0.8
    on.generate_posterior(10, 1e-5)
    assert np.all(np.hypot(on.state_x[:m], on.state_y[:m]) <= 0.6 + 1e-12)


def test_params_absent_read_as_off():
    p = _params()
    del p.read_twist_per_sz
    del p.back_action_coherence_slope
    fb = Feedback(expt_params=p)
    assert fb.read_twist == 0.0 and not fb.read_twist_on and not fb.read_coherence_slope_on
    assert "read_twist_on" not in Feedback.kernel_invariants        # (written per shot in an A/B)


# -- per-shot A/B of two read models (p.feedback_read_model scanned) ---------------------------

M1 = dict(read_alpha_lightshift=1.432, read_twist_per_sz=0.869, back_action_coherence=0.739)


def test_per_shot_model_1_is_bit_for_bit_the_fixed_m1_params():
    ab = Feedback(expt_params=copy.deepcopy(_params(feedback_read_model=np.array([0.0, 1.0]))))
    m1 = Feedback(expt_params=copy.deepcopy(_params(**M1)))
    m0 = Feedback(expt_params=copy.deepcopy(_params()))
    assert ab.read_model_per_shot and not m1.read_model_per_shot and not m0.read_model_per_shot
    # written per shot: never kernel invariants (ARTIQ refuses writes to them)
    assert not (set(fbmod.READ_MODEL_ATTRS) & set(Feedback.kernel_invariants))
    assert {"read_model_per_shot", "rm1_twist", "rm0_coherence"} <= set(Feedback.kernel_invariants)
    dt = ab.t_raman_pulse_current
    for model, ref in ((1.0, m1), (0.0, m0), (1.0, m1)):
        ab.select_read_model(model)
        _scramble(ref)
        _copy_state(ab, ref)
        r_ab, r_ref = _run(ab, _steps(), dt), _run(ref, _steps(), dt)
        for name in ("state_x", "state_y", "state_z", "P0"):
            assert _same(getattr(ab, name), getattr(ref, name)), (model, name)
        assert _same(np.array(r_ab), np.array(r_ref))


def test_not_scanned_select_does_nothing():
    fb = Feedback(expt_params=copy.deepcopy(_params(**M1)))
    before = {a: getattr(fb, a) for a in fbmod.READ_MODEL_ATTRS}
    fb.select_read_model(0.0)
    fb.select_read_model(1.0)
    assert {a: getattr(fb, a) for a in fbmod.READ_MODEL_ATTRS} == before
    assert fb.p.feedback_read_model == -1.0


def test_replay_resolves_the_read_model_per_shot():
    from types import SimpleNamespace
    from kexp.analysis.feedback import FeedbackReplayCore
    res = FeedbackReplayCore._resolve_read_model_r

    def fake(source, ad=None):
        f = SimpleNamespace(_read_model_source=source, ad=ad)
        f._xvar_per_shot = lambda key, n: FeedbackReplayCore._xvar_per_shot(f, key, n)
        return f
    assert np.array_equal(res(fake(-1.0), 4), [-1.0] * 4)
    assert np.array_equal(res(fake(np.array([1., 0., 0., 1.])), 4), [1., 0., 0., 1.])
    from_xvar = fake(np.array([0., 1.]),
                     SimpleNamespace(xvarnames=["feedback_read_model"],
                                     xvars=[np.array([1., 1., 0., 0., 1., 0.])]))
    assert np.array_equal(res(from_xvar, 6), [1., 1., 0., 0., 1., 0.])
    with pytest.raises(ValueError):
        res(fake(np.array([0., 1., 2.])), 4)


# -- guard: a posterior without the read model is refused when it is on ----------------------

class _OldOverlap:
    """A session copy of the fast path made before the read model: its
    propagate_hypotheses has no twist (as the 10-09 sensing chain's copy)."""

    def propagate_hypotheses(self, t, phase_raman_pulse_start=0.):
        nx, ny, coherence = 0.0, 0.0, self.back_action_coherence
        return nx * coherence, ny * coherence


def test_a_posterior_without_the_read_model_is_refused_when_it_is_on():
    class OldFast(_OldOverlap, Feedback):
        pass
    for params in (TWIST_SLOPE, dict(read_alpha_lightshift=1.432),
                   dict(feedback_read_model=np.array([0.0, 1.0]))):
        with pytest.raises(RuntimeError, match="does not implement it"):
            OldFast(expt_params=copy.deepcopy(_params(**params)))
    OldFast(expt_params=copy.deepcopy(_params()))               # off: as before, no check


def test_the_repo_posteriors_pass_the_guard():
    from kexp.experiments.HF_experiments.feedback.feedback_reinit import feedback_reinit
    Both = _overlap_class()
    Both(expt_params=copy.deepcopy(_params(**ON)))                  # fast path: no raise
    Feedback(expt_params=copy.deepcopy(_params(**ON)))
    src_ok = all(t in __import__("inspect").getsource(feedback_reinit.propagate_hypotheses)
                 for t in Feedback.READ_MODEL_TOKENS)
    assert src_ok


# -- the replay with several xvars ----------------------------------------------------------------

def _two_xvar_replay(offset_value=0.0, override=False):
    from types import SimpleNamespace
    from kexp.analysis.feedback import FeedbackReplayCore
    ad = SimpleNamespace(xvarnames=["feedback_fractional_initial_offset", "feedback_read_model"],
                         xvars=[np.array([0., 1., 2.]), np.array([0., 1.])])
    fake = SimpleNamespace(ad=ad, _read_model_source=np.array([0., 1.]),
                           _fractional_initial_offset_source=np.array([0., 1., 2.]),
                           p=SimpleNamespace(feedback_fractional_initial_offset=offset_value))
    fake._xvar_per_shot = lambda key, n: FeedbackReplayCore._xvar_per_shot(fake, key, n)
    return FeedbackReplayCore, fake


def test_two_xvar_run_gives_every_shot_its_own_offset_and_model():
    core, fake = _two_xvar_replay()
    assert np.array_equal(core._resolve_read_model_r(fake, 6), [0., 1., 0., 1., 0., 1.])
    assert np.array_equal(core._resolve_fractional_initial_offset_r(fake, 6),
                          [0., 0., 1., 1., 2., 2.])
    # the data rows come in the same order: (3, 2, step) -> 6 rows, last xvar fastest
    apd = np.arange(3 * 2 * 4, dtype=float).reshape(3, 2, 4)
    rows = core._to_repeat_step(fake, apd, "apd")
    assert rows.shape == (6, 4) and np.array_equal(rows[3], apd[1, 1])
    with pytest.raises(ValueError, match="per-shot values"):
        core._resolve_read_model_r(fake, 5)                       # counts that do not match


def test_a_deliberate_offset_override_still_wins_in_a_two_xvar_run():
    core, fake = _two_xvar_replay(offset_value=0.7)
    assert np.array_equal(core._resolve_fractional_initial_offset_r(fake, 6), [0.7] * 6)


# -- the replay's wiring ------------------------------------------------------------------------

def test_replay_reads_the_params_and_takes_overrides():
    from types import SimpleNamespace
    from kexp.base.feedback import _feedback_kwargs_from_atomdata
    from kexp.analysis.feedback import FeedbackReplayCore
    p = _params()
    kw = _feedback_kwargs_from_atomdata(SimpleNamespace(p=p))
    assert kw["read_twist_per_sz"] == 0.0 and kw["back_action_coherence_slope"] == 0.0
    del p.read_twist_per_sz                                          # an older run
    assert _feedback_kwargs_from_atomdata(SimpleNamespace(p=p))["read_twist_per_sz"] == 0.0
    assert FeedbackReplayCore._P_ATTR_TO_KWARG["read_twist_per_sz"] == "read_twist_per_sz"
    assert FeedbackReplayCore._P_ATTR_TO_KWARG["back_action_coherence_slope"] == \
        "back_action_coherence_slope"
    target = SimpleNamespace(t_raman_pulse=1e-6, t_raman_pulse_ideal=1e-6)
    FeedbackReplayCore._apply_feedback_kwargs_to_params(
        SimpleNamespace(p=target),
        {"read_twist_per_sz": 0.869, "back_action_coherence_slope": 0.193,
         "read_alpha_lightshift": 1.432})
    assert target.read_twist_per_sz == 0.869 and target.back_action_coherence_slope == 0.193
    assert target.read_alpha_lightshift == 1.432
