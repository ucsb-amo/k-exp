"""Offline tests for the OPX port of the Bayesian feedback loop (design spec
section 4, pass 3b): the host helpers (grid, phase tables, per-step gaps /
schedule, co-rotating frame tables, level draw), the fixed-point numerics
(grid-index drive with axis tables, co-rotating frame, L/32 log weights,
sincos table, argmax law and the flat-rule flag) against the ARTIQ
generate_posterior oracle, the params file, the QUA trace of the sequence
(exact integer-Hz IF tables, per-step waits from the pulse-time list, the
single pulse-start timestamp, the structure variants), the finish hook
(incl. the recomputed-schedule slip check), and the replay class on a
synthetic run.

Run from the workspace root with the root venv:
    .venv/Scripts/python.exe -m pytest k-exp/tests/test_feedback_opx.py -q

Nothing here opens a socket or talks to the OPX.
"""

import copy
import os
import re
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from waxa.base.xvar import xvar
from waxx.config.data_vault import DataVault

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from opx_sim_fixture import fake_raman_expt                    # noqa: E402
from test_opx import make_map, make_transition_map             # noqa: E402

from kexp.control.opx.params_bridge import build_shot_tables   # noqa: E402
from kexp.control.opx.builder import (OPXProgramBuilder, SHOT_INDEX_KEY,  # noqa: E402
                                      RESERVED_STREAMS)
from kexp.control.opx.manager import VALID_MASK_KEY, INT_MISSING  # noqa: E402
from kexp.control.opx.sequence import Stream                   # noqa: E402
from kexp.control.opx.units import s_to_cc, demod2volts, CLOCK_NS  # noqa: E402
from kexp.control.opx.opx_config import T_DIGITAL_EDGE_NS      # noqa: E402
from kexp.base.feedback import (Feedback, feedback_grid_omega,  # noqa: E402
                                hypothesis_phase_tables, schedule_pulse_starts,
                                draw_t_raman_pulse_list, draw_t_raman_pulse_list_levels,
                                t_raman_pulse_level_set)
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import (  # noqa: E402
    ExptParams as ExptParamsFeedback)
from kexp.experiments.HF_experiments.feedback.expt_params_feedback_opx import (  # noqa: E402
    ExptParams as ExptParamsFeedbackOPX)
from kexp.experiments.opx_sequences import feedback as fbseq   # noqa: E402
from kexp.experiments.opx_sequences.feedback import (          # noqa: E402
    bayesian_feedback, bayesian_feedback_open_loop, make_feedback_sequence,
    EXP_LUT_BITS, SINCOS_LUT_BITS, LOG_WEIGHT_SCALE, exp_lut_table, exp_lut_emulation,
    sincos_lut_table, sincos_lut_emulation, axis_tables, level_matrix_tables,
    level_seed_tables, corotating_phase_tables, extend_schedule_cc, nearest_grid_index,
    if_tables_hz, applied_frequency_hz,
    feedback_constants, build_feedback_shot_tables, feedback_finish,
    feedback_step_gaps_cc, scheduled_pulse_starts_s,
    log_weights_to_probabilities, timestamps_cc_to_seconds, volts2raw,
    open_loop_drive_indices, BLOCK_EDGE_CC)
from kexp.analysis.feedback_opx import (                       # noqa: E402
    FeedbackOPXReplay, FixedPointState, FixedPointRangeError,
    posterior_update_fixed_point_emulation, run_shot_fixed_point_emulation,
    true_bloch_step, apd_volts_to_photon_fraction, ARGMAX_AGREEMENT_EXPECTED)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _params(N=20, m=21, span=3.0, offset=2.0, **kw):
    p = ExptParamsFeedbackOPX()
    p.N_pulses = N
    p.feedback_grid_size = m
    p.feedback_guess_span_Omega = span
    p.feedback_fractional_initial_offset = offset
    p.update_raman_frequency_bool = 1
    # an integer photon number: generate_posterior truncates n = int(N) but
    # keeps k = N * p_meas a float, a 1.5e-4 scale mismatch with the ARTIQ
    # 1336.2 that the OPX (sigma/N only) does not have; see
    # FeedbackOPXReplay.N_PHOTONS_REF
    p.n_photons_per_shot = 1336.0
    p.std_n_photons_per_shot = p.std_photon_fraction_opx * 1336.0
    # the continuous duration draw unless a test asks for levels: tests pin
    # the structure they exercise rather than inherit the params file's
    # default (test_params_file_* checks that default)
    p.t_raman_pulse_n_levels = 0
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _const(p, **kw):
    return feedback_constants(lambda k: getattr(p, k), **kw)


class FeedbackOPXExpt:
    """Stub with a REAL ExptParamsFeedbackOPX (what build_shot_tables needs of
    an Expt after finish_prepare) and the fake Raman pair for the split."""

    def __init__(self, xvars, **kw):
        self.params = _params(**kw)
        self.p = self.params
        self.scan_xvars = [xvar(k, np.asarray(v), position=i)
                           for i, (k, v) in enumerate(xvars)]
        self.xvardims = [len(xv.values) for xv in self.scan_xvars]
        r = fake_raman_expt()
        self.dds, self.raman = r.dds, r.raman

    def compute_new_derived(self):
        pass


def _trace(seq, xvars, cmap=None, **kw):
    ex = FeedbackOPXExpt(xvars, **kw)
    tables = build_shot_tables(ex)
    b = OPXProgramBuilder(seq, cmap or make_transition_map(ex), tables, tables.n_shots)
    prog, ctx = b.trace()
    return ex, tables, b, prog, ctx


def _qua(prog):
    from qm import generate_qua_script
    src = generate_qua_script(prog)
    return src[src.index('with program()'):src.index('config = None')]


def _stmts(src):
    return [ln.strip() for ln in src.splitlines() if ln.strip()]


def _fake_terms():
    """The drive split of the fake Raman pair (test_opx.F_TR): integer IF0s
    and slopes as ctx.transition_offset_terms returns them."""
    ex = fake_raman_expt()
    f_tr = 119.4639e6
    f150, f80 = ex.raman.ao_frequencies(f_tr)
    a150, a80 = ex.raman.ao_frequencies(f_tr + 1.e3)
    b150, b80 = ex.raman.ao_frequencies(f_tr - 1.e3)
    return {'raman_80': (int(round(float(f80))), float((a80 - b80) / 2.e3)),
            'raman_150': (int(round(float(f150))), float((a150 - b150) / 2.e3))}


def _tables_for(p, seeds, open_loop=False, terms=None, **ckw):
    n = len(seeds)
    col = lambda k: np.full(n, float(np.asarray(getattr(p, k), dtype=float).reshape(-1)[0]))
    return build_feedback_shot_tables(col, n, _const(p, **ckw), open_loop=open_loop,
                                      seeds=np.asarray(seeds), terms=terms)


def _artiq_feedback(p, lut_size=1 << 20):
    """The ARTIQ posterior with the OPX calibration mapped onto the names
    it reads. lut_size 2^20: the sin/cos LUT of generate_posterior is then
    exact to ~4e-12, so the comparison tests the algorithm, not the LUT."""
    q = copy.copy(p)
    q.v_apd_all_up = q.v_apd_all_up_opx
    q.v_apd_all_down = q.v_apd_all_down_opx
    q.std_n_photons_per_shot = q.std_photon_fraction_opx * q.n_photons_per_shot
    q.t_raman_pulse_offset = q.t_raman_pulse_offset_opx
    q.t_raman_pulse_ideal = q.t_raman_pulse - q.t_raman_pulse_offset
    q.feedback_apd_map_enabled = False
    return Feedback(lut_size=lut_size, expt_params=q)


def _synthetic_measure(p, c, omega_true, t_in, d_s, rng, noise=True):
    """A synthetic APD: the true Bloch vector stepped by the reset model;
    returns measure(i, w_d) -> p_meas plus the record of true s_z."""
    st = {'s': (0.0, 0.0, 1.0)}
    fb = _artiq_feedback(p)
    rec = []

    def measure(i, w_d):
        omega_ctrl = c.omega_res + c.Omega * float(w_d)
        hz, st['s'] = true_bloch_step(st['s'], omega_ctrl, omega_true,
                                      d_s[i] - c.t_offset_s, d_s[i], t_in[i],
                                      c.Omega, 2 * np.pi * p.frequency_lightshift,
                                      c.t_img_s, c.C)
        p1 = float(fb.expected_photon_fraction(hz))
        rec.append(hz)
        return p1 + (rng.normal(0.0, c.sigma_p) if noise else 0.0)
    return measure, rec


# ---------------------------------------------------------------------------
# host helpers (kexp/base/feedback.py additions + the sequence's tables)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('m, span, offset', [
    (21, 5.0, 0.0), (21, 3.0, 2.0), (21, 2.0, -1.7), (17, 3.0, 0.5),
    (5, 1.0, 1.0), (21, 2.0, 2.5), (2, 1.0, 0.0)])
def test_feedback_grid_omega_matches_kernel_loop(m, span, offset):
    p = _params(m=m, span=span, offset=offset)
    fb = Feedback(expt_params=copy.copy(p))       # runs _initialize_frequency_grid
    grid, zidx = feedback_grid_omega(p)
    assert grid.shape == (m,) and grid.dtype == np.float64
    np.testing.assert_array_equal(grid, fb.omega_guess_list)
    assert zidx == int(fb.p.feedback_resonance_grid_index)
    assert grid[zidx] == 2 * np.pi * p.frequency_raman_transition   # exact snap
    if m > 1:
        assert np.all(np.diff(grid) < 0)
        Omega = np.pi / p.t_raman_pi_pulse
        assert np.allclose(-np.diff(grid) / Omega, 2 * span / (m - 1))
    g2, z2 = feedback_grid_omega(p, fractional_initial_offset=offset + 1.)
    p.feedback_fractional_initial_offset = offset + 1.
    g3, z3 = feedback_grid_omega(p)
    np.testing.assert_array_equal(g2, g3) and z2 == z3
    with pytest.raises(ValueError):
        feedback_grid_omega(p, feedback_grid_size=1)


def test_hypothesis_and_corotating_phase_tables():
    p = _params(m=21, span=5.0, offset=0.0)
    grid, _ = feedback_grid_omega(p)
    f = grid / (2 * np.pi)
    t = np.linspace(0., 2.e-3, 41)                  # up to 2 ms
    phi0, dphi = hypothesis_phase_tables(f, t)
    assert phi0.shape == t.shape and dphi.shape == t.shape
    assert np.all((phi0 >= 0.) & (phi0 < 1.)) and np.all((dphi >= 0.) & (dphi < 1.))
    for j in range(f.size):
        expect = np.mod(-f[j] * t, 1.0)
        got = np.mod(phi0 + j * dphi, 1.0)
        diff = np.abs(got - expect)
        diff = np.minimum(diff, 1. - diff)
        assert np.max(diff) < 1.e-9
    np.testing.assert_allclose(phi0, np.mod(-f[0] * t, 1.), atol=1e-12)
    np.testing.assert_allclose(dphi, np.mod(-(f[1] - f[0]) * t, 1.), atol=1e-12)
    assert phi0[0] == 0. and dphi[0] == 0.
    F = np.stack([f, f + 1.e3])
    T = np.stack([t, t * 0.5])
    P0, DP = hypothesis_phase_tables(F, T)
    np.testing.assert_allclose(P0[0], phi0, atol=1e-12)
    np.testing.assert_allclose(P0[1], np.mod(-(f[0] + 1.e3) * t * 0.5, 1.), atol=1e-12)
    with pytest.raises(ValueError):
        hypothesis_phase_tables(F, t)
    # the co-rotating frame advances: gamma_{j,i} = phi_{j,i} - phi_{j,i+1} - alpha
    d0, dd = corotating_phase_tables(f, t)
    assert d0.shape == (40,) and dd.shape == (40,)
    assert np.all((d0 >= 0.) & (d0 < 1.)) and np.all((dd >= 0.) & (dd < 1.))
    for j in range(f.size):
        ph = np.mod(-f[j] * t, 1.0)
        expect = np.mod(ph[:-1] - ph[1:], 1.0)
        got = np.mod(d0 + j * dd, 1.0)
        diff = np.abs(got - expect)
        assert np.max(np.minimum(diff, 1. - diff)) < 1e-9
    D0, DD = corotating_phase_tables(F, T)
    np.testing.assert_allclose(D0[0], d0, atol=1e-12)


def test_schedule_composition():
    edge = T_DIGITAL_EDGE_NS // CLOCK_NS
    assert BLOCK_EDGE_CC == edge == 4
    d = np.array([[900, 1200, 1780], [1000, 1100, 1000]], dtype=np.int64)
    t_img, budget, over, extra = 1250, 10000, 3, 7
    # per-step gaps from the drawn list: d_i + edge + t_img + edge + budget
    # + overhead + extra gap -- ARTIQ's compute_t_between_pulses_mu per step
    gaps = feedback_step_gaps_cc(d, t_img, budget, over, extra)
    np.testing.assert_array_equal(gaps, d + edge + t_img + edge + budget + over + extra)
    # the schedule is their cumulative sum, pulse 0 at 0
    t = schedule_pulse_starts(d, t_img, budget, over + extra)
    assert t.dtype == np.int64 and t.shape == d.shape
    for s in range(2):
        assert t[s, 0] == 0
        for i in range(2):
            assert t[s, i + 1] == t[s, i] + gaps[s, i]
    t1 = schedule_pulse_starts(d[0], t_img, budget, 0)
    assert list(t1) == [0, 900 + 4 + 1250 + 4 + 10000,
                        900 + 1200 + 2 * (4 + 1250 + 4 + 10000)]
    with pytest.raises(TypeError):
        schedule_pulse_starts(d.astype(float), t_img, budget, 0)
    # the recomputation from saved seconds + params (finish hook / replay)
    p = _params(t_feedback_extra_gap=2.e-6)
    c = _const(p)
    t_s = scheduled_pulse_starts_s(p, d * 4e-9)
    np.testing.assert_allclose(
        t_s, schedule_pulse_starts(d, c.t_img_cc, c.budget_cc, c.overhead_cc + 500) * 4e-9)
    # the N+1-row schedule: a would-be pulse N one gap (with d_N = d_{N-1}) later
    ext = extend_schedule_cc(d, c)
    assert ext.shape == (2, 4)
    np.testing.assert_array_equal(ext[:, :3], np.rint(t_s / 4e-9).astype(np.int64))
    np.testing.assert_array_equal(
        ext[:, 3], ext[:, 2] + feedback_step_gaps_cc(d[:, 2], c.t_img_cc, c.budget_cc,
                                                     c.overhead_cc, c.extra_gap_cc))


def test_open_loop_indices_match_deterministic_bayesian():
    for m, N in ((21, 9), (21, 17), (5, 4), (7, 30)):
        expect = np.clip(np.rint(np.linspace(0, m - 1, N)), 0, m - 1).astype(int)
        np.testing.assert_array_equal(open_loop_drive_indices(m, N), expect)


def test_if_tables_invert_to_the_two_photon_frequency():
    terms = _fake_terms()
    f_tr = 119.4639e6
    assert abs(2 * (terms['raman_150'][0] - terms['raman_80'][0]) - f_tr) <= 2.
    assert 2 * (terms['raman_150'][1] - terms['raman_80'][1]) == pytest.approx(1., abs=1e-9)
    p = _params()
    c = _const(p)
    T = _tables_for(p, [1], terms=terms)
    w = T.w_grid[0]
    tab = if_tables_hz(w, c.f_Omega_hz, terms)
    assert tab.shape == (21, 2) and tab.dtype == np.int64
    np.testing.assert_array_equal(tab, T.if_hz[0])
    # every grid point's applied two-photon frequency is within ~3 Hz of
    # resonance + w * Omega/2pi; the resonance index gives the transition back
    f_app = 2. * (tab[:, 1] - tab[:, 0])
    assert np.max(np.abs(f_app - (f_tr + w * c.f_Omega_hz))) <= 3.
    assert abs(f_app[T.zidx[0]] - f_tr) <= 2.
    # the finish-hook lookup, with INT_MISSING -> NaN
    idx = np.array([[0, 20, 7, -1]])
    f = applied_frequency_hz(tab[None, :, :], idx)
    np.testing.assert_array_equal(f[0, :3], f_app[[0, 20, 7]])
    assert np.isnan(f[0, 3])
    # nearest-index snap: exact on-grid, first minimum on a tie
    assert nearest_grid_index(w, w[5]) == 5
    assert nearest_grid_index(w, 2.0) == 10 and w[10] == pytest.approx(2.1)
    np.testing.assert_array_equal(nearest_grid_index(T.w_grid, [2.0]), [10])


def test_level_draw_and_tables():
    p = _params()
    t_pi = p.t_raman_pi_pulse
    lev = t_raman_pulse_level_set(t_pi, 0.5, 1.0, 8)
    assert lev.shape == (8,) and np.all(np.diff(lev) > 0)
    np.testing.assert_allclose(lev, np.rint(np.linspace(0.5, 1.0, 8) * t_pi / 4e-9) * 4e-9)
    d1, i1 = draw_t_raman_pulse_list_levels(7, 20, t_pi, 0.5, 1.0, 8)
    d2, i2 = draw_t_raman_pulse_list_levels(7, 20, t_pi, 0.5, 1.0, 8)
    np.testing.assert_array_equal(d1, d2) and np.testing.assert_array_equal(i1, i2)
    assert i1.dtype == np.int64 and np.all((i1 >= 0) & (i1 < 8))
    np.testing.assert_array_equal(d1, lev[i1])
    assert not np.array_equal(draw_t_raman_pulse_list_levels(8, 20, t_pi, 0.5, 1.0, 8)[1], i1)
    with pytest.raises(ValueError, match='distinct'):
        t_raman_pulse_level_set(t_pi, 0.5, 0.5000001, 4)
    # axis tables over k = j - d and the (level, k) matrix entries
    m, dw = 21, 0.3
    ax = axis_tables(dw, m)
    k = np.arange(-20, 21)
    np.testing.assert_allclose(ax['h'], np.sqrt(1 / 16 + (k * dw / 4) ** 2))
    np.testing.assert_allclose(ax['ux'] ** 2 + ax['uz'] ** 2, 1.)
    np.testing.assert_allclose(ax['ux2'], ax['ux'] ** 2)
    np.testing.assert_allclose(ax['uxuz'], ax['ux'] * ax['uz'])
    a_l = np.array([0.2, 0.35, 0.5])
    mt = level_matrix_tables(a_l, dw, m)
    assert mt['Am'].shape == (3, 41)
    th = -4 * a_l[:, None] * ax['h'][None, :]
    c_, s_ = np.cos(2 * np.pi * th), np.sin(2 * np.pi * th)
    np.testing.assert_allclose(mt['cth'], c_)
    np.testing.assert_allclose(mt['Am'], c_ + (1 - c_) * ax['ux2'])
    np.testing.assert_allclose(mt['B'], s_ * ax['uz'])
    np.testing.assert_allclose(mt['D'], s_ * ax['ux'])
    np.testing.assert_allclose((1 + mt['cth']) - mt['Am'], c_ + (1 - c_) * ax['uz'] ** 2, atol=1e-15)
    w = 5.1 - 0.3 * np.arange(m)
    st = level_seed_tables([0.25, 0.5], w, 0.2)
    assert st['cb'].shape == (2, 21) and st['cdb'].shape == (2,)
    np.testing.assert_allclose(st['beta'][1, 4], 2.0 * (w[4] - w[0]) / 4 + 0.2)
    np.testing.assert_allclose(st['dbeta'], np.array([1., 2.]) * 0.3 / 4)


# ---------------------------------------------------------------------------
# params file
# ---------------------------------------------------------------------------

def test_params_file_inherits_and_forces_no_remesh():
    p = ExptParamsFeedbackOPX()
    base = ExptParamsFeedback()
    assert isinstance(p, ExptParamsFeedback)
    for key in ('t_raman_pi_pulse', 'frequency_raman_transition', 'N_pulses',
                'feedback_grid_size', 't_img_pulse', 'frequency_lightshift',
                'back_action_coherence', 'feedback_measurement_midpoint_fraction',
                't_raman_pulse_seed', 't_raman_pulse_min_frac_pi'):
        assert getattr(p, key) == getattr(base, key)
    assert p.v_apd_all_up_opx == base.v_apd_all_up            # placeholder copies
    assert p.v_apd_all_down_opx == base.v_apd_all_down
    assert p.std_photon_fraction_opx == pytest.approx(212.75 / 1336.2)
    assert p.t_raman_pulse_offset_opx == 127.e-9
    assert p.t_opx_feedback_compute_budget > 0.
    assert p.t_opx_feedback_align_overhead >= 0.
    assert p.t_feedback_extra_gap == 0.
    assert p.feedback_remesh_threshold_Omega == 0.
    assert p.feedback_phase_model_reset == 1
    # pass 3b flags and their defaults
    assert p.feedback_flat_rule_bool == 0
    assert p.feedback_log_weight_scale == 32 == LOG_WEIGHT_SCALE
    assert p.opx_exp_lut_bits == 8 == EXP_LUT_BITS
    assert p.opx_sincos_lut_bits == 12 == SINCOS_LUT_BITS
    assert p.t_raman_pulse_n_levels == 8
    assert not hasattr(p, 'feedback_q_clamp') and not hasattr(p, 'feedback_log_weight_floor')
    c = _const(p)
    assert c.scale == 32 and c.k_exp == 5 and not c.flat_rule
    assert c.sincos_lut_bits == 12 and c.exp_lut_bits == 8 and c.n_levels == 8
    assert c.inv_sigma_p_s == pytest.approx(c.inv_sigma_p / 8)
    # the floor: -8 - the largest decrement (3/sigma_p/8)^2 (+ a 2^-16 margin)
    assert c.L_floor == pytest.approx(-8 + (3 * c.inv_sigma_p / 8) ** 2 + 2 ** -16)
    assert -2.5 < c.L_floor < -2.4 and 32 * c.L_floor == pytest.approx(-78.5, abs=0.1)
    assert _const(p, sincos_lut_bits=0).sincos_lut_bits == 0
    assert _const(p, exp_lut_bits=0).exp_lut_bits == 0
    q = ExptParamsFeedbackOPX()
    for key in ('opx_exp_lut_bits', 'opx_sincos_lut_bits', 'feedback_log_weight_scale',
                'feedback_flat_rule_bool', 't_raman_pulse_n_levels'):
        delattr(q, key)
    cq = _const(q)                                              # older params: module defaults
    assert (cq.exp_lut_bits, cq.sincos_lut_bits, cq.scale, cq.flat_rule, cq.n_levels) == \
        (EXP_LUT_BITS, SINCOS_LUT_BITS, LOG_WEIGHT_SCALE, False, 0)
    assert c.flat_threshold == pytest.approx(21 / 1.15)
    assert c.flat_threshold4 == pytest.approx(21 / 4.6) and c.flat_threshold4 < 8
    assert c.f_Omega_hz == pytest.approx(1. / (2 * p.t_raman_pi_pulse))
    assert c.inv_sigma_p < 8 and c.n_split == 2       # 1/range_raw = 11.2 -> two factors
    assert c.t_img_cc == 1250 and c.extra_gap_cc == 0
    assert c.budget_cc == s_to_cc(p.t_opx_feedback_compute_budget)
    # the file runs the levels structure, which has its own measured overhead
    assert c.overhead_cc == round(p.t_opx_feedback_align_overhead_levels / 4e-9)
    p0 = ExptParamsFeedbackOPX()
    p0.t_raman_pulse_n_levels = 0
    assert _const(p0).overhead_cc == round(p.t_opx_feedback_align_overhead / 4e-9)
    assert c.phi_LS == pytest.approx(p.frequency_lightshift * p.t_img_pulse)
    for key, val, match in (
            ('feedback_remesh_threshold_Omega', 0.5, 'remesh'),
            ('feedback_phase_model_reset', 0, 'phase model'),
            ('feedback_log_weight_scale', 3, 'power of two'),
            ('feedback_log_weight_scale', 2, 'increase the scale'),
            ('opx_sincos_lut_bits', 3, 'sincos'),
            ('t_raman_pulse_n_levels', 2, 'levels'),
            ('std_photon_fraction_opx', 0.1, 'std_photon_fraction'),
            ('feedback_grid_size', 33, 'grid_size'),
            ('t_opx_feedback_align_overhead', 5.e-9, 'multiple'),
            ('t_feedback_extra_gap', 6.e-9, 'multiple'),
            ('t_feedback_extra_gap', -4.e-9, '>= 0'),
            ('t_opx_feedback_compute_budget', 0., '16 ns'),
            ('opx_exp_lut_bits', 11, 'exp_lut_bits')):
        q = ExptParamsFeedbackOPX()
        q.t_raman_pulse_n_levels = 0            # the continuous structure's keys
        setattr(q, key, val)
        with pytest.raises(ValueError, match=match):
            _const(q)
    q = ExptParamsFeedbackOPX()                 # the file's levels structure
    q.t_opx_feedback_align_overhead_levels = 5.e-9
    with pytest.raises(ValueError, match='multiple'):
        _const(q)
    # the midpoint remap must keep p1 monotonic on [-1, 1] (no p1 clamps)
    q = ExptParamsFeedbackOPX()
    q.feedback_measurement_midpoint_remap_enabled = 1
    q.feedback_measurement_midpoint_fraction = 0.2
    with pytest.raises(ValueError, match='midpoint'):
        _const(q)
    q.feedback_measurement_midpoint_fraction = 0.4
    assert _const(q).mid_m_half == pytest.approx(-0.1)


# ---------------------------------------------------------------------------
# numerics: the fixed-point emulation vs generate_posterior (phase 0)
# ---------------------------------------------------------------------------

TIE_NATS = 1e-7     # two hypotheses closer than this in log-weight are a numerical tie


def _lockstep(p, seed, N=20, noise=True, lut_size=1 << 20, detune=0.37, **ckw):
    """Run the ARTIQ posterior (phase 0) and the OPX emulation on the same
    synthetic shot, feeding both the drive the ARTIQ side chose (snapped
    to the grid index the OPX would drive)."""
    c = _const(p, **ckw)
    m = c.m
    T = _tables_for(p, [seed])
    w_grid, zidx = T.w_grid[0], int(T.zidx[0])
    grid = T.omega_grid[0]
    rng = np.random.default_rng(seed)
    omega_true = c.omega_res + c.Omega * detune
    measure, _ = _synthetic_measure(p, c, omega_true, T.t_start_s[0], T.d_s[0],
                                    rng, noise=noise)
    fb = _artiq_feedback(p, lut_size=lut_size)
    fb.omega_guess_list = grid
    fb.omega_sq_list = grid * grid
    fb.reset_feedback_state()
    st = FixedPointState.uniform(m)
    n_photons = float(fb.N_photons_per_shot)
    d = int(T.d_init[0])
    rows = []
    floored_so_far = 0
    for i in range(N):
        w_d = float(w_grid[d])
        p_meas = measure(i, w_d)
        fb.omega_raman = c.omega_res + c.Omega * w_d
        fb.t_raman_pulse_current = float(T.d_s[0, i])
        fb.t_raman_pulse_ideal_current = float(T.d_s[0, i]) - c.t_offset_s
        omega_new, _mn, _std = fb.generate_posterior(
            n_photons * p_meas, float(T.t_start_s[0, i]),
            phase_raman_pulse_start=0.0, update_raman_frequency=1,
            update_rabi_frequency=0, include_photon_noise=1)
        u = posterior_update_fixed_point_emulation(
            st, d, p_meas, T.a[0, i], T.b[0, i], T.dphi0[0, i], T.ddphi[0, i],
            w_grid, c, zidx=zidx)
        floored_so_far += u['n_floored']
        L_artiq = np.log(np.maximum(fb.P0, 1e-300))
        top = np.sort(L_artiq)[-2:]
        tie = bool(top[1] - top[0] < TIE_NATS)
        w_next_artiq = (float(omega_new) - c.omega_res) / c.Omega
        rows.append(dict(
            P0_artiq=fb.P0.copy(), P0_fp=u['P0'], argmax_artiq=int(fb.max_idx),
            argmax_fp=u['jmax'], s_z_artiq=float(fb.state_z[zidx]), s_z_fp=u['s_z'],
            w_next_artiq=w_next_artiq, w_next_fp=u['w_next'], d_next_fp=u['d_next'],
            flat_fp=u['flat'], flat_artiq=(fb.P0[fb.max_idx] < 1.15 / m),
            clean=(floored_so_far == 0), n_floored=u['n_floored'], tie=tie,
            w_mean_fp=u['w_mean']))
        # both follow the ARTIQ decision, as the grid index the OPX would drive
        d = nearest_grid_index(w_grid, w_next_artiq)
    return rows


def _check_rows(rows, p0_tol, w_tol=1e-9, flat_rule=False, sz_tol=1e-9):
    """sz_tol: exact trig agrees to ~1e-10 in s_z; with the sincos table the
    table's own trig error (<= 2.9e-7 at 12 bits) propagates into s_z at the
    same order, so those cases pass a looser bound."""
    n_tie = 0
    for r in rows:
        if r['tie']:
            # exact symmetric degeneracy (e.g. hypotheses d +- k after the
            # first pulse from the pole): either index is a valid argmax
            n_tie += 1
            assert r['P0_fp'][r['argmax_fp']] == pytest.approx(r['P0_fp'][r['argmax_artiq']], abs=1e-6)
        else:
            assert r['argmax_fp'] == r['argmax_artiq']
        assert r['s_z_fp'] == pytest.approx(r['s_z_artiq'], abs=sz_tol)
        np.testing.assert_allclose(r['P0_fp'], r['P0_artiq'], atol=p0_tol)
        if flat_rule:
            assert r['flat_fp'] == r['flat_artiq']
        else:
            assert not r['flat_fp']
        if r['flat_fp']:
            # the OPX snaps the flat-rule mean to the nearest grid index
            assert abs(r['w_mean_fp'] - r['w_next_artiq']) < 2e-4
        elif not r['tie']:
            assert r['w_next_fp'] == pytest.approx(r['w_next_artiq'], abs=w_tol)
    return n_tie


def test_numerics_oracle_matches_generate_posterior():
    p = _params(N=20, m=21, span=3.0, offset=2.0)        # feedback_fast config
    # exact trig (opx_sincos_lut_bits = 0): the L/32 representation with no
    # clamp and the -78.5 nat floor agrees with the double-precision
    # posterior to 1e-6 in P0; every decision identical (ties aside)
    n_clean, n_total, n_tie = 0, 0, 0
    for seed in range(1, 7):
        rows = _lockstep(p, seed, sincos_lut_bits=0)
        n_tie += _check_rows(rows, p0_tol=1e-6)
        n_total += len(rows)
        n_clean += sum(int(r['clean']) for r in rows)
    assert n_clean >= 20 and n_total == 120 and n_tie <= 12
    for cfg in (dict(N=20, m=21, span=5.0, offset=0.0),
                dict(N=12, m=11, span=2.0, offset=-1.0)):
        _check_rows(_lockstep(_params(**cfg), seed=3, N=cfg['N'], noise=False,
                              sincos_lut_bits=0), p0_tol=1e-6)
    # the default (sincos table, 12 bits): <= 2.9e-7 on the trig values,
    # measured <= 3e-7 on s_z and <= 5e-7 on P0 over seeds 1-6; decisions
    # identical
    for seed in (1, 2, 3):
        _check_rows(_lockstep(p, seed), p0_tol=5e-5, sz_tol=1e-6)
    # the midpoint remap on (mid = 0.4): no p1 clamps needed, same agreement
    q = _params(N=20, m=21, span=3.0, offset=2.0,
                feedback_measurement_midpoint_remap_enabled=1,
                feedback_measurement_midpoint_fraction=0.4)
    _check_rows(_lockstep(q, 4, sincos_lut_bits=0), p0_tol=1e-6)
    # the flat rule restored (feedback_flat_rule_bool = 1): flat decisions
    # match ARTIQ's, the mean snapped to the grid
    q = _params(N=20, m=21, span=3.0, offset=2.0, feedback_flat_rule_bool=1)
    for seed in (1, 2):
        rows = _lockstep(q, seed, sincos_lut_bits=0)
        _check_rows(rows, p0_tol=1e-6, flat_rule=True)


def test_exp_and_sincos_lut_emulation_and_bit_arithmetic():
    # exp table (flat-rule path): exact at the nodes, <= (step^2/8) relative
    # in between; 8 bits -> 1.9e-6, 5 bits -> 1.2e-4
    for bits, tol in ((8, 1.95e-6), (5, 1.25e-4)):
        lut = exp_lut_table(bits)
        assert lut.size == 8 * 2 ** bits + 2 and lut[8 * 2 ** bits] == 1.
        L = np.linspace(-8., 0., 200001)
        e = exp_lut_emulation(L, bits)
        rel = np.abs(e - np.exp(L)) / np.exp(L)
        assert np.max(rel) <= tol
        nodes = -np.arange(0, 8 * 2 ** bits + 1) / 2 ** bits
        np.testing.assert_allclose(exp_lut_emulation(nodes, bits), np.exp(nodes), rtol=1e-15)
    bits = EXP_LUT_BITS
    lut = exp_lut_table(bits)
    n_lut, shift = 8 * 2 ** bits, 28 - bits
    rng = np.random.default_rng(0)
    for L in np.concatenate([rng.uniform(-8., 0., 500), [-8., -7.99999, -1., -1e-9, 0.]]):
        u = int(np.round(L * 2 ** 28))                   # the fixed bit pattern
        u = max(u, -2 ** 31)
        n_idx = (u >> shift) + n_lut                     # arithmetic shift floors
        rem = u - ((u >> shift) << shift)
        frac = (rem << bits) / 2 ** 28
        e_qua = lut[n_idx] + frac * (lut[n_idx + 1] - lut[n_idx])
        assert 0 <= n_idx <= n_lut and 0. <= frac < 1.
        assert e_qua == pytest.approx(float(exp_lut_emulation(u / 2 ** 28, bits)), abs=1e-12)
    # the sincos table: n + n/4 + 2 entries, cos read a quarter turn up,
    # <= (2pi/n)^2 / 8 absolute error; negative angles wrap
    for sbits, tol in ((12, 3.0e-7), (10, 4.8e-6)):
        tab = sincos_lut_table(sbits)
        n = 2 ** sbits
        assert tab.size == n + n // 4 + 2 and tab[0] == 0. and tab[n // 4] == 1.
        th = np.linspace(-7.99, 7.99, 400001)
        cc, ss = sincos_lut_emulation(th, sbits)
        assert np.max(np.abs(cc - np.cos(2 * np.pi * th))) <= tol
        assert np.max(np.abs(ss - np.sin(2 * np.pi * th))) <= tol
    # the QUA integer arithmetic on the 4.28 bit pattern (unsafe_cast_int,
    # the low 28 bits via arithmetic shifts, index / fraction) matches the
    # float emulation, including negative angles
    sbits = SINCOS_LUT_BITS
    tab = sincos_lut_table(sbits)
    n = 2 ** sbits
    for th in np.concatenate([rng.uniform(-7.99, 7.99, 500), [-0.3, -1e-9, 0., 0.999999, -7.99]]):
        u = int(np.round(th * 2 ** 28))
        fr28 = u - ((u >> 28) << 28)
        assert 0 <= fr28 < 2 ** 28
        ni = fr28 >> (28 - sbits)
        rem = fr28 - (ni << (28 - sbits))
        frac = (rem << sbits) / 2 ** 28
        c_qua = tab[ni + n // 4] + frac * (tab[ni + n // 4 + 1] - tab[ni + n // 4])
        s_qua = tab[ni] + frac * (tab[ni + 1] - tab[ni])
        cc, ss = sincos_lut_emulation(u / 2 ** 28, sbits)
        assert c_qua == pytest.approx(float(cc), abs=1e-12)
        assert s_qua == pytest.approx(float(ss), abs=1e-12)


def test_numerics_default_lut_effect_is_small():
    p = _params(N=20, m=21, span=3.0, offset=2.0)
    worst = 0.
    for seed in (1, 2):
        for r in _lockstep(p, seed, lut_size=4096, sincos_lut_bits=0):
            if not r['tie']:
                assert r['argmax_fp'] == r['argmax_artiq']
            worst = max(worst, float(np.max(np.abs(r['P0_fp'] - r['P0_artiq']))))
    assert worst < 1e-3


def test_fixed_point_ranges_and_floor_semantics():
    p = _params(N=20, m=21, span=3.0, offset=2.0)
    c = _const(p)
    T = _tables_for(p, [5])
    w_grid = T.w_grid[0]
    for d in (0, c.m - 1, int(T.d_init[0])):
        for p_meas in (-5., -2., 0., 0.5, 1., 3., 9.):
            st = FixedPointState.uniform(c.m)
            u = posterior_update_fixed_point_emulation(
                st, d, p_meas, T.a[0, 0], T.b[0, 0], T.dphi0[0, 0], T.ddphi[0, 0],
                w_grid, c, zidx=int(T.zidx[0]))
            assert -2. <= u['p_meas_used'] <= 3.
            assert np.all(u['L'] <= 0.) and np.all(u['L'] >= -8.)
            assert np.all(st.L <= 0.) and np.all(st.L >= -8.) and st.M == u['M']
            assert u['d_next'] == u['jmax'] and u['w_next'] == w_grid[u['jmax']]
            assert not u['flat'] and np.isnan(u['w_mean'])
    # the lazy floor: a hypothesis far below the previous max is held at
    # L_floor (-78.5 nats) before its decrement; no clamp anywhere
    st = FixedPointState.uniform(c.m)
    st.L[:] = -7.9
    st.L[3] = 0.
    st.M = 0.
    u = posterior_update_fixed_point_emulation(
        st, int(T.d_init[0]), 1.0, T.a[0, 0], T.b[0, 0], T.dphi0[0, 0],
        T.ddphi[0, 0], w_grid, c, zidx=int(T.zidx[0]))
    assert u['n_floored'] == c.m - 1
    assert np.min(st.L) >= -8. and np.max(st.L) <= 0.
    # and with M carried from a previous pulse the subtraction happens first
    st = FixedPointState.uniform(c.m)
    st.L[:] = -3.0
    st.M = -3.0
    u = posterior_update_fixed_point_emulation(
        st, int(T.d_init[0]), 0.5, T.a[0, 0], T.b[0, 0], T.dphi0[0, 0],
        T.ddphi[0, 0], w_grid, c, zidx=int(T.zidx[0]))
    assert u['n_floored'] == 0
    with pytest.raises(TypeError):
        posterior_update_fixed_point_emulation(
            FixedPointState.uniform(c.m), 2.0, 0.5, T.a[0, 0], T.b[0, 0], 0., 0., w_grid, c)
    with pytest.raises(ValueError, match='outside the grid'):
        posterior_update_fixed_point_emulation(
            FixedPointState.uniform(c.m), 21, 0.5, T.a[0, 0], T.b[0, 0], 0., 0., w_grid, c)
    with pytest.raises(FixedPointRangeError):
        posterior_update_fixed_point_emulation(
            FixedPointState.uniform(c.m), 0, 0.5, T.a[0, 0], T.b[0, 0], 0., 0., w_grid + 9., c)
    T6 = _tables_for(_params(m=21, span=3.0, offset=6.0), [5])
    assert T6.w_grid.min() == 0. and T6.w_grid.max() == pytest.approx(6.)
    with pytest.raises(ValueError, match='fixed'):
        _tables_for(_params(m=21, span=5.0, offset=6.0), [5])
    with pytest.raises(ValueError, match='detuning'):
        _tables_for(_params(m=21, span=5.5, offset=0.0), [5])


def test_shot_tables_draw_gaps_schedule_grid_and_levels():
    p = _params(N=6, m=7, span=2.0, offset=0.0, t_feedback_extra_gap=2.e-6)
    c = _const(p)
    assert c.extra_gap_cc == 500
    terms = _fake_terms()
    T = _tables_for(p, [11, 12], open_loop=True, terms=terms)
    for s, seed in enumerate((11, 12)):
        drawn = draw_t_raman_pulse_list(seed, 6, p.t_raman_pi_pulse, 0.5, 1.0)
        np.testing.assert_array_equal(T.d_cc[s], s_to_cc(drawn))
        np.testing.assert_allclose(T.d_s[s], T.d_cc[s] * 4e-9)
    assert np.all(T.d_cc >= 4) and T.level_idx is None
    # per-step gaps from the drawn list; the switch hold is the gap minus
    # the pulse, its edge and the sync overhead (the imaging exposure runs
    # inside the hold: t_img + edge + budget + extra); cumsum schedule
    np.testing.assert_array_equal(
        T.gap_cc, T.d_cc + 2 * c.edge_cc + c.t_img_cc + c.budget_cc + c.overhead_cc + 500)
    np.testing.assert_array_equal(
        T.wait_cc, np.full((2, 6), c.t_img_cc + c.edge_cc + c.budget_cc + 500))
    np.testing.assert_array_equal(T.t_start_cc[:, 0], 0)
    np.testing.assert_array_equal(T.t_start_cc[:, 1:], np.cumsum(T.gap_cc, axis=1)[:, :-1])
    np.testing.assert_allclose(T.t_start_s, scheduled_pulse_starts_s(p, T.d_s))
    np.testing.assert_array_equal(T.t_start_ext_cc, extend_schedule_cc(T.d_cc, c))
    g, z = feedback_grid_omega(p)
    np.testing.assert_array_equal(T.omega_grid[0], g)
    assert T.zidx[0] == z and T.w_grid[0, z] == 0.
    assert T.dw[0] == pytest.approx(2 * 2.0 / 6)
    assert list(T.d_init) == [z, z] and list(T.w_init) == [0., 0.]
    np.testing.assert_allclose(T.a, (T.d_s - c.t_offset_s) / (2 * p.t_raman_pi_pulse))
    np.testing.assert_allclose(T.b, T.d_s / (2 * p.t_raman_pi_pulse))
    phi0, dphi = hypothesis_phase_tables(T.omega_grid / (2 * np.pi),
                                         T.t_start_ext_cc * 4e-9)
    np.testing.assert_array_equal(T.phi0, phi0)
    np.testing.assert_array_equal(T.dphi, dphi)
    d0, dd = corotating_phase_tables(T.omega_grid / (2 * np.pi), T.t_start_ext_cc * 4e-9)
    np.testing.assert_array_equal(T.dphi0, d0)
    np.testing.assert_array_equal(T.ddphi, dd)
    np.testing.assert_array_equal(T.d_sched, np.tile(open_loop_drive_indices(7, 6), (2, 1)))
    np.testing.assert_array_equal(T.w_sched, T.w_grid[:, open_loop_drive_indices(7, 6)])
    assert T.if_hz.shape == (2, 7, 2)
    np.testing.assert_array_equal(T.if_hz[0], if_tables_hz(T.w_grid[0], c.f_Omega_hz, terms))
    # the initial drive snaps to the grid: 2.0 -> 2.1 in the simulator config
    Ts = _tables_for(_params(N=6, m=21, span=3.0, offset=2.0), [1])
    assert Ts.d_init[0] == 10 and Ts.w_init[0] == 2.0
    assert Ts.w_init_snapped[0] == pytest.approx(2.1)
    n = 3
    cols = {k: np.full(n, float(np.asarray(getattr(p, k), dtype=float).reshape(-1)[0]))
            for k in ('t_raman_pulse_random_bool', 't_raman_pulse',
                      't_raman_pulse_min_frac_pi', 't_raman_pulse_max_frac_pi',
                      'feedback_guess_span_Omega', 't_raman_pulse_seed')}
    cols['feedback_fractional_initial_offset'] = np.array([-2., 0., 2.])
    T2 = build_feedback_shot_tables(lambda k: cols[k], n, c, seeds=[1, 2, 3])
    assert list(T2.zidx) == [0, 3, 6]
    np.testing.assert_allclose(T2.w_init, [-2., 0., 2.])
    # the grid is centred on the initial offset and the initial drive is the
    # offset itself (ARTIQ: omega_res + Omega * offset), so the drive starts
    # at the centre index on every shot while the resonance index moves
    assert list(T2.d_init) == [3, 3, 3] and T2.if_hz is None
    cols['t_raman_pulse_seed'][:] = 0.
    T3 = build_feedback_shot_tables(lambda k: cols[k], n, c)
    assert np.all(T3.seed > 0) and len(set(T3.seed.tolist())) == 3
    # the smallest allowed budget (16 ns): the hold is the exposure + edge + 4
    q = _params(N=6, m=7, span=2.0, offset=0.0, t_opx_feedback_compute_budget=16.e-9)
    assert _tables_for(q, [1]).wait_cc.min() == c.t_img_cc + c.edge_cc + 4
    # discrete durations: the level draw, its index column, a shared level set
    q = _params(N=6, m=7, span=2.0, offset=0.0, t_raman_pulse_n_levels=8)
    Tl = _tables_for(q, [11, 12])
    lev = t_raman_pulse_level_set(q.t_raman_pi_pulse, 0.5, 1.0, 8)
    np.testing.assert_allclose(Tl.level_s, np.tile(lev, (2, 1)))
    assert Tl.level_idx.shape == (2, 6) and Tl.level_idx.dtype == np.int64
    for s, seed in enumerate((11, 12)):
        d_l, i_l = draw_t_raman_pulse_list_levels(seed, 6, q.t_raman_pi_pulse, 0.5, 1.0, 8)
        np.testing.assert_allclose(Tl.d_s[s], d_l)
        np.testing.assert_array_equal(Tl.level_idx[s], i_l)
    assert np.all(np.isin(np.rint(Tl.d_s / 4e-9), np.rint(lev / 4e-9)))
    cols_l = {k: np.full(2, float(np.asarray(getattr(q, k), dtype=float).reshape(-1)[0]))
              for k in cols}
    cols_l['t_raman_pulse_max_frac_pi'] = np.array([1.0, 0.9])
    with pytest.raises(ValueError, match='level set'):
        build_feedback_shot_tables(lambda k: cols_l[k], 2, _const(q), seeds=[1, 2])
    cols_l['t_raman_pulse_max_frac_pi'][:] = 1.0
    cols_l['t_raman_pulse_random_bool'][:] = 0.
    with pytest.raises(ValueError, match='random_bool'):
        build_feedback_shot_tables(lambda k: cols_l[k], 2, _const(q), seeds=[1, 2])


# ---------------------------------------------------------------------------
# the QUA trace
# ---------------------------------------------------------------------------

def _pulse_loop_order(N):
    """The regexes of one pulse's statements, in order (pass-3b structure:
    IF tables by drive index, the update after the measurement, the axis
    tables and the sincos table in the grid loop, argmax, in-loop saves)."""
    return [
        r"assign\(v\d+, a\d+\[v\d+\]\)",                        # if80 = table[d]
        r"assign\(v\d+, a\d+\[v\d+\]\)",                        # if150
        r"update_frequency\('raman_80', v\d+, 'Hz', False\)",
        r"update_frequency\('raman_150', v\d+, 'Hz', False\)",
        r"reset_if_phase\('raman_80'\)",
        r"reset_if_phase\('raman_150'\)",
        r"align\('raman_80', 'raman_150', 'raman_switch'\)",
        r"play\('pass', 'raman_switch', duration=a\d+\[\(\(v1\*%d\)\+v\d+\)\], timestamp_stream=r\d+\)" % N,
        r"play\('block', 'raman_switch'\)",
        r"align\('raman_switch', 'imaging_switch'\)",
        r"align\('imaging_switch', 'apd'\)",
        r"play\('pass', 'imaging_switch', duration=1250\)",
        r"play\('block', 'imaging_switch'\)",
        r"measure\('acquire', 'apd', integration\.full\(\"integration_window\", v\d+, \"out1\"\)\)",
        r"save\(v\d+, r\d+\)",                                  # apd
        r"wait\(a\d+\[\(\(v1\*%d\)\+v\d+\)\], 'raman_switch'\)" % N,   # per-step hold
        r"assign\(v\d+, \(\(v\d+--0\.24050[0-9]*\)\*5\.5796[0-9]*\)\)",  # photon fraction
        r"Util\.cond\(",                                        # the ONE clamp (x2)
        r"Util\.cond\(",
        r"assign\(v\d+, \(4-v\d+\)\)",                          # koff = (m-1) - d
        r"Cast\.mul_fixed_by_int\(-0\.\d+,v\d+\)",             # wq_d - wq_0 = dwq * d
        r"Math\.cos2pi\(v\d+\)",                                # the 4 seed trig calls
        r"Math\.sin2pi\(v\d+\)",
        r"Math\.cos2pi\(v\d+\)",
        r"Math\.sin2pi\(v\d+\)",
        r"assign\(v\d+, \(0\.62\*",                             # C folded into the seed phasor
        r"assign\(v\d+, \(v\d+\+v\d+\)\)",                      # kk = j + koff
        r"assign\(v\d+, a\d+\[v\d+\]\)",                        # h = table[kk]
        r"Cast\.unsafe_cast_int\(v\d+\)",                       # sincos table index
        r"assign\(v\d+, \(v\d+-\(\(v\d+>>28\)<<28\)\)\)",       # the 28 fraction bits
        r"Cast\.unsafe_cast_fixed\(\(v\d+<<12\)\)",
        r"assign\(v\d+, \(1\.0-v\d+\)\)",                       # omc
        r"Util\.cond\(",                                        # the lazy floor
        r"Math\.argmax\(",
        r"save\(v\d+, r\d+\)",                                  # drive_index
        r"save\(a\d+\[3\], r\d+\)",                             # s_z = z[zidx]
        r"save\(v\d+, r\d+\)",                                  # log_weights (L[j] - M)
    ]


def test_sequence_traces_offline():
    xv = [('t_raman_pulse_seed', [11, 12, 13])]
    N, m = 4, 5
    ex, tables, b, prog, ctx = _trace(bayesian_feedback, xv, N=N, m=m)
    assert bayesian_feedback.exp_lut_bits is None        # the run's params decide
    assert bayesian_feedback.sincos_lut_bits is None
    assert ctx._save_counts == {
        'apd': N, 'drive_index': N, 's_z': N, 'log_weights': N * m,
        't_pulse_start_cc': N}
    assert b.measurements['log_weights'] == Stream((N, m))
    assert b.measurements['drive_index'] == Stream((N,), int)
    assert b.measurements['t_pulse_start_cc'] == Stream((N,), int)
    assert b.measurements['apd'] == Stream((N,))
    assert ctx._stream_roles == {'apd': 'imaging'}           # volts on fill
    assert set(b.stream_specs()) == set(fbseq.STREAM_KEYS) | set(RESERVED_STREAMS)
    hd = ctx._host_data_values
    assert set(hd) == set(fbseq.HOST_KEYS) | set(fbseq.DERIVED_KEYS)
    assert hd['t_raman_pulse'].shape == (3, N)
    assert hd['omega_raman_mesh'].shape == (3, N + 1, m)
    assert hd['if_table_hz'].shape == (3, m, 2)
    assert hd['probabilities'].shape == (3, N + 1, m) and np.all(np.isnan(hd['probabilities']))
    assert hd['t_raman_pulse_seed'].reshape(-1).tolist() == [11., 12., 13.]
    g, _ = feedback_grid_omega(ex.params)
    assert np.allclose(hd['omega_raman_mesh'], g)
    c = _const(ex.params)
    terms = ctx.transition_offset_terms('raman')
    g_w = (g - 2 * np.pi * ex.params.frequency_raman_transition) / (np.pi / ex.params.t_raman_pi_pulse)
    np.testing.assert_array_equal(hd['if_table_hz'][0], if_tables_hz(g_w, c.f_Omega_hz, terms))
    # the per-step wait table and the phase tables are shipped, not saved;
    # the constant grid's IF and axis tables are plain QUA arrays
    assert set(ctx._shot_arrays) == {'t_raman_pulse_cc', 't_wait_cc', 'theta_scale_x4',
                                     'alpha_scale_x4', 'cos_dphi0', 'sin_dphi0',
                                     'cos_ddphi', 'sin_ddphi'}
    np.testing.assert_array_equal(ctx._shot_arrays['t_wait_cc'],
                                  np.full((3, N), c.t_img_cc + c.edge_cc + c.budget_cc))

    src = _qua(prog)
    st = _stmts(src)
    assert not any(x.startswith('with if_(') for x in st)
    for absent in ('Math.sqrt(', 'Math.exp(', 'Math.inv_sqrt(', 'Math.sum(', 'Math.inv(',
                   'Math.dot(', 'Math.max(', 'Math.argmin('):
        assert absent not in src, absent
    assert src.count('Math.cos2pi(') == 2 and src.count('Math.sin2pi(') == 2   # seeds only
    assert 'value=[0.0, 0.0015339801' in src                   # the sine table, 12 bits
    assert src.count('Util.cond(') == 3                        # pm clamp x2 + the floor
    assert 'timestamp_stream' not in src[src.index("play('pass', 'imaging_switch'"):
                                         src.index("wait(a")]   # only the Raman play
    pos = src.index("update_frequency('raman_80'")
    pos = src.rfind('assign(', 0, src.rfind('assign(', 0, pos))
    for pat in _pulse_loop_order(N):
        mm = re.compile(pat).search(src, pos)
        assert mm is not None, pat
        pos = mm.end()
    # the integer IF tables of the grid are declared with their values
    tab = if_tables_hz(g_w, c.f_Omega_hz, terms)
    assert f"declare(int, value=[{', '.join(str(int(v)) for v in tab[:, 0])}])" in src
    assert f"declare(int, value=[{', '.join(str(int(v)) for v in tab[:, 1])}])" in src
    # dw/4 for span 3, m 5 is -0.375; the ARTIQ-mirrored grid construction
    # gives it to float precision (3e-15 off, far below the 2^-28 fixed step)
    mm = re.search(r"assign\(v\d+, Cast\.mul_fixed_by_int\((-?[0-9.e-]+),v\d+\)\)", src)
    assert mm and float(mm.group(1)) == pytest.approx(-0.375, abs=1e-12)
    assert f"{c.L_floor}" in src or f"{c.L_floor:.10g}" in src[:0] or 'Util.cond((v' in src
    # the switch element sees exactly [align, pass, block, align, wait] per pulse
    recs = [r for r in b.log.records if r.phase == 'body']
    on_switch = [r for r in recs
                 if (r.element == 'raman_switch')
                 or (r.kind == 'align' and r.extra.get('elements')
                     and 'raman_switch' in r.extra['elements'])]
    kinds = [(r.kind, r.op if r.kind == 'play' else None) for r in on_switch]
    assert kinds == [('align', None), ('play', 'pass'), ('play', 'block'),
                     ('align', None), ('wait', None)]
    # framing: one trigger, the echo, the hand-back, the IF restore
    assert src.count("wait_for_trigger('raman_switch')") == 1
    assert 'r1.save_all("opx_shot_index")' in src
    assert re.search(r"play\('trigger', 'artiq_handback'", src)
    assert re.search(r"r\d+\.buffer\(%d\)\.buffer\(%d\)\.save_all\(\"log_weights\"\)" % (m, N), src)
    assert re.search(r"r\d+\.buffer\(%d\)\.save_all\(\"drive_index\"\)" % N, src)
    assert re.search(r"r\d+\.buffer\(%d\)\.save_all\(\"t_pulse_start_cc\"\)" % N, src)
    i_hb = src.index("'artiq_handback'")
    assert "update_frequency('raman_150', " in src[i_hb:]        # restored


def test_sequence_structure_variants_trace():
    N, m = 3, 5
    xv = [('t_raman_pulse_seed', [11, 12])]
    # opx_sincos_lut_bits = 0: Math trig per point, no sine table
    ex, tables, b, prog, ctx = _trace(bayesian_feedback, xv, N=N, m=m, opx_sincos_lut_bits=0)
    src = _qua(prog)
    assert src.count('Math.cos2pi(') == 3 and 'unsafe_cast' not in src
    assert 'value=[0.0, 0.0015339801' not in src
    assert ctx._save_counts['log_weights'] == N * m
    # an explicit override on the sequence beats the params (10-bit table)
    seq = make_feedback_sequence(False, sincos_lut_bits=10, name='_fb_sc10')
    assert seq.sincos_lut_bits == 10 and seq.exp_lut_bits is None
    ex, tables, b, prog, ctx = _trace(seq, xv, N=N, m=m, opx_sincos_lut_bits=0)
    src = _qua(prog)
    assert src.count('Math.cos2pi(') == 2
    assert re.search(r"Cast\.unsafe_cast_fixed\(\(v\d+<<10\)\)", src)
    assert 'value=[0.0, 0.0061358846' in src                   # sin(2 pi / 1024)
    # the flat rule on: the exp table pass, P/4 sums, dot, argmin snap
    ex, tables, b, prog, ctx = _trace(bayesian_feedback, xv, N=N, m=m, feedback_flat_rule_bool=1)
    src = _qua(prog)
    for present in ('Math.sum(', 'Math.inv(', 'Math.dot(', 'Math.argmin(', 'Math.abs(',
                    'Math.argmax('):
        assert present in src, present
    assert re.search(r"assign\(v\d+, \(\(v\d+>>20\)\+2048\)\)", src)       # exp table index
    assert re.search(r"declare\(fixed, value=\[0\.000335", src)            # exp(-8) first
    assert src.count('assign(v') > 0 and 'Math.exp(' not in src
    ex2, tables2, b2, prog2, ctx2 = _trace(bayesian_feedback, xv, N=N, m=m,
                                           feedback_flat_rule_bool=1, opx_exp_lut_bits=0)
    assert 'Math.exp(' in _qua(prog2)
    # the update is fully after the measurement
    i_upd = src.index("update_frequency('raman_80', v")
    i_meas = src.index("measure('acquire'")
    assert i_upd < i_meas < src.index('--0.2405', i_meas) < src.index('Math.argmax(', i_meas)
    # discrete durations (B+E): (level, k) tables, no trig at all, the
    # level index shipped per pulse
    ex, tables, b, prog, ctx = _trace(bayesian_feedback, xv, N=N, m=m, t_raman_pulse_n_levels=8)
    src = _qua(prog)
    assert 'Math.cos2pi(' not in src and 'Math.sin2pi(' not in src and 'unsafe_cast' not in src
    assert 'level_idx' in ctx._shot_arrays and 'theta_scale_x4' not in ctx._shot_arrays
    assert 'alpha_scale_x4' not in ctx._shot_arrays
    c = _const(ex.params)
    T = _tables_for(ex.params, [11, 12])
    mt = level_matrix_tables((T.level_s[0] - c.t_offset_s) / (2 * c.t_pi), float(T.dw[0]), m)
    first = ', '.join(str(float(v)) for v in mt['Am'].reshape(-1)[:3])
    assert f"declare(fixed, value=[{first}" in src
    assert re.search(r"assign\(v\d+, \(\(v\d+\*5\)\+v\d+\)\)", src)         # lm = level*m + d
    assert re.search(r"assign\(v\d+, \(\(v\d+\*9\)\+v\d+\)\)", src)         # kbase = level*(2m-1) + koff
    assert re.search(r"assign\(v\d+, \(\(1\.0\+v\d+\)-v\d+\)\)", src)      # E = (1 + c) - Am
    assert np.all(np.isin(ctx._shot_arrays['level_idx'], np.arange(8)))


def test_sequence_open_loop_and_per_shot_grid_trace():
    xv = [('feedback_fractional_initial_offset', [-2., 0., 2.])]
    ex, tables, b, prog, ctx = _trace(bayesian_feedback_open_loop, xv, N=3, m=5,
                                      span=2.0, update_raman_frequency_bool=0)
    hd = ctx._host_data_values
    assert set(hd) == set(fbseq.HOST_KEYS) | set(fbseq.DERIVED_KEYS)
    # the grid varies per shot: its IF tables are shipped per shot, the
    # axis tables (span constant) are not; the open-loop drive schedule is
    # shipped as indices, not saved (recomputable)
    assert {'if_table_80_hz', 'if_table_150_hz', 'zidx', 'drive_schedule_idx'} <= set(ctx._shot_arrays)
    assert 'drive_index_init' not in ctx._shot_arrays and 'axis_h' not in ctx._shot_arrays
    src = _qua(prog)
    assert re.search(r"assign\(v\d+, a\d+\[\(\(v1\*5\)\+v\d+\)\]\)", src)   # if80 from the shot table
    for s in range(3):
        g, z = feedback_grid_omega(ex.params, fractional_initial_offset=[-2., 0., 2.][s])
        np.testing.assert_allclose(hd['omega_raman_mesh'][s, 0], g)
        assert ctx._shot_arrays['zidx'][s] == z
    idx = open_loop_drive_indices(5, 3)
    np.testing.assert_array_equal(ctx._shot_arrays['drive_schedule_idx'], np.tile(idx, (3, 1)))
    np.testing.assert_array_equal(hd['if_table_hz'][:, :, 0], ctx._shot_arrays['if_table_80_hz'])
    # a scanned span makes the axis tables per shot; spans 1 and 3 at offset 1
    # move the resonance index (4 vs 3) while the initial drive stays at the
    # grid centre (index 2), so only the former is shipped per shot
    xv2 = [('feedback_guess_span_Omega', [1.0, 3.0])]
    ex, tables, b, prog, ctx = _trace(bayesian_feedback, xv2, N=3, m=5, offset=1.0)
    assert {'axis_h', 'axis_ux2', 'grid_step_wq', 'if_table_80_hz'} <= set(ctx._shot_arrays)
    assert 'zidx' in ctx._shot_arrays and 'drive_index_init' not in ctx._shot_arrays
    np.testing.assert_array_equal(ctx._shot_arrays['zidx'], [4, 3])


def test_sequence_refuses_bad_configs():
    xv = [('t_raman_pulse_seed', [11, 12])]
    with pytest.raises(RuntimeError, match='update_raman_frequency_bool'):
        _trace(bayesian_feedback, xv, N=3, m=5, update_raman_frequency_bool=0)
    with pytest.raises(RuntimeError, match='update_raman_frequency_bool'):
        _trace(bayesian_feedback_open_loop, xv, N=3, m=5)
    with pytest.raises(ValueError, match='remesh'):
        _trace(bayesian_feedback, xv, N=3, m=5, feedback_remesh_threshold_Omega=0.5)
    with pytest.raises(RuntimeError, match='t_img_pulse'):
        _trace(bayesian_feedback, xv, N=3, m=5, t_img_pulse=4.e-6)
    with pytest.raises(RuntimeError, match='varies per shot'):
        _trace(bayesian_feedback, [('frequency_raman_transition', [119.46e6, 119.47e6])],
               N=3, m=5)
    with pytest.raises(ValueError, match='levels'):
        _trace(bayesian_feedback, xv, N=3, m=5, t_raman_pulse_n_levels=3)
    # the flat rule needs a run-constant grid (Math.dot over the w/4 array)
    with pytest.raises(RuntimeError, match='run-constant grid'):
        _trace(bayesian_feedback, [('feedback_fractional_initial_offset', [0., 1.])],
               N=3, m=5, feedback_flat_rule_bool=1)
    # discrete durations need run-constant tables (no scanned span)
    with pytest.raises(RuntimeError, match='run constants'):
        _trace(bayesian_feedback, [('feedback_guess_span_Omega', [2., 3.])],
               N=3, m=5, t_raman_pulse_n_levels=8)
    # a drive split that is not the +1/+1 double pass: its IF0s do not
    # invert to the run transition
    ex = FeedbackOPXExpt(xv, N=3, m=5)
    cmap = make_transition_map(ex)
    cmap.channels['raman'].transition_to_ifs = lambda f: {
        'raman_80': 0.2 * np.asarray(f, float), 'raman_150': 0.8 * np.asarray(f, float)}
    with pytest.raises(RuntimeError, match='does not reproduce'):
        _trace(bayesian_feedback, xv, cmap=cmap, N=3, m=5)
    seq = make_feedback_sequence(False)
    assert seq.name == 'bayesian_feedback' and seq.finish is feedback_finish
    assert seq.claims == ('raman', 'imaging')


# ---------------------------------------------------------------------------
# finish hook
# ---------------------------------------------------------------------------

def _finish_stub(n_shots, N, m):
    stub = FeedbackOPXExpt([('t_raman_pulse_seed', np.arange(1, n_shots + 1))], N=N, m=m)
    data = DataVault(expt=stub)
    for key, spec in bayesian_feedback.resolve_measurements(stub.params).items():
        setattr(data, key, data.add_data_container(spec.shape, spec.np_dtype))
    for key, spec in bayesian_feedback.resolve_host_data(stub.params).items():
        setattr(data, key, data.add_data_container(spec.shape, np.float64))
    for key, spec in RESERVED_STREAMS.items():
        setattr(data, key, data.add_data_container(spec.shape, np.int64))
    setattr(data, VALID_MASK_KEY, data.add_data_container((1,), np.int32))
    data.init()
    stub.data = data
    return stub


def test_finish_hook_derives_containers(capsys):
    n_shots, N, m = 3, 4, 5
    stub = _finish_stub(n_shots, N, m)
    p = stub.params
    d = stub.data
    rng = np.random.default_rng(0)
    terms = _fake_terms()
    c = _const(p)
    T = _tables_for(p, [1, 2, 3], terms=terms)
    valid = np.array([1, 1, 0], dtype=np.int32)
    apd_v = rng.normal(-0.16, 0.01, (n_shots, N)); apd_v[2] = np.nan
    didx = rng.integers(0, m, (n_shots, N)).astype(np.int64)
    didx[2] = INT_MISSING
    Lw = -rng.uniform(0, 3, (n_shots, N, m)); Lw[..., 2] = 0.; Lw[2] = np.nan
    d_s = rng.uniform(3.5e-6, 7.e-6, (n_shots, N)); d_s = np.rint(d_s / 4e-9) * 4e-9
    t_sched = scheduled_pulse_starts_s(p, d_s)              # what the OPX was held to
    t0 = np.array([1000, 2 ** 32 - 300, 0], dtype=np.int64)  # shot 1 wraps
    t_cc = ((t0[:, None] + np.rint(t_sched / 4e-9).astype(np.int64)) % 2 ** 32)
    t_cc[0, 2] += 3                                           # 3-cycle slip
    t_cc[2] = INT_MISSING
    d.apd._run_data[:] = apd_v
    d.drive_index._run_data[:] = didx
    d.if_table_hz._run_data[:] = T.if_hz.astype(float)
    d.log_weights._run_data[:] = Lw
    d.t_pulse_start_cc._run_data[:] = t_cc
    d.t_raman_pulse._run_data[:] = d_s
    getattr(d, VALID_MASK_KEY)._run_data[:] = valid

    feedback_finish(stub, d)
    out = capsys.readouterr().out

    om = d.omega_raman._run_data
    for s in range(2):
        f_exp = 2. * (T.if_hz[s, didx[s], 1] - T.if_hz[s, didx[s], 0])
        np.testing.assert_array_equal(om[s], 2 * np.pi * f_exp)
        # the applied frequency is the grid point's to within the integer rounding
        assert np.max(np.abs(f_exp - (p.frequency_raman_transition
                                       + T.w_grid[s, didx[s]] * c.f_Omega_hz))) <= 3.
    assert np.all(np.isnan(om[2]))
    prob = d.probabilities._run_data
    assert prob.shape == (n_shots, N + 1, m)
    np.testing.assert_allclose(prob[:2, 0], 1. / m)
    np.testing.assert_allclose(prob[:2, 1:], log_weights_to_probabilities(Lw[:2], 32))
    np.testing.assert_allclose(np.sum(prob[:2, 1:], axis=-1), 1.)
    assert np.all(np.isnan(prob[2]))
    ts = d.t_pulse_start._run_data
    np.testing.assert_allclose(ts[1], t_sched[1], atol=1e-15)          # wrap repaired
    np.testing.assert_allclose(ts[0, [0, 1, 3]], t_sched[0, [0, 1, 3]], atol=1e-15)
    assert ts[0, 2] == pytest.approx(t_sched[0, 2] + 3 * 4e-9)
    assert np.all(np.isnan(ts[2]))
    np.testing.assert_allclose(d.t._run_data[:2], ts[:2] + d_s[:2] + p.t_img_pulse)
    # no slip container: the check is recomputed from the durations + params
    assert not hasattr(d, 'opx_schedule_slip')
    assert 'slip: 3.0 cycles' in out and '***' in out and '1 pulse(s)' in out
    for key in fbseq.DERIVED_KEYS:
        assert getattr(d, key)._data_gotten

    stub = _finish_stub(1, N, m)
    d = stub.data
    d.apd._run_data[:] = 0.1
    d.drive_index._run_data[:] = T.zidx[0]
    d.if_table_hz._run_data[:] = T.if_hz[0].astype(float)
    d.log_weights._run_data[:] = 0.
    d_s = np.full((1, N), 4.e-6)
    d.t_raman_pulse._run_data[:] = d_s
    t_sched = scheduled_pulse_starts_s(p, d_s)
    d.t_pulse_start_cc._run_data[:] = 77 + np.rint(t_sched / 4e-9).astype(np.int64)
    getattr(d, VALID_MASK_KEY)._run_data[:] = 1
    feedback_finish(stub, d)
    out = capsys.readouterr().out
    assert 'slip: 0.0 cycles' in out and '***' not in out
    np.testing.assert_allclose(d.probabilities._run_data[0, 1:], 1. / m)
    assert abs(d.omega_raman._run_data[0, 0] / (2 * np.pi) - p.frequency_raman_transition) <= 2.


def test_timestamp_and_probability_conversions():
    t = np.array([[10, 20, 35], [2 ** 32 - 5, 5, 15], [-1, 3, 4]], dtype=np.int64)
    s = timestamps_cc_to_seconds(t)
    np.testing.assert_allclose(s[0], [0., 40e-9, 100e-9])
    np.testing.assert_allclose(s[1], [0., 40e-9, 80e-9])       # wraps mod 2^32
    assert np.all(np.isnan(s[2]))                               # no reference pulse
    s2 = timestamps_cc_to_seconds(t, valid=[1, 0, 1])
    assert np.all(np.isnan(s2[1]))
    s3 = timestamps_cc_to_seconds(t, t_ref_cc=[5, 2 ** 32 - 10, -1])
    np.testing.assert_allclose(s3[0], [20e-9, 60e-9, 120e-9])
    np.testing.assert_allclose(s3[1], [20e-9, 60e-9, 100e-9])
    assert np.all(np.isnan(s3[2]))
    L = np.array([[0., -1., -8.]])
    P = log_weights_to_probabilities(L, 32)
    np.testing.assert_allclose(P[0], np.exp(32 * L[0]) / np.sum(np.exp(32 * L[0])))
    np.testing.assert_allclose(fbseq.log_weights4_to_probabilities(L),
                               log_weights_to_probabilities(L, 4))
    assert volts2raw(demod2volts(0.3, 5.e-6), 5.e-6) == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# replay class on a synthetic run made by the emulation
# ---------------------------------------------------------------------------

def _synthetic_ad(p, seeds, detune=0.37, noise=True, drop_last=False,
                  open_loop=False):
    """A fake atomdata from a synthetic closed-loop run produced by the
    emulation: what the OPX would have saved (the minimal data set), in
    ARTIQ names. drive_index and if_table_hz are exactly what the OPX
    streams/ships. Returns the drive indices too."""
    c = _const(p)
    n, N, m = len(seeds), c.N, c.m
    terms = _fake_terms()
    T = _tables_for(p, seeds, open_loop=open_loop, terms=terms)
    omega_true = c.omega_res + c.Omega * detune
    apd = np.empty((n, N)); d_used = np.empty((n, N), dtype=np.int64); s_z = np.empty((n, N))
    Lw = np.empty((n, N, m)); floors = 0
    for s in range(n):
        rng = np.random.default_rng(100 + seeds[s])
        measure, _ = _synthetic_measure(p, c, omega_true, T.t_start_s[s], T.d_s[s],
                                        rng, noise=noise)
        out = run_shot_fixed_point_emulation(
            T.w_grid[s], int(T.zidx[s]), T.a[s], T.b[s], T.dphi0[s], T.ddphi[s], c,
            measure, d_init=int(T.d_init[s]),
            d_sched=(T.d_sched[s] if open_loop else None))
        apd[s] = p.v_apd_all_down_opx + out['p_meas'] * (p.v_apd_all_up_opx - p.v_apd_all_down_opx)
        d_used[s], s_z[s], Lw[s] = out['d_used'], out['s_z'], out['L']
        floors += int(np.sum(out['n_floored']))
    valid = np.ones(n, dtype=np.int32)
    if drop_last:
        valid[-1] = 0
        apd[-1] = np.nan; s_z[-1] = np.nan; Lw[-1] = np.nan
        d_used[-1] = INT_MISSING
    prob = np.full((n, N + 1, m), np.nan)
    prob[:, 0] = 1. / m
    prob[:, 1:] = log_weights_to_probabilities(Lw, c.scale)
    om = 2 * np.pi * applied_frequency_hz(T.if_hz, d_used)
    om[valid == 0] = np.nan
    t_cc = 900 + np.arange(n, dtype=np.int64)[:, None] * 500000 + T.t_start_cc
    data = SimpleNamespace(
        apd=apd, drive_index=d_used, if_table_hz=T.if_hz.astype(float), s_z=s_z,
        log_weights=Lw, t_pulse_start_cc=t_cc,
        t_raman_pulse=T.d_s, t_raman_pulse_seed=np.asarray(seeds, dtype=float),
        omega_raman_mesh=np.repeat(T.omega_grid[:, None, :], N + 1, axis=1),
        omega_raman=om, probabilities=prob, t_pulse_start=T.t_start_s.copy(),
        t=T.t_start_s + T.d_s + p.t_img_pulse,
        opx_data_valid=valid)
    ad = SimpleNamespace(p=copy.copy(p), data=data, run_info=SimpleNamespace(run_id=4242),
                         xvarnames=['t_raman_pulse_seed'], xvardims=[n])
    return ad, T, floors, omega_true, d_used


def test_replay_class_roundtrip_synthetic():
    p = _params(N=8, m=9, span=2.0, offset=0.0)
    ad, T, floors, omega_true, d_used = _synthetic_ad(p, [1, 2, 3, 4])
    fr = FeedbackOPXReplay(ad)
    assert fr.n_shots == 4 and fr.N_step == 8 and fr.m == 9
    assert fr.v_apd_all_up == p.v_apd_all_up_opx
    assert fr.std_n_photons_per_shot / fr.N_photons_per_shot == pytest.approx(p.std_photon_fraction_opx)
    assert fr.L_opx_rr.shape == (4, 8, 9) and fr.L_prior_rr is None
    assert fr.log_weight_scale == 32 and fr.drive_index_rr.shape == (4, 8)
    omega_res, Omega = fr._omega_resonance_rad_s, fr.Omega
    w_used = np.take_along_axis(T.w_grid, d_used, axis=1)
    om_ctrl = omega_res + Omega * w_used                        # the OPX's own control

    # the exact-frequency round trip: the default replay drives with the
    # applied integer-Hz frequency (drive_index + if_table_hz), which the
    # emulation snaps back onto the exact grid index, so it reproduces the
    # run it generated exactly
    res = fr.emulate_fixed_point(True).replay_measured()
    assert res.metadata['fixed_point_emulation'] and res.metadata['t_source'] == 'actual'
    assert res.metadata['control_omega_source'] == 'measured'
    assert res.metadata['control_snap_Omega'] < 3. / fr.p.frequency_raman_transition * 1e3
    np.testing.assert_allclose(res.omega_control_rr, om_ctrl, rtol=1e-12)
    np.testing.assert_allclose(res.P0_rr, ad.data.probabilities[:, 1:], atol=1e-9)
    np.testing.assert_allclose(res.s_z_rr, ad.data.s_z, atol=1e-9)
    assert np.nanmax(res.max_abs_dP_r) < 1e-9
    np.testing.assert_allclose(res.slip_rr, 0.)
    np.testing.assert_allclose(res.t_pulse_start_rr, T.t_start_s)
    np.testing.assert_allclose(res.t_scheduled_rr, T.t_start_s)
    assert np.nanmax(np.abs(res.omega_applied_rr - om_ctrl)) < 2 * np.pi * 3.
    rep = fr.compare_with_opx(res)
    assert rep['max_abs_dP'] < 1e-9 and rep['argmax_agreement_fraction'] == 1.
    assert rep['argmax_ok'] and rep['n_argmax_disagree'] == 0
    assert rep['argmax_agreement_expected'] == ARGMAX_AGREEMENT_EXPECTED == 0.99
    assert rep['n_valid'] == 4 and 'fixed-point' in rep['summary'] and '99%' in rep['summary']
    # the same through an explicit override of the exact control
    res_o = fr.simulate_counterfactual(omega_control_rr=om_ctrl, control_omega_source='override')
    np.testing.assert_allclose(res_o.P0_rr, res.P0_rr, atol=1e-12)

    # the double-precision replay with the applied frequency (<= 3 Hz from
    # the grid point) against the OPX's own posterior: the floor is the only
    # representation difference, argmax everywhere the same
    res2 = fr.emulate_fixed_point(False).replay_measured()
    assert not res2.metadata['fixed_point_emulation']
    np.testing.assert_allclose(res2.omega_control_rr, 2 * np.pi * applied_frequency_hz(
        ad.data.if_table_hz, ad.data.drive_index))
    rep2 = fr.compare_with_opx(res2)
    assert rep2['argmax_agreement_fraction'] == 1. and rep2['argmax_ok']
    assert rep2['max_abs_dP'] < 1e-4
    # ... and with the exact grid control it agrees to the floor level
    res2w = fr.simulate_counterfactual(omega_control_rr=om_ctrl,
                                       control_omega_source='override')
    rep2w = fr.compare_with_opx(res2w)
    assert rep2w['argmax_agreement_fraction'] == 1.
    assert rep2w['max_abs_dP'] < (1e-6 if floors == 0 else 1e-4)
    # the closed loop recomputed by the emulation reproduces the control
    res3 = fr.emulate_fixed_point(True).replay_measured(control_omega_source='recomputed')
    np.testing.assert_allclose(res3.omega_control_rr, om_ctrl, rtol=1e-12)
    # scheduled instead of actual timestamps: identical here (slip 0)
    res4 = fr.simulate_counterfactual(omega_control_rr=om_ctrl,
                                      control_omega_source='override',
                                      use_actual_timestamps=False)
    assert res4.metadata['t_source'] == 'scheduled'
    np.testing.assert_allclose(res4.P0_rr, res.P0_rr, atol=1e-9)
    assert res.log_weights_opx_rr.shape == (4, 8, 9) and res.P0_opx_rr.shape == (4, 8, 9)
    np.testing.assert_allclose(res.log_weights4_opx_rr, res.log_weights_opx_rr * 8)
    assert res.t_raman_pulse_rr.shape == (4, 8) and res.dT_mu_rr.shape == (4, 8)
    assert np.all(np.isnan(res.dT_mu_rr[:, -1])) and np.all(res.dT_mu_rr[:, :-1] > 0)
    fr.emulate_fixed_point(False)

    fr.p.frequency_lightshift = p.frequency_lightshift * 1.5
    res_cf = fr.simulate_counterfactual()
    assert res_cf.metadata['control_omega_source'] == 'recomputed'
    assert np.nanmax(np.abs(res_cf.P0_rr - res.P0_rr)) > 1e-6
    fr.p.frequency_lightshift = p.frequency_lightshift
    synth = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.3, seed=2, noise_scale=0.)
    assert synth['apd_rr'].shape == (4, 8) and np.all(np.isfinite(synth['apd_rr']))
    assert synth['omega_true_rad_s'] == pytest.approx(omega_res + 0.3 * Omega)
    # the synthetic run replays through the counterfactual path consistently
    res_s = fr.simulate_counterfactual(apd_input_rr=synth['apd_rr'],
                                       omega_control_rr=synth['omega_control_rr'],
                                       control_omega_source='override')
    assert np.all(np.isfinite(res_s.P0_rr))
    synth_fp = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.3, seed=2, fixed_point=True)
    assert np.all(np.isfinite(synth_fp['apd_rr']))
    w_fp = (synth_fp['omega_control_rr'] - omega_res) / Omega
    assert np.all(np.isin(np.round(w_fp, 9), np.round(T.w_grid[0], 9)))   # on-grid drives
    # the null test the ARTIQ replay offers: an injected ON-GRID truth
    # (0.5 Omega = one grid step) with noiseless measurements is reproduced
    # exactly by its own hypothesis, so the posterior argmax must be that
    # hypothesis on every shot and the posterior concentrated on it
    p20 = _params(N=20, m=9, span=2.0, offset=0.0)
    ad20, _T, _f, _o, _d = _synthetic_ad(p20, [1, 2])
    fr20 = FeedbackOPXReplay(ad20)
    s20 = fr20.simulate_feedback_run_apd(detuning_offset_Omega=0.5, seed=2, noise_scale=0.)
    r20 = fr20.simulate_counterfactual(apd_input_rr=s20['apd_rr'],
                                       omega_control_rr=s20['omega_control_rr'],
                                       control_omega_source='override')
    grid_w = (r20.omega_guess_list - fr20._omega_resonance_rad_s) / fr20.Omega
    j_true = int(np.argmin(np.abs(grid_w - 0.5)))
    assert grid_w[j_true] == pytest.approx(0.5, abs=1e-12)
    final = r20.P0_rr[:, -1, :]
    assert list(np.argmax(final, axis=1)) == [j_true, j_true]
    # the majority of the mass sits on the true hypothesis (sigma_p = 0.16
    # leaves its neighbours some, ~0.7-0.8 on it after 20 pulses)
    assert np.all(final[:, j_true] > 0.5), final[:, j_true]
    # the same null test through the OPX emulation as the controller
    s20f = fr20.simulate_feedback_run_apd(detuning_offset_Omega=0.5, seed=2, noise_scale=0.,
                                          fixed_point=True)
    r20f = fr20.emulate_fixed_point(True).simulate_counterfactual(
        apd_input_rr=s20f['apd_rr'], omega_control_rr=s20f['omega_control_rr'],
        control_omega_source='override')
    assert list(np.argmax(r20f.P0_rr[:, -1, :], axis=1)) == [j_true, j_true]


def test_replay_handles_invalid_shots_scanned_offset_open_loop_and_old_files():
    p = _params(N=5, m=7, span=2.0, offset=0.0)
    ad, T, _f, _o, d_used = _synthetic_ad(p, [7, 8, 9], drop_last=True)
    fr = FeedbackOPXReplay(ad)
    assert list(fr.valid_r) == [True, True, False]
    res = fr.emulate_fixed_point(True).replay_measured()
    assert np.all(np.isnan(res.P0_rr[2])) and np.all(np.isfinite(res.P0_rr[:2]))
    assert np.isnan(res.max_abs_dP_r[2]) and res.metadata['n_valid'] == 2
    rep = fr.compare_with_opx(res)
    assert rep['n_valid'] == 2 and rep['max_abs_dP'] < 1e-9
    # pass-2 files: dif_hz + log_weights4 (scale 4) instead of the index/table
    ad2 = copy.deepcopy(ad)
    om_old = ad2.data.omega_raman.copy()
    dif = np.rint(om_old / (2 * np.pi) / 2.)
    dif[~np.isfinite(dif)] = INT_MISSING
    ad2.data.dif_hz = dif.astype(np.int64)
    ad2.data.log_weights4 = ad2.data.log_weights * 8.
    del ad2.data.drive_index, ad2.data.if_table_hz, ad2.data.log_weights
    fr_old = FeedbackOPXReplay(ad2)
    assert fr_old.log_weight_scale == 4. and fr_old.drive_index_rr is None
    np.testing.assert_allclose(np.nan_to_num(fr_old.omega_applied_rr),
                               np.nan_to_num(2 * np.pi * 2. * np.where(dif < 0, np.nan, dif)))
    np.testing.assert_allclose(fr_old.P0_opx_rr[:2], fr.P0_opx_rr[:2])
    # older still: only the omega_raman container
    del ad2.data.dif_hz
    fr_older = FeedbackOPXReplay(ad2)
    np.testing.assert_array_equal(np.nan_to_num(fr_older.omega_applied_rr), np.nan_to_num(om_old))

    p2 = _params(N=5, m=7, span=2.0, offset=0.0)
    ad2, T2, _f2, _o2, _d2 = _synthetic_ad(p2, [3, 4])
    ad2.p.feedback_fractional_initial_offset = np.array([0., 1.])
    ad2.xvarnames, ad2.xvardims = ['feedback_fractional_initial_offset'], [2]
    c = _const(p2)
    cols = {k: np.full(2, float(np.asarray(getattr(p2, k), dtype=float).reshape(-1)[0]))
            for k in ('t_raman_pulse_random_bool', 't_raman_pulse',
                      't_raman_pulse_min_frac_pi', 't_raman_pulse_max_frac_pi',
                      'feedback_guess_span_Omega', 't_raman_pulse_seed')}
    cols['feedback_fractional_initial_offset'] = np.array([0., 1.])
    Tb = build_feedback_shot_tables(lambda k: cols[k], 2, c, seeds=[3, 4])
    ad2.data.omega_raman_mesh = np.repeat(Tb.omega_grid[:, None, :], 6, axis=1)
    fr2 = FeedbackOPXReplay(ad2)
    np.testing.assert_allclose(fr2.offset_r, [0., 1.])
    g1, z1 = fr2._grid_for_shot(1)
    np.testing.assert_allclose(g1, Tb.omega_grid[1])
    assert z1 == Tb.zidx[1]

    p3 = _params(N=6, m=7, span=2.0, offset=0.0, update_raman_frequency_bool=0)
    ad3, T3, _f3, _o3, d3 = _synthetic_ad(p3, [5, 6], open_loop=True)
    fr3 = FeedbackOPXReplay(ad3)
    np.testing.assert_array_equal(d3, T3.d_sched)
    res3 = fr3.emulate_fixed_point(True).replay_measured()
    np.testing.assert_allclose(res3.P0_rr, ad3.data.probabilities[:, 1:], atol=1e-9)
    res3b = fr3.emulate_fixed_point(False).replay_measured()
    assert fr3.compare_with_opx(res3b)['argmax_agreement_fraction'] == 1.
    # the flat rule flag is mirrored: a file recorded with it on replays with it
    p4 = _params(N=6, m=7, span=2.0, offset=0.0, feedback_flat_rule_bool=1)
    ad4, T4, _f4, _o4, d4 = _synthetic_ad(p4, [5, 6])
    fr4 = FeedbackOPXReplay(ad4)
    assert fr4.constants().flat_rule
    res4 = fr4.emulate_fixed_point(True).replay_measured()
    np.testing.assert_allclose(res4.P0_rr, ad4.data.probabilities[:, 1:], atol=1e-9)
    # ... and the levels option: the durations come from the level set
    p5 = _params(N=6, m=7, span=2.0, offset=0.0, t_raman_pulse_n_levels=8)
    ad5, T5, _f5, _o5, d5 = _synthetic_ad(p5, [5, 6])
    fr5 = FeedbackOPXReplay(ad5)
    assert fr5.constants().n_levels == 8
    res5 = fr5.emulate_fixed_point(True).replay_measured()
    np.testing.assert_allclose(res5.P0_rr, ad5.data.probabilities[:, 1:], atol=1e-9)


def test_manager_path_use_finish_prepare_fill_and_finish(monkeypatch, capsys):
    """The whole host-side data path with the real config builder and
    channel map: use() registers every container with the resolved shapes,
    on_finish_prepare traces (connection monkeypatched out) and writes the
    provenance texts, fill_containers takes synthetic streams + the host
    tables, and the finish hook derives the ARTIQ-named containers."""
    import json
    from kexp.control.opx.manager import (OPXManager, SHOT_TABLES_ATTR,
                                          QUA_SOURCE_ATTR)
    from kexp.control.opx.opx_config import kexp_channel_map, build_opx_config

    class Stub(FeedbackOPXExpt):
        def __init__(self, xvars, **kw):
            super().__init__(xvars, **kw)
            self.xvarnames = [xv.key for xv in self.scan_xvars]
            self.data = DataVault(expt=self)
            self.run_info = SimpleNamespace(save_data=False)
            self._extra_file_texts = {}
            self._shot_complete_count = int(np.prod(self.xvardims))

    N, m = 3, 5
    stub = Stub([('t_raman_pulse_seed', [21, 22])], N=N, m=m)
    monkeypatch.setattr(OPXManager, '_connect', lambda self: None)
    monkeypatch.setattr(OPXManager, '_run_simulation', lambda self, prog, config: None)
    mgr = OPXManager(stub, host='none', cluster='none',
                     map_builder=kexp_channel_map, config_builder=build_opx_config)
    mgr._exit_after_simulate = False
    mgr.use(bayesian_feedback, simulate=True, simulate_viewer=False,
            simulate_web_plot=False, simulate_shots=0)
    d = stub.data
    for key in fbseq.STREAM_KEYS + fbseq.HOST_KEYS + fbseq.DERIVED_KEYS + tuple(RESERVED_STREAMS):
        assert hasattr(d, key), key
    for key in ('apd_raw', 'omega_control_w', 'if_raman_80_hz', 't_pulse_scheduled',
                'opx_schedule_slip', 'hypothesis_phi0', 't_between_pulses', 'dif_hz',
                'log_weights4'):
        assert not hasattr(d, key), key
    assert d.log_weights._per_shot_data_shape == (N, m)
    assert d.t_pulse_start_cc._dtype is np.int64 and d.drive_index._dtype is np.int64
    assert d.if_table_hz._per_shot_data_shape == (m, 2)
    assert d.probabilities._per_shot_data_shape == (N + 1, m)
    mgr.on_finish_prepare()
    texts = stub._extra_file_texts
    assert 'reset_if_phase' in texts[QUA_SOURCE_ATTR]
    doc = json.loads(texts[SHOT_TABLES_ATTR])
    assert doc['n_shots'] == 2 and doc['sequence'] == 'bayesian_feedback'
    assert set(doc['shot_arrays']) >= {'t_raman_pulse_cc', 't_wait_cc', 'cos_dphi0'}
    for key in ('feedback_flat_rule_bool', 'feedback_log_weight_scale', 'opx_sincos_lut_bits',
                't_raman_pulse_n_levels', 't_feedback_extra_gap'):
        assert key in doc['accessed'], key
    assert mgr._host_values['t_raman_pulse'].shape == (2, N)
    assert mgr._host_values['if_table_hz'].shape == (2, m, 2)

    d.init()
    specs = mgr._stream_specs
    rng = np.random.default_rng(1)
    d_s = mgr._host_values['t_raman_pulse']
    t_sched_cc = np.rint(scheduled_pulse_starts_s(stub.params, d_s) / 4e-9).astype(np.int64)
    c = _const(stub.params)
    t_p = np.array([[600], [300600]], dtype=np.int64) + 400 + t_sched_cc
    didx = np.array([[0, 2, 4], [1, 3, 3]])
    fetched = {
        'apd': rng.normal(-0.2, 0.01, (2, N)),
        'drive_index': didx,
        's_z': rng.uniform(-1, 1, (2, N)),
        'log_weights': -rng.uniform(0, 2, (2, N, m)),
        't_pulse_start_cc': t_p,
        SHOT_INDEX_KEY: np.arange(2),
    }
    counts = {k: 2 for k in fetched}
    OPXManager.fill_containers(stub, bayesian_feedback, mgr._map, mgr._stream_roles,
                               fetched, counts, 2, specs=specs,
                               host_data=mgr._host_values)
    feedback_finish(stub, d)
    out = capsys.readouterr().out
    assert 'slip: 0.0 cycles' in out and '***' not in out
    t_int = stub.params.t_opx_integration_len
    np.testing.assert_allclose(d.apd._run_data, demod2volts(fetched['apd'], t_int))
    np.testing.assert_allclose(d.t_pulse_start._run_data, t_sched_cc * 4e-9)
    np.testing.assert_allclose(d.t._run_data, t_sched_cc * 4e-9 + d_s + stub.params.t_img_pulse)
    np.testing.assert_array_equal(d.drive_index._run_data, didx)
    g, _z = feedback_grid_omega(stub.params)
    w = (g - 2 * np.pi * stub.params.frequency_raman_transition) / (np.pi / stub.params.t_raman_pi_pulse)
    f_app = d.omega_raman._run_data / (2 * np.pi)
    assert np.all(np.abs(f_app - (stub.params.frequency_raman_transition
                                  + w[didx] * c.f_Omega_hz)) <= 3.)
    np.testing.assert_allclose(d.probabilities._run_data[:, 0], 1. / m)
    np.testing.assert_allclose(np.sum(d.probabilities._run_data[:, 1:], axis=-1), 1.)
    np.testing.assert_allclose(d.probabilities._run_data[:, 1:],
                               log_weights_to_probabilities(fetched['log_weights'], 32))
    np.testing.assert_array_equal(d.t_raman_pulse._run_data, mgr._host_values['t_raman_pulse'])
    assert list(getattr(d, VALID_MASK_KEY)._run_data) == [1, 1]


def test_apd_volts_and_true_step_conventions():
    p = _params()
    c = _const(p)
    assert apd_volts_to_photon_fraction(p.v_apd_all_up_opx, p.v_apd_all_up_opx,
                                        p.v_apd_all_down_opx) == 1.
    assert apd_volts_to_photon_fraction(p.v_apd_all_down_opx, p.v_apd_all_up_opx,
                                        p.v_apd_all_down_opx) == 0.
    hz, s = true_bloch_step((0., 0., 1.), c.omega_res, c.omega_res,
                            p.t_raman_pi_pulse, p.t_raman_pi_pulse, 0.,
                            c.Omega, 0., 0., 1.)
    assert hz == pytest.approx(-1., abs=1e-12) and s[2] == pytest.approx(-1., abs=1e-12)
    hz, s = true_bloch_step((0., 0., 1.), c.omega_res, c.omega_res,
                            p.t_raman_pi_pulse / 2, p.t_raman_pi_pulse / 2, 0.,
                            c.Omega, 2 * np.pi * 40.e3, 5.e-6, 0.62)
    assert hz == pytest.approx(0., abs=1e-12)
    assert np.hypot(s[0], s[1]) == pytest.approx(0.62, abs=1e-12)
