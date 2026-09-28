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
    open_loop_drive_indices, BLOCK_EDGE_CC,
    remesh_spacing_steps, remesh_lattice_w, remesh_grid_lattice_indices,
    lattice_frame_advances, spacing_frame_advances, remesh_level_tables,
    remesh_axis_tables)
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


# The APD calibration of run 78309 (the OPX placeholder copies before
# 2026-09-27). The QUA-trace tests pin it rather than inherit the params
# file, whose calibration moves: their literals were computed for it --
# v_down_raw = -0.19702 V * 5000 ns / 4096 = -0.24050..., k1 = 1/(raw range)
# / n_split = 11.159 / 2 = 5.5796..., and n_split = 2 sets how many doublings
# the photon fraction gets. test_params_file_* checks the file's own values.
SIGMA_P_78309 = 212.75 / 1336.2
CAL_78309 = dict(v_apd_all_up_opx=-0.12361, v_apd_all_down_opx=-0.19702,
                 std_photon_fraction_opx=SIGMA_P_78309,
                 std_n_photons_per_shot=SIGMA_P_78309 * 1336.0)   # _params' n = 1336

# The model constants of the params files before the 2026-09-27 write-back
# of the joint fit 83203 (C 0.62 -> 0.7746, f_LS 40.61 -> 50.11 kHz, t_pi
# 6.5821 -> 6.4393 us; t_raman_pulse = t_pi/2 as the params file derives
# it). The trace pins only C (the seed-phasor literal "0.62*" is the only
# trace literal among them); the replay round trip pins all three (its
# 1e-6 bound is set by the sincos-table error, which moves with them).
MODEL_PRE_83203 = dict(back_action_coherence=0.62, frequency_lightshift=40610.,
                       t_raman_pi_pulse=6.5821e-6, t_raman_pulse=6.5821e-6 / 2)
TRACE_PIN = dict(CAL_78309,
                 back_action_coherence=MODEL_PRE_83203['back_action_coherence'])


def _trace(seq, xvars, cmap=None, **kw):
    ex = FeedbackOPXExpt(xvars, **{**TRACE_PIN, **kw})
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
    # derived from the ARTIQ calibration's ratio (was the literal 212.75 / 1336.2 of 78309)
    assert p.std_photon_fraction_opx == pytest.approx(base.std_n_photons_per_shot / base.n_photons_per_shot)
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
    # derived from the calibration, not a free parameter (-2.45 = -78.5 nats
    # at the 78309 sigma_p 0.159; it moves with std_photon_fraction_opx).
    # What feedback_constants needs of it: room below 0 for the lazy
    # normalisation (it raises otherwise), and floor - largest decrement
    # still inside QUA fixed, so L stays in [-8, 0] by construction
    assert c.L_floor < -1e-3
    assert c.L_floor - (3 * c.inv_sigma_p_s) ** 2 == pytest.approx(-8 + 2 ** -16)
    assert c.L_floor - (3 * c.inv_sigma_p_s) ** 2 >= -8.
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
    # the photon-fraction split: the smallest n in (1, 2, 4, 8) that puts
    # k1 = 1/(raw range)/n inside QUA fixed (78309: 11.2 -> 2; the file's
    # calibration decides, _split_factor raises past 8)
    assert c.inv_sigma_p < 8 and c.n_split in (1, 2, 4, 8)
    assert abs(c.k1) < 8 and c.k1 == pytest.approx(c.inv_range_raw / c.n_split)
    assert c.n_split == 1 or abs(c.inv_range_raw) / (c.n_split // 2) >= 8
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
    # model constants pinned (MODEL_PRE_83203): with no floors the
    # double-precision vs emulation agreement below is set by the 12-bit
    # sincos table the emulation inherits from the params file (exact trig:
    # ~1e-10), and that error moves with C, f_LS and t_pi (2026-09-27:
    # 4.9e-7 before the 83203 write-back, 1.05e-6 after; the table's design
    # accuracy, <= 2.3e-5 on P0, is the numerics tests' business)
    p = _params(N=8, m=9, span=2.0, offset=0.0, **MODEL_PRE_83203)
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
    # sigma_p pinned at the 78309 value the thresholds below were written for
    # (0.159); the params file's calibration moves (0.18-0.24 on 2026-09-27)
    # and would change how concentrated the null-test posterior gets
    sp20 = 212.75 / 1336.2
    p20 = _params(N=20, m=9, span=2.0, offset=0.0,
                  std_photon_fraction_opx=sp20, std_n_photons_per_shot=sp20 * 1336.0)
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


# ---------------------------------------------------------------------------
# 2026-09-28: exact grid step, the split update, remesh-ready tables
# ---------------------------------------------------------------------------

def _circ(a, b):
    """Circular distance of two angles in turns."""
    d = np.abs(np.mod(np.asarray(a) - np.asarray(b), 1.0))
    return np.minimum(d, 1.0 - d)


def test_grid_step_exact_keeps_tables_run_constant_in_offset_scans():
    """The grid step comes from the construction (2 span/(m-1)). Before
    2026-09-28 it was w_grid[0] - w_grid[1], whose ~1e-13 rounding varied
    with the scanned offset: the axis tables became per-shot arrays and the
    levels structure (the params file's default) refused an offset scan."""
    p = _params(N=6, m=21, span=2.5, offset=0.0)
    c = _const(p)
    offsets = [-2.5, -1.5, 0., 1.5, 2.5]
    n = len(offsets)

    def col(k):
        if k == 'feedback_fractional_initial_offset':
            return np.asarray(offsets, dtype=float)
        return np.full(n, float(np.asarray(getattr(p, k), dtype=float).reshape(-1)[0]))
    T = build_feedback_shot_tables(col, n, c, seeds=np.arange(1, n + 1))
    assert np.all(T.dw == 2 * 2.5 / 20)
    np.testing.assert_allclose(T.w_grid[:, 0] - T.w_grid[:, 1], T.dw, atol=1e-9)
    xv = [('feedback_fractional_initial_offset', offsets)]
    for lev, keys in ((8, ('rot_Am', 'rot_B', 'rot_Cc', 'rot_D', 'rot_cth',
                           'seed_cos_beta', 'seed_sin_beta')),
                      (0, ('axis_h', 'axis_ux', 'axis_uz', 'axis_ux2', 'axis_uxuz'))):
        ex, tables, b, prog, ctx = _trace(bayesian_feedback, xv, N=4, m=21, span=2.5,
                                          t_raman_pulse_n_levels=lev)
        assert not any(k in ctx._shot_arrays for k in keys), lev
        assert 'if_table_80_hz' in ctx._shot_arrays          # the grid itself is per shot
    # the exact seed tables equal the w_grid form to its rounding
    lev_b = np.linspace(0.2, 0.6, 8)
    s0 = level_seed_tables(lev_b, T.w_grid[0], c.phi_LS)
    s1 = level_seed_tables(lev_b, T.w_grid[0], c.phi_LS, dw=float(T.dw[0]))
    for k in ('cb', 'sb', 'cdb', 'sdb', 'beta', 'dbeta'):
        np.testing.assert_allclose(s0[k], s1[k], atol=1e-11)


SPLIT_TRACE = dict(opx_feedback_split_update=1,
                   # provisional values so the structure traces; the real ones
                   # are measured on the QOP simulator (docs/opx/sim_split_timing.py)
                   t_opx_feedback_align_overhead_split=328.e-9,
                   t_opx_feedback_align_overhead_levels_split=344.e-9)

SPLIT_TIMING_ORDER = [
    r"update_frequency\('raman_150'", r"reset_if_phase\('raman_80'\)",
    r"reset_if_phase\('raman_150'\)", r"align\('raman_80', 'raman_150', 'raman_switch'\)",
    r"play\('pass', 'raman_switch', duration=a\d+\[.*timestamp_stream=r\d+\)",
    r"play\('block', 'raman_switch'\)", r"align\('raman_switch', 'imaging_switch'\)",
    r"align\('imaging_switch', 'apd'\)", r"play\('pass', 'imaging_switch', duration=1250\)",
    r"play\('block', 'imaging_switch'\)"]


def test_split_update_trace():
    xv = [('t_raman_pulse_seed', [11, 12, 13])]
    N, m = 4, 5
    # refused until the split structure's sync overhead is given explicitly
    with pytest.raises(ValueError, match='overhead'):
        _const(_params(opx_feedback_split_update=1))
    assert not _const(_params()).split_update
    for lev in (0, 8):
        ex, tables, b, prog, ctx = _trace(bayesian_feedback, xv, N=N, m=m,
                                          t_raman_pulse_n_levels=lev, **SPLIT_TRACE)
        c = _const(ex.params)
        key = ('t_opx_feedback_align_overhead_levels_split' if lev
               else 't_opx_feedback_align_overhead_split')
        assert c.split_update and c.overhead_cc == s_to_cc(SPLIT_TRACE[key])
        # the same streams with the same per-shot counts as the default
        assert ctx._save_counts == {
            'apd': N, 'drive_index': N, 's_z': N, 'log_weights': N * m,
            't_pulse_start_cc': N}
        assert set(b.stream_specs()) == set(fbseq.STREAM_KEYS) | set(RESERVED_STREAMS)
        src = _qua(prog)
        assert not any(x.startswith('with if_(') for x in _stmts(src))
        # ONE for_ over all N pulses (no prologue / epilogue: every interval
        # has the loop structure the one sync overhead is measured for)
        assert src.count('Math.argmax(') == 1
        meas = [mm.start() for mm in re.finditer(r"measure\('acquire'", src)]
        assert len(meas) == 1
        start = meas[0]
        # the timing statements of the pulse, in the pass-3b order
        head = src[src.rfind("update_frequency('raman_80'", 0, start):start]
        pos = 0
        for pat in SPLIT_TIMING_ORDER:
            mm = re.compile(pat).search(head, pos)
            assert mm is not None, pat
            pos = mm.end()
        i_wait = src.index("'raman_switch')", src.index("wait(a", start))
        i_pm = src.index('--0.24050', start)            # the photon-fraction assignment
        i_argmax = src.index('Math.argmax(', start)
        pre, post = src[i_wait:i_pm], src[i_pm:i_argmax]
        # the REVIEWED premise limit: ctx.measure saves the ADC value right
        # after the measure statement, before the hold -- that save is the
        # first read of v, so the thread waits for the result before the
        # "pre-read" half is reached (docstring: EXPECT NO GAIN)
        assert src.index('save(', start) < i_wait
        # before the photon fraction: the rotation, p1_j into its array, the
        # phasors, and no saves
        assert re.search(r"assign\(a\d+\[v\d+\], \(0\.5\*\(1\.0\+v\d+\)\)\)", pre)
        assert 'Util.cond(' not in pre and 'save(' not in pre
        assert ('Cast.unsafe_cast_int(' in pre) == (lev == 0)    # sincos table (continuous)
        # after it: the two clamps and the likelihood's floor only
        assert post.count('Util.cond(') == 3
        assert 'Cast.unsafe_cast_int(' not in post and '(0.5*(1.0+' not in post
        # the saves follow the argmax, as in the default structure
        assert src[i_argmax:].count('save(') >= 3
    # the flat rule traces in the split structure too
    _trace(bayesian_feedback, xv, N=N, m=m, feedback_flat_rule_bool=1, **SPLIT_TRACE)


def test_remesh_lattice_and_spacing_tables_match_direct():
    """Every table a remeshed grid needs is a run constant or a lattice
    table: the co-rotating frame advance depends on the grid's point-0
    frequency and the pulse intervals only (dphi0 = frac(f_0 dt_i)), the
    step and the rotation / seed tables on the spacing level only."""
    p = _params(N=12, m=21, span=2.5, offset=0.0, t_raman_pulse_n_levels=8)
    c = _const(p)
    T = _tables_for(p, [5])
    t_ext = T.t_start_ext_cc[0].astype(float) * CLOCK_NS * 1e-9
    m, n_sp, r = 21, 3, 2
    w0, dw = float(T.w_grid[0, 0]), float(T.dw[0])
    lat_w = remesh_lattice_w(w0, dw, m, n_sp, r)
    assert lat_w.size == 20 * 4 + 1 and lat_w[0] == w0
    np.testing.assert_allclose(lat_w[::4], T.w_grid[0], atol=1e-9)   # the run grid is on it
    f_lat = (c.omega_res + c.Omega * lat_w) / (2 * np.pi)
    A0 = lattice_frame_advances(f_lat, t_ext)
    steps = remesh_spacing_steps(dw, n_sp, r)
    np.testing.assert_allclose(steps, dw / np.array([1., 2., 4.]))
    DD = spacing_frame_advances(steps * c.f_Omega_hz, t_ext)
    assert A0.shape == (lat_w.size, p.N_pulses) and DD.shape == (n_sp, p.N_pulses)
    assert np.all((A0 >= 0.) & (A0 < 1.)) and np.all((DD >= 0.) & (DD < 1.))
    # level 0 with point 0 on lattice point 0: the run's own tables
    assert np.max(_circ(A0[0], T.dphi0[0])) < 1e-9
    assert np.max(_circ(DD[0], T.ddphi[0])) < 1e-9
    # any remeshed grid on the lattice: the direct tables of that grid
    for level, n0 in ((0, 0), (1, 0), (1, 17), (1, 40), (2, 3), (2, 60)):
        idx = remesh_grid_lattice_indices(n0, level, m, n_sp, r)
        d0, dd = corotating_phase_tables(f_lat[idx], t_ext)
        assert np.max(_circ(A0[n0], d0)) < 1e-9, (level, n0)
        assert np.max(_circ(DD[level], dd)) < 1e-9, (level, n0)
    with pytest.raises(ValueError):
        remesh_grid_lattice_indices(70, 2, m, n_sp, r)          # leaves the lattice
    with pytest.raises(ValueError):
        remesh_grid_lattice_indices(0, 3, m, n_sp, r)           # no such level
    # the rotation / seed / axis tables per spacing level are the per-grid
    # builders at dw_l (nothing about where the grid sits)
    a_lev = (T.level_s[0] - c.t_offset_s) / (2 * c.t_pi)
    b_lev = T.level_s[0] / (2 * c.t_pi)
    R = remesh_level_tables(a_lev, b_lev, dw, m, n_sp, r, c.phi_LS)
    AX = remesh_axis_tables(dw, m, n_sp, r)
    assert R['Am'].shape == (n_sp, 8, 2 * m - 1) and R['cb'].shape == (n_sp, 8, m)
    for l, dwl in enumerate(steps):
        mt = level_matrix_tables(a_lev, dwl, m)
        st = level_seed_tables(b_lev, m, c.phi_LS, dw=dwl)
        for k in ('Am', 'B', 'Cc', 'D', 'cth'):
            np.testing.assert_array_equal(R[k][l], mt[k])
        for k in ('cb', 'sb', 'cdb', 'sdb'):
            np.testing.assert_array_equal(R[k][l], st[k])
        for k, v in axis_tables(dwl, m).items():
            np.testing.assert_array_equal(AX[k][l], v)


def test_remesh_grid_posterior_from_lattice_tables_matches_generate_posterior():
    """A grid of spacing level 1 centred away from the run grid, fed only the
    lattice / per-level frame tables, against the double-precision ARTIQ
    posterior on that grid: the tables carry the physics of a data-dependent
    grid with no per-grid trig."""
    p = _params(N=16, m=21, span=2.5, offset=0.0)
    c = _const(p, sincos_lut_bits=0)
    T = _tables_for(p, [7])
    t_ext = T.t_start_ext_cc[0].astype(float) * CLOCK_NS * 1e-9
    m, n_sp, r = 21, 2, 2
    lat_w = remesh_lattice_w(T.w_grid[0, 0], T.dw[0], m, n_sp, r)
    f_lat = (c.omega_res + c.Omega * lat_w) / (2 * np.pi)
    A0 = lattice_frame_advances(f_lat, t_ext)
    DD = spacing_frame_advances(remesh_spacing_steps(T.dw[0], n_sp, r) * c.f_Omega_hz, t_ext)
    n0, level, zj = 13, 1, 6
    w_grid = lat_w[remesh_grid_lattice_indices(n0, level, m, n_sp, r)]
    grid = c.omega_res + c.Omega * w_grid
    rng = np.random.default_rng(7)
    omega_true = c.omega_res + c.Omega * (w_grid[zj] + 0.3 * (w_grid[0] - w_grid[1]))
    measure, _ = _synthetic_measure(p, c, omega_true, T.t_start_s[0], T.d_s[0], rng)
    fb = _artiq_feedback(p)
    fb.omega_guess_list = grid
    fb.omega_sq_list = grid * grid
    fb.reset_feedback_state()
    st = FixedPointState.uniform(m)
    d = 10
    for i in range(p.N_pulses):
        w_d = float(w_grid[d])
        p_meas = measure(i, w_d)
        fb.omega_raman = c.omega_res + c.Omega * w_d
        fb.t_raman_pulse_current = float(T.d_s[0, i])
        fb.t_raman_pulse_ideal_current = float(T.d_s[0, i]) - c.t_offset_s
        fb.generate_posterior(float(fb.N_photons_per_shot) * p_meas, float(T.t_start_s[0, i]),
                              phase_raman_pulse_start=0.0, update_raman_frequency=1,
                              update_rabi_frequency=0, include_photon_noise=1)
        u = posterior_update_fixed_point_emulation(
            st, d, p_meas, T.a[0, i], T.b[0, i], A0[n0, i], DD[level, i], w_grid, c, zidx=zj)
        np.testing.assert_allclose(u['P0'], fb.P0, atol=1e-6)
        assert u['s_z'] == pytest.approx(float(fb.state_z[zj]), abs=1e-9)
        d = int(u['jmax'])


def test_reset_model_is_origin_free_after_a_pole_reset():
    """remesh_plan section 6: once every hypothesis is azimuth-free (spin up
    at shot start, or reset to (0, 0, z) by a pole return) only the pulse
    intervals matter -- moving the time origin changes nothing -- so a remesh
    needs no per-hypothesis phase accumulators and no origin reset. Control:
    with transverse states present, moving the origin mid-shot does change
    the posterior (the test would see a wrong claim)."""
    p = _params(N=14, m=21, span=2.5, offset=0.0)
    c = _const(p)
    T = _tables_for(p, [3])
    t, d_s, grid = T.t_start_s[0], T.d_s[0], T.omega_grid[0]
    rng = np.random.default_rng(3)
    pm = rng.uniform(0.0, 1.0, size=p.N_pulses)      # any readings: a statement about the model
    drives = rng.integers(3, 18, size=p.N_pulses)
    r = 6

    def run(shift=0.0, reset_at=None, z_reset=0.6, shift_from=None, extra=0.0):
        fb = _artiq_feedback(p)
        fb.omega_guess_list = grid
        fb.omega_sq_list = grid * grid
        fb.reset_feedback_state()
        out = []
        for i in range(p.N_pulses):
            if reset_at is not None and i == reset_at:
                fb.state_x[:] = 0.0
                fb.state_y[:] = 0.0
                fb.state_z[:] = z_reset
            ti = float(t[i]) + shift
            if shift_from is not None and i >= shift_from:
                ti += extra
            fb.omega_raman = grid[drives[i]]
            fb.t_raman_pulse_current = float(d_s[i])
            fb.t_raman_pulse_ideal_current = float(d_s[i]) - c.t_offset_s
            fb.generate_posterior(float(fb.N_photons_per_shot) * pm[i], ti,
                                  phase_raman_pulse_start=0.0, update_raman_frequency=1,
                                  update_rabi_frequency=0, include_photon_noise=1)
            out.append(fb.P0.copy())
        return np.array(out)

    base = run()
    np.testing.assert_allclose(run(shift=3.7e-4), base, atol=1e-8)          # any origin
    ref = run(reset_at=r)
    # origin moved to the reset pulse (or anywhere) after the reset: identical
    np.testing.assert_allclose(run(reset_at=r, shift_from=r, extra=-float(t[r])), ref, atol=1e-8)
    np.testing.assert_allclose(run(shift=2.1e-4, reset_at=r, shift_from=r, extra=5.3e-5), ref,
                               atol=1e-8)
    # control: no reset, origin moved mid-shot -> a different posterior
    moved = run(shift_from=r, extra=5.3e-5)
    assert np.max(np.abs(moved[r:] - base[r:])) > 1e-3


def test_corotating_state_is_the_drive_frame_vector():
    """remesh_plan sections 3.1 / 7.1: after the update of pulse i the OPX's
    stored (x, y) of hypothesis j are the lab-frame vector of
    generate_posterior rotated by Rz(-phi_{j,i+1}), phi_{j,i+1} = -omega_j
    t_{i+1} the drive-axis azimuth at the NEXT pulse start (the plan's 3.1
    formula, x' = x cos phi + y sin phi, y' = -x sin phi + y cos phi): they
    already are the components along / across the next pulse's drive axis,
    which the pole-return rotation needs -- X, Y = sum_j P_j x_j,
    sum_j P_j y_j with no rotation on the OPX. The opposite sign fails (the
    test would catch a sign error)."""
    p = _params(N=10, m=21, span=2.5, offset=0.0)
    c = _const(p, sincos_lut_bits=0)
    T = _tables_for(p, [4])
    t_ext = T.t_start_ext_cc[0].astype(float) * CLOCK_NS * 1e-9
    grid, w_grid = T.omega_grid[0], T.w_grid[0]
    fb = _artiq_feedback(p)
    fb.omega_guess_list = grid
    fb.omega_sq_list = grid * grid
    fb.reset_feedback_state()
    st = FixedPointState.uniform(21)
    rng = np.random.default_rng(4)
    d = int(T.d_init[0])
    worst, worst_flipped, transverse = 0.0, 0.0, 0.0
    for i in range(p.N_pulses):
        p_meas = float(rng.uniform(0.1, 0.9))
        fb.omega_raman = grid[d]
        fb.t_raman_pulse_current = float(T.d_s[0, i])
        fb.t_raman_pulse_ideal_current = float(T.d_s[0, i]) - c.t_offset_s
        fb.generate_posterior(float(fb.N_photons_per_shot) * p_meas, float(T.t_start_s[0, i]),
                              phase_raman_pulse_start=0.0, update_raman_frequency=1,
                              update_rabi_frequency=0, include_photon_noise=1)
        posterior_update_fixed_point_emulation(
            st, d, p_meas, T.a[0, i], T.b[0, i], T.dphi0[0, i], T.ddphi[0, i], w_grid, c)
        phi = 2 * np.pi * np.mod(-(grid / (2 * np.pi)) * t_ext[i + 1], 1.0)
        for sgn in (1.0, -1.0):
            xr = np.cos(phi) * fb.state_x + sgn * np.sin(phi) * fb.state_y
            yr = -sgn * np.sin(phi) * fb.state_x + np.cos(phi) * fb.state_y
            err = max(np.max(np.abs(xr - st.x)), np.max(np.abs(yr - st.y)))
            if sgn > 0:
                worst = max(worst, err)
            else:
                worst_flipped = max(worst_flipped, err)
        transverse = max(transverse, float(np.max(np.hypot(st.x, st.y))))
        np.testing.assert_allclose(st.z, fb.state_z, atol=1e-9)
        d = int(rng.integers(0, 21))
    assert transverse > 0.1                    # there is a transverse state to check
    assert worst < 1e-8
    assert worst_flipped > 1e-2


# ---------------------------------------------------------------------------
# 2026-09-28: the remesh with pole return (bayesian_feedback_remesh)
# ---------------------------------------------------------------------------

from kexp.experiments.opx_sequences.feedback import (          # noqa: E402
    bayesian_feedback_remesh, pole_level_durations_cc, remesh_pulse_starts_cc,
    STREAM_KEYS_REMESH, HOST_KEYS_REMESH)
from kexp.analysis.feedback_opx import (                       # noqa: E402
    remesh_trigger_fixed_point_emulation, remesh_apply_fixed_point_emulation)

# provisional values so the structures trace -- the real ones are measured on
# the QOP simulator (docs/opx/sim_remesh_timing.py) -- DISTINCT per key, so a
# key mix-up shows as a slip
RM = dict(opx_remesh_enable=1,
          t_opx_feedback_align_overhead_remesh=328.e-9,
          t_opx_feedback_align_overhead_levels_remesh=344.e-9,
          t_opx_feedback_align_overhead_split_remesh=332.e-9,
          t_opx_feedback_align_overhead_levels_split_remesh=348.e-9,
          t_opx_feedback_compute_budget_remesh=12.e-6,
          t_opx_feedback_compute_budget_levels_remesh=11.e-6,
          t_opx_feedback_compute_budget_split_remesh=12.004e-6,
          t_opx_feedback_compute_budget_levels_split_remesh=11.004e-6,
          t_opx_remesh_hold=2.e-6)


def _rm_tables(T, s=0):
    return dict(lat_w=T.lat_w[s], lat_adv=T.lat_adv[s], fine_adv=T.fine_adv[s],
                pole_a=T.pole_a, pole_b=T.pole_b, n_res=int(T.n_res[s]),
                wq=T.w_grid[s] / 4.0)


def _remesh_detector(p, c, T, s, detune, seed, noise=True, level_map=None):
    """A synthetic APD for remesh shot s: the true Bloch vector stepped by
    the reset model. The pole pulse (announced by the emulation's on_pole)
    plays its level's duration -- or level_map(level)'s, to play a wrong
    one -- and every later pulse starts (d_pole - d_drawn) + t_opx_remesh_hold
    later, as the OPX does. Returns (measure, on_pole, rec): rec['hz'] the
    true z seen per pulse, rec['t'] the pulse starts played (s)."""
    rng = np.random.default_rng(seed)
    omega_true = c.omega_res + c.Omega * detune
    fb = _artiq_feedback(p)
    pole_d = T.pole_d_cc.astype(float) * CLOCK_NS * 1e-9
    hold = c.remesh_hold_cc * CLOCK_NS * 1e-9
    st = dict(s=(0.0, 0.0, 1.0), shift=0.0, pole=None)
    rec = dict(hz=[], t=[])

    def on_pole(i, k):
        st['pole'] = (i, k if level_map is None else int(level_map(k)))

    def measure(i, w_d):
        d_drawn = float(T.d_s[s, i])
        d = d_drawn
        t = float(T.t_start_s[s, i]) + st['shift']
        pole_here = st['pole'] is not None and st['pole'][0] == i
        if pole_here:
            d = float(pole_d[st['pole'][1]])
        omega_ctrl = c.omega_res + c.Omega * float(w_d)
        hz, st['s'] = true_bloch_step(st['s'], omega_ctrl, omega_true, d - c.t_offset_s, d, t,
                                      c.Omega, 2 * np.pi * p.frequency_lightshift,
                                      c.t_img_s, c.C)
        rec['hz'].append(hz)
        rec['t'].append(t)
        if pole_here:
            st['shift'] += (d - d_drawn) + hold
        p1 = float(fb.expected_photon_fraction(hz))
        return p1 + (rng.normal(0.0, c.sigma_p) if noise else 0.0)
    return measure, on_pole, rec


def _oracle_remesh_shot(p, c, T, measure, follow=None, on_pole=None):
    """The remesh in double precision, independent of the fixed-point code:
    generate_posterior (phase 0) for every update, exact exp / atan2 for the
    trigger and the pole angle -- from the lab-frame state rotated into the
    next pulse's drive frame -- and the same grid / interpolation / reset
    rules (feedback_reinit.py's, with the OPX's lattice snap and L-linear
    interpolation). The posterior uses the DRAWN schedule: after the pole
    pulse the OPX starts every pulse later by a constant, which the reset to
    the z axis makes irrelevant (the replay tests use the actual starts)."""
    m, R, N = c.m, c.remesh_ratio, c.N
    n_pole = c.n_pole
    t_ext = T.t_start_ext_cc[0].astype(float) * CLOCK_NS * 1e-9
    fb = _artiq_feedback(p)
    grid = T.omega_grid[0].copy()
    fb.omega_guess_list = grid
    fb.omega_sq_list = grid * grid
    fb.reset_feedback_state()
    pole_d_s = T.pole_d_cc.astype(float) * CLOCK_NS * 1e-9
    n0, pole_now, fired, pole_k, sz_lat = 0, False, False, 0, 0.0
    rec = dict(pulse=-1, n0=0, k=-1, s0=0.0)
    d = int(T.d_init[0])
    rows = []
    for i in range(N):
        if follow is not None:
            # the recorded decisions, driven at the recorded applied frequency
            d = int(follow['drives'][i])
            pole_now = (i == follow['remesh_pulse'])
            if pole_now:
                pole_k = int(follow['pole_level'])
        w_cur = (grid - c.omega_res) / c.Omega
        if pole_now and on_pole is not None:
            on_pole(i, pole_k)
        p_meas = measure(i, float(w_cur[d]))
        dur = pole_d_s[pole_k] if pole_now else float(T.d_s[0, i])
        fb.omega_raman = grid[d] if follow is None else float(follow['omega'][i])
        fb.t_raman_pulse_current = dur
        fb.t_raman_pulse_ideal_current = dur - c.t_offset_s
        fb.generate_posterior(float(fb.N_photons_per_shot) * p_meas, float(T.t_start_s[0, i]),
                              phase_raman_pulse_start=0.0, update_raman_frequency=1,
                              update_rabi_frequency=0, include_photon_noise=1)
        jmax = int(np.argmax(fb.P0))
        if pole_now:
            pmu = float(np.clip(p_meas, -2.0, 3.0))
            s0 = float(np.clip(2 * pmu - 1, -1, 1)) if c.reinit_state_source == 0 else sz_lat
            n0 = int(np.clip(jmax * R - (m - 1) // 2, 0, (m - 1) * (R - 1)))
            if follow is not None:
                n0 = int(follow['remesh_n0'])
            lp = np.log(np.maximum(fb.P0, 1e-300))
            pos = n0 + np.arange(m)
            k, f = pos // R, (pos % R) / R
            k1 = np.minimum(k + 1, m - 1)
            Ln = lp[k] + f * (lp[k1] - lp[k])
            Pn = np.exp(Ln - Ln.max())
            fb.P0[:] = Pn / Pn.sum()
            fb.state_x[:] = 0.0
            fb.state_y[:] = 0.0
            fb.state_z[:] = s0
            grid = c.omega_res + c.Omega * T.lat_w[0, n0 + np.arange(m)]
            fb.omega_guess_list = grid
            fb.omega_sq_list = grid * grid
            jmax = int(np.argmax(fb.P0))
            rec = dict(pulse=i, n0=n0, k=pole_k, s0=s0)
            pole_now = False
        rows.append(dict(P0=fb.P0.copy(), d=d, grid=grid.copy()))
        if follow is not None:
            if i == follow['remesh_pulse'] - 1:
                # the model S_z at the recorded level (state source 1)
                phi = 2 * np.pi * np.mod(-(grid / (2 * np.pi)) * t_ext[i + 1], 1.0)
                a = -np.sin(phi) * fb.state_x + np.cos(phi) * fb.state_y
                b = fb.state_z.copy()
                kf = int(follow['pole_level'])
                cp, sp = np.cos(2 * np.pi * T.pole_a[kf]), np.sin(2 * np.pi * T.pole_a[kf])
                sz_lat = (float(b[jmax] * cp - a[jmax] * sp) if c.reinit_method == 0
                          else float(np.sum(fb.P0 * (b * cp - a * sp))))
            continue
        if not fired:
            P = fb.P0
            w = (grid - c.omega_res) / c.Omega
            if c.reinit_trigger_mode == 0:
                mean = np.sum(P * w)
                ok = np.sqrt(max(np.sum(P * w * w) - mean * mean, 0.0)) < c.reinit_std_thr
            else:
                outside = np.abs(np.arange(m) - jmax) > c.reinit_margin_excl
                pout = np.max(P[outside]) if outside.any() else 0.0
                ok = (np.log(P[jmax] / pout) if pout > 0 else 100.0) >= c.reinit_margin_s * c.scale
            forced = c.reinit_force_pulse > 0 and i >= c.reinit_force_pulse - 1
            window = c.reinit_min_pulse - 1 <= i <= N - 3
            phi = 2 * np.pi * np.mod(-(grid / (2 * np.pi)) * t_ext[i + 1], 1.0)
            a = -np.sin(phi) * fb.state_x + np.cos(phi) * fb.state_y
            b = fb.state_z.copy()
            if c.reinit_method == 0:
                th = -np.arctan2(a[jmax], b[jmax]) / (2 * np.pi)
            else:
                th = 0.5 * np.arctan2(-2 * np.sum(P * a * b),
                                      np.sum(P * b * b) - np.sum(P * a * a)) / (2 * np.pi)
            th = th + 0.5 if th < 0 else th
            th = th - 0.5 if th >= 0.5 else th
            k = int(np.clip(np.floor(2 * (n_pole - 1) * (th + 1 / (4 * (n_pole - 1)))),
                            0, n_pole - 1))
            cp, sp = np.cos(2 * np.pi * T.pole_a[k]), np.sin(2 * np.pi * T.pole_a[k])
            szp = (b[jmax] * cp - a[jmax] * sp if c.reinit_method == 0
                   else float(np.sum(P * (b * cp - a * sp))))
            if window and (ok or forced):
                pole_now, fired, pole_k, sz_lat = True, True, k, float(szp)
        d = jmax
    return rows, rec


@pytest.mark.parametrize('cfg', [
    dict(t_raman_pulse_n_levels=0, feedback_reinit_trigger_mode=0, feedback_reinit_method=1,
         feedback_reinit_state_source=0, seed=5, detune=0.37),
    dict(t_raman_pulse_n_levels=0, feedback_reinit_trigger_mode=1, feedback_reinit_method=0,
         feedback_reinit_state_source=1, seed=8, detune=-0.8),
    dict(t_raman_pulse_n_levels=8, feedback_reinit_trigger_mode=0, feedback_reinit_method=1,
         feedback_reinit_state_source=0, seed=11, detune=1.1),
    # fires on its metric (no forcing)
    dict(t_raman_pulse_n_levels=8, feedback_reinit_trigger_mode=0, feedback_reinit_method=0,
         feedback_reinit_state_source=1, feedback_reinit_force_pulse=0,
         feedback_reinit_std_threshold_Omega=1.2, seed=13, detune=0.45),
])
def test_remesh_emulation_matches_double_precision_oracle(cfg):
    cfg = dict(cfg)
    seed, detune = cfg.pop('seed'), cfg.pop('detune')
    p = _params(N=16, m=21, span=2.5, offset=0.0, **{**RM, **cfg})
    c = _const(p, sincos_lut_bits=0, exp_lut_bits=0)       # exact: compare the algorithm
    assert c.remesh and c.remesh_ratio == 4 and c.n_pole == 17
    T = _tables_for(p, [seed], sincos_lut_bits=0, exp_lut_bits=0)
    m1, op1, _r1 = _remesh_detector(p, c, T, 0, detune, seed)
    em = run_shot_fixed_point_emulation(
        T.w_grid[0], int(T.zidx[0]), T.a[0], T.b[0], T.dphi0[0], T.ddphi[0], c, m1,
        d_init=int(T.d_init[0]), remesh=_rm_tables(T), on_pole=op1)
    m2, op2, _r2 = _remesh_detector(p, c, T, 0, detune, seed)
    rows, rec = _oracle_remesh_shot(p, c, T, m2, on_pole=op2)
    assert em['remesh_pulse'] >= 0, 'the trigger never fired'
    if c.reinit_force_pulse == 0:
        assert em['remesh_pulse'] >= c.reinit_min_pulse
    assert (em['remesh_pulse'], em['remesh_n0'], em['remesh_pole_level']) == \
        (rec['pulse'], rec['n0'], rec['k'])
    assert em['remesh_s0'] == pytest.approx(rec['s0'], abs=1e-6)
    for i, r in enumerate(rows):
        assert em['d_used'][i] == r['d'], i
        np.testing.assert_allclose(em['P0'][i], r['P0'], atol=1e-6, err_msg=f"pulse {i}")
        np.testing.assert_allclose(c.omega_res + c.Omega * em['grid'][i], r['grid'], rtol=0,
                                   atol=1e-3)
    # the pole pulse played its level's rotation; the fine grid is dw/4 wide and on the lattice
    p_idx = em['remesh_pulse']
    assert em['a_used'][p_idx] == T.pole_a[em['remesh_pole_level']]
    g = em['grid'][p_idx]
    np.testing.assert_allclose(-np.diff(g), T.dw[0] / 4, atol=1e-12)
    np.testing.assert_allclose(g, T.lat_w[0, em['remesh_n0'] + np.arange(21)])


def test_remesh_frame_advance_by_integer_powers_matches_the_lattice():
    """The QUA seeds build the fine grid's point-0 frame advance as
    (run point 0) x (run step)^u x (fine step)^v, n0 = R u + v, by
    branch-free square-and-multiply (power_bits in the sequence); the same
    statements in numpy reproduce the lattice table for every n0 and pulse."""
    p = _params(N=12, m=21, span=2.5, offset=0.0, **RM)
    c = _const(p)
    T = _tables_for(p, [3])
    R, lg = c.remesh_ratio, c.remesh_log2
    n0_max = 20 * (R - 1)
    nbu = max(1, int(n0_max >> lg).bit_length())

    def power(acc, base, e, nbits):
        acc, base = complex(*acc), complex(*base)
        for bit in range(nbits):
            t = acc * base
            if (e >> bit) & 1:
                acc = t
            if bit < nbits - 1:
                base = base * base
        return acc
    worst = 0.0
    for i in range(p.N_pulses):
        p0 = (np.cos(2 * np.pi * T.dphi0[0, i]), np.sin(2 * np.pi * T.dphi0[0, i]))
        pdd = (np.cos(2 * np.pi * T.ddphi[0, i]), np.sin(2 * np.pi * T.ddphi[0, i]))
        pe = (np.cos(2 * np.pi * T.fine_adv[0, i]), np.sin(2 * np.pi * T.fine_adv[0, i]))
        for n0 in range(n0_max + 1):
            u, v = n0 >> lg, n0 - ((n0 >> lg) << lg)
            acc = power(p0, pdd, u, nbu)
            acc = power((acc.real, acc.imag), pe, v, lg)
            want = np.exp(2j * np.pi * T.lat_adv[0, n0, i])
            worst = max(worst, abs(acc - want))
    assert worst < 1e-9


def test_remesh_sequence_trace_and_refusals():
    xv = [('feedback_fractional_initial_offset', [-2., 0., 2.])]
    N, m = 8, 21
    for lev in (0, 8):
        for split in (0, 1):
            ex, tables, b, prog, ctx = _trace(bayesian_feedback_remesh, xv, N=N, m=m, span=2.5,
                                              t_raman_pulse_n_levels=lev,
                                              opx_feedback_split_update=split, **RM)
            c = _const(ex.params)
            key = ('t_opx_feedback_compute_budget' + ('_levels' if lev else '')
                   + ('_split' if split else '') + '_remesh')
            assert c.budget_key == key and c.budget_cc == s_to_cc(RM[key])
            assert c.overhead_key == key.replace('compute_budget', 'align_overhead')
            assert ctx._save_counts == {
                'apd': N, 'drive_index': N, 's_z': N, 'log_weights': N * m,
                't_pulse_start_cc': N, 'remesh_pulse': 1, 'remesh_n0': 1,
                'remesh_pole_level': 1, 'remesh_s0': 1, 'remesh_trigger': 1}
            assert set(b.stream_specs()) == (set(fbseq.STREAM_KEYS) | set(STREAM_KEYS_REMESH)
                                             | set(RESERVED_STREAMS))
            assert set(HOST_KEYS_REMESH) <= set(ctx._host_data_values)
            assert {'remesh_trigger_metric', 's_z_on_grid'} <= set(ctx._host_data_values)
            # the offset scan keeps the (spacing, level, k) tables run constants
            for k in ('rot_Am', 'seed_cos_beta', 'axis_h', 'axis_ux2'):
                assert k not in ctx._shot_arrays
            src = _qua(prog)
            st = _stmts(src)
            # the only if_: the remesh, classical statements only (one loop in
            # both structures, so one if_)
            starts = [n for n, s in enumerate(st) if s.startswith('with if_(')]
            assert len(starts) == 1
            lines = src.splitlines()
            for n, ln in enumerate(lines):
                if ln.strip().startswith('with if_('):
                    ind = len(ln) - len(ln.lstrip())
                    body = []
                    for ln2 in lines[n + 1:]:
                        if ln2.strip() and len(ln2) - len(ln2.lstrip()) <= ind:
                            break
                        body.append(ln2.strip())
                    for bad in ('play(', 'wait(', 'align(', 'measure(', 'update_frequency(',
                                'reset_if_phase(', 'save(', 'frame_rotation'):
                        assert not any(x.startswith(bad) for x in body), bad
                    assert any('Math.argmax(' in x for x in body)
            # the pulse's duration: the pole level's on the pole pulse; its hold
            # is the drawn step's plus pole_now * t_opx_remesh_hold (500 cycles)
            assert re.search(r"assign\(v\d+, Util\.cond\(\(v\d+==1\),a\d+\[v\d+\],a\d+\[", src)
            assert re.search(r"play\('pass', 'raman_switch', duration=v\d+, timestamp_stream", src)
            assert re.search(r"wait\(\(a\d+\[.*\]\+\(v\d+\*500\)\), 'raman_switch'\)", src)
            assert 'Math.atan2_2pi(' in src
            # the pole level by the exact bit shift (17 levels: 2 (n-1) = 2^5),
            # and no division outside Math.inv's documented domain
            assert re.search(r"Cast\.unsafe_cast_int\(\(v\d+\+0\.015625\)\)>>23", src)
            assert 'Math.div(' not in src and 'mul_int_by_fixed' not in src
            assert 'Math.inv((v' in src
    # the bit shift is floor(2 (n-1) x) on the 4.28 grid, for every level count
    rng = np.random.default_rng(0)
    for n_pole in (3, 5, 9, 17, 33, 257):
        q = int(round(np.log2(2 * (n_pole - 1))))
        x = np.round((rng.uniform(0, 0.5, 5000) + 1 / (4 * (n_pole - 1))) * 2 ** 28)
        np.testing.assert_array_equal(x.astype(np.int64) >> (28 - q),
                                      np.floor(2 * (n_pole - 1) * x / 2 ** 28).astype(np.int64))
    # refusals
    with pytest.raises(RuntimeError, match='bayesian_feedback_remesh'):
        _trace(bayesian_feedback, xv, N=N, m=m, span=2.5, **RM)
    with pytest.raises(RuntimeError, match='bayesian_feedback'):
        _trace(bayesian_feedback_remesh, xv, N=N, m=m, span=2.5)
    for bad, match in (
            (dict(opx_remesh_ratio=3), 'opx_remesh_ratio'),
            (dict(opx_remesh_pole_levels=2), 'opx_remesh_pole_levels'),
            (dict(opx_remesh_pole_levels=16), 'opx_remesh_pole_levels'),
            (dict(feedback_reinit_pole_enabled=0), 'feedback_reinit_pole_enabled'),
            (dict(feedback_reinit_center_mode=1), 'feedback_reinit_center_mode'),
            (dict(feedback_reinit_temper_beta=0.5), 'feedback_reinit_temper_beta'),
            (dict(feedback_flat_rule_bool=1), 'flat rule'),
            (dict(N=2), 'N_pulses >= 3'),
            (dict(feedback_reinit_method=2), '0 or 1'),
            (dict(N=4, feedback_reinit_min_pulse=3), 'trigger window'),
            (dict(feedback_reinit_trigger_mode=1, feedback_reinit_margin_excl=10),
             'feedback_reinit_margin_excl'),
            (dict(feedback_reinit_trigger_mode=1, feedback_reinit_margin_nats=300.),
             'feedback_reinit_margin_nats'),
            (dict(feedback_reinit_span_Omega=0.5), 'feedback_reinit_span_Omega'),
            (dict(t_opx_remesh_hold=None), 't_opx_remesh_hold'),
            (dict(t_opx_feedback_compute_budget_remesh=None),
             't_opx_feedback_compute_budget_remesh'),
            (dict(t_opx_feedback_align_overhead_remesh=None), 'overhead')):
        kw = {k: v for k, v in {**RM, **bad}.items() if v is not None}
        n_p = kw.pop('N', 16)
        with pytest.raises(ValueError, match=match):
            _const(_params(N=n_p, span=2.5, **kw))
    # consistent keys are accepted
    _const(_params(N=16, span=2.5, feedback_reinit_span_Omega=2.5 / 4, **RM))
    with pytest.raises(ValueError, match='closed-loop'):
        fbseq.make_feedback_sequence(open_loop=True, remesh=True)
    # a switch offset under 4 cycles: pole level 0 is played at the 4-cycle
    # minimum, and its model rotation is that of the played 16 ns
    c0 = _const(_params(N=8, m=21, span=2.5, t_raman_pulse_offset_opx=0.0, **RM))
    d0, a0, b0 = pole_level_durations_cc(c0)
    assert d0[0] == 4 and np.all(np.diff(d0) >= 0)
    assert a0[0] == pytest.approx(16e-9 / (2 * c0.t_pi)) and b0[0] == a0[0]


def _remesh_finish_stub(n_shots, N, m, **kw):
    stub = FeedbackOPXExpt([('t_raman_pulse_seed', np.arange(1, n_shots + 1))], N=N, m=m,
                           span=2.5, offset=0.0, **RM, **kw)
    data = DataVault(expt=stub)
    for key, spec in bayesian_feedback_remesh.resolve_measurements(stub.params).items():
        setattr(data, key, data.add_data_container(spec.shape, spec.np_dtype))
    for key, spec in bayesian_feedback_remesh.resolve_host_data(stub.params).items():
        setattr(data, key, data.add_data_container(spec.shape, np.float64))
    for key, spec in RESERVED_STREAMS.items():
        setattr(data, key, data.add_data_container(spec.shape, np.int64))
    setattr(data, VALID_MASK_KEY, data.add_data_container((1,), np.int32))
    data.init()
    stub.data = data
    return stub, data


def test_remesh_finish_hook(capsys):
    n_shots, N, m = 2, 8, 21
    stub, d = _remesh_finish_stub(n_shots, N, m)
    p = stub.params
    c = _const(p)
    T = _tables_for(p, [1, 2], terms=_fake_terms())
    rng = np.random.default_rng(1)
    didx = rng.integers(0, m, (n_shots, N)).astype(np.int64)
    d.apd._run_data[:] = -0.16
    d.drive_index._run_data[:] = didx
    d.if_table_hz._run_data[:] = T.if_hz.astype(float)
    d.if_lattice_hz._run_data[:] = T.if_lat_hz.astype(float)
    d.omega_raman_mesh._run_data[:] = np.repeat(T.omega_grid[:, None, :], N + 1, axis=1)
    d.log_weights._run_data[:] = -rng.uniform(0, 2, (n_shots, N, m))
    d_s = T.d_s.copy()
    d.t_raman_pulse._run_data[:] = d_s               # the DRAWN durations, as the host ships them
    rp, kpl = np.array([3, -1]), np.array([5, -1])
    pole_d_cc, _a, _b = pole_level_durations_cc(c)
    d_app_cc = T.d_cc.copy()
    d_app_cc[0, 3] = pole_d_cc[5]
    # the OPX's pulse starts: the pole step is ARTIQ's formula with the pole
    # duration plus t_opx_remesh_hold, so the later pulses start later
    t_cc = remesh_pulse_starts_cc(d_app_cc, c, rp)
    shift = t_cc - T.t_start_cc
    assert np.all(shift[0, :4] == 0) and np.all(shift[1] == 0)
    assert np.all(shift[0, 4:] == pole_d_cc[5] - T.d_cc[0, 3] + c.remesh_hold_cc)
    d.t_pulse_start_cc._run_data[:] = 500 + t_cc
    d.remesh_pulse._run_data[:] = rp.reshape(d.remesh_pulse._run_data.shape)
    d.remesh_n0._run_data[:] = np.array([17, 0]).reshape(d.remesh_n0._run_data.shape)
    d.remesh_pole_level._run_data[:] = kpl.reshape(d.remesh_pole_level._run_data.shape)
    d.remesh_trigger._run_data[:] = np.array([0.01, 0.0]).reshape(d.remesh_trigger._run_data.shape)
    getattr(d, VALID_MASK_KEY)._run_data[:] = 1
    feedback_finish(stub, d)
    out = capsys.readouterr().out
    assert 'slip: 0.0 cycles' in out and '***' not in out     # held to the pole-step schedule
    om = d.omega_raman._run_data / (2 * np.pi)
    R = c.remesh_ratio
    for s, (pp, n0) in enumerate(((3, 17), (-1, 0))):
        lat = np.where((np.arange(N) > pp) & (pp >= 0), n0 + didx[s], didx[s] * R)
        f_exp = 2.0 * (T.if_lat_hz[s, lat, 1] - T.if_lat_hz[s, lat, 0])
        np.testing.assert_allclose(om[s], f_exp, rtol=0, atol=1e-6)
    np.testing.assert_allclose(om[1], 2.0 * (T.if_hz[1, didx[1], 1] - T.if_hz[1, didx[1], 0]),
                               rtol=0, atol=1e-6)
    mesh = d.omega_raman_mesh._run_data
    np.testing.assert_allclose(mesh[0, :4], np.repeat(T.omega_grid[:1], 4, axis=0))
    fine = c.omega_res + c.Omega * T.lat_w[0, 17 + np.arange(m)]
    np.testing.assert_allclose(mesh[0, 4:], np.repeat(fine[None], N + 1 - 4, axis=0), atol=1e-3)
    np.testing.assert_allclose(mesh[1], np.repeat(T.omega_grid[1:2], N + 1, axis=0))
    tr = d.t_raman_pulse._run_data
    assert tr[0, 3] == pytest.approx(pole_d_cc[5] * 4e-9)
    np.testing.assert_allclose(np.delete(tr[0], 3), np.delete(d_s[0], 3))
    np.testing.assert_allclose(tr[1], d_s[1])
    np.testing.assert_allclose(d.t._run_data, d.t_pulse_start._run_data + tr + p.t_img_pulse)
    # the trigger value in physical units: var(w/4) = 0.01 -> std 0.4 Omega
    tm = d.remesh_trigger_metric._run_data.reshape(-1)
    assert tm[0] == pytest.approx(0.4) and np.isnan(tm[1])
    # s_z_on_grid: resonance (run index 10 -> lattice 40) is off shot 0's fine
    # grid (lattice 17..37) from the pole pulse's own save on
    on = d.s_z_on_grid._run_data
    np.testing.assert_array_equal(on[0], [1, 1, 1, 0, 0, 0, 0, 0])
    np.testing.assert_array_equal(on[1], np.ones(N))
    assert '5 s_z value(s) in 1 shot(s)' in out
    # idempotent: a second pass gives the same containers and still no slip
    keys = ('t_raman_pulse', 't', 't_pulse_start', 'omega_raman', 'omega_raman_mesh',
            'probabilities', 'remesh_trigger_metric', 's_z_on_grid')
    snap = {k: np.array(getattr(d, k)._run_data, copy=True) for k in keys}
    feedback_finish(stub, d)
    out2 = capsys.readouterr().out
    assert 'slip: 0.0 cycles' in out2 and '***' not in out2
    for k in keys:
        np.testing.assert_array_equal(getattr(d, k)._run_data, snap[k], err_msg=k)
    # a slip: named with the overhead / budget keys this structure used and
    # the step where the slip changed
    d.t_pulse_start_cc._run_data[0, 5:] += 3
    feedback_finish(stub, d)
    out3 = capsys.readouterr().out
    assert '***' in out3 and '4->5: 1' in out3
    assert 't_opx_feedback_align_overhead_remesh = 328 ns' in out3 and '(12000 ns)' in out3


def _synthetic_remesh_run(p, offsets, seeds, detune, perturb=None, invalid=(), noise=True):
    """A remesh run file as the experiment side produces it: per shot the
    OPX loop (the emulation, closed loop, trigger / pole pulse / remesh)
    on a synthetic detector that plays the pole pulse and shifts the later
    pulse starts as the OPX does; its streams and host data put into
    DataVault containers as the manager fills them; the real finish hook run
    on them. perturb(s, out) -> a follow dict or None: the recording then
    plays those decisions (as hardware rounding could make a decision the
    emulation would not). invalid: shots the OPX did not run (streams
    INT_MISSING / NaN, valid flag 0, as the manager fills them). Returns
    (ad, T, runs, recs): ad an atomdata-like object with the run's params
    (offset scanned) and the containers after finish, runs the emulation's
    per-shot outputs (the OPX's own values), recs the detector records."""
    n = len(offsets)
    c = _const(p)
    N, m = c.N, c.m
    stub = FeedbackOPXExpt([('feedback_fractional_initial_offset', np.asarray(offsets))],
                           **{k: getattr(p, k) for k in ('N_pulses', 'feedback_grid_size')},
                           **{'span': p.feedback_guess_span_Omega})
    stub.params = p
    stub.p = p
    data = DataVault(expt=stub)
    meas_specs = bayesian_feedback_remesh.resolve_measurements(p)
    for key, spec in meas_specs.items():
        setattr(data, key, data.add_data_container(spec.shape, spec.np_dtype))
    for key, spec in bayesian_feedback_remesh.resolve_host_data(p).items():
        setattr(data, key, data.add_data_container(spec.shape, np.float64))
    for key, spec in RESERVED_STREAMS.items():
        setattr(data, key, data.add_data_container(spec.shape, np.int64))
    setattr(data, VALID_MASK_KEY, data.add_data_container((1,), np.int32))
    data.init()
    stub.data = data

    def col(k):
        if k == 'feedback_fractional_initial_offset':
            return np.asarray(offsets, dtype=float)
        return np.full(n, float(np.asarray(getattr(p, k), dtype=float).reshape(-1)[0]))
    T = build_feedback_shot_tables(col, n, c, seeds=np.asarray(seeds), terms=_fake_terms())

    def shot(s, follow=None):
        meas, on_pole, rec = _remesh_detector(p, c, T, s, detune, 1000 + seeds[s], noise=noise)
        out = run_shot_fixed_point_emulation(
            T.w_grid[s], int(T.zidx[s]), T.a[s], T.b[s], T.dphi0[s], T.ddphi[s], c, meas,
            d_init=int(T.d_init[s]), remesh=_rm_tables(T, s), follow=follow, on_pole=on_pole)
        return out, rec
    runs, recs = [], []
    for s in range(n):
        out, rec = shot(s)
        fol = perturb(s, out) if perturb is not None else None
        if fol is not None:
            out, rec = shot(s, fol)
        runs.append(out)
        recs.append(rec)
    rp = np.array([o['remesh_pulse'] for o in runs])
    kpl = np.array([o['remesh_pole_level'] for o in runs])
    d_app_cc = T.d_cc.copy()
    for s in np.flatnonzero(rp >= 0):
        d_app_cc[s, rp[s]] = T.pole_d_cc[kpl[s]]
    t_cc = remesh_pulse_starts_cc(d_app_cc, c, rp)
    # the pulse starts the detector's physics used ARE the sequence's schedule
    for s in range(n):
        np.testing.assert_allclose(np.asarray(recs[s]['t']), t_cc[s] * CLOCK_NS * 1e-9,
                                   rtol=0, atol=1e-15)
    d = data
    shp = lambda dc, v: np.asarray(v).reshape(dc._run_data.shape)
    d.apd._run_data[:] = np.array([p.v_apd_all_down_opx + o['p_meas']
                                   * (p.v_apd_all_up_opx - p.v_apd_all_down_opx) for o in runs])
    d.drive_index._run_data[:] = np.array([o['d_used'] for o in runs])
    d.s_z._run_data[:] = np.array([o['s_z'] for o in runs])
    d.log_weights._run_data[:] = np.array([o['L'] for o in runs])
    d.t_pulse_start_cc._run_data[:] = 700 + np.arange(n)[:, None] * 400000 + t_cc
    for key in ('remesh_pulse', 'remesh_n0', 'remesh_pole_level', 'remesh_s0', 'remesh_trigger'):
        getattr(d, key)._run_data[:] = shp(getattr(d, key), [o[key] for o in runs])
    d.t_raman_pulse._run_data[:] = T.d_s
    d.t_raman_pulse_seed._run_data[:] = shp(d.t_raman_pulse_seed, T.seed.astype(float))
    d.omega_raman_mesh._run_data[:] = np.repeat(T.omega_grid[:, None, :], N + 1, axis=1)
    d.if_table_hz._run_data[:] = T.if_hz.astype(float)
    d.if_lattice_hz._run_data[:] = T.if_lat_hz.astype(float)
    getattr(d, VALID_MASK_KEY)._run_data[:] = 1
    for s in invalid:
        for key in meas_specs:
            arr = getattr(d, key)._run_data
            arr[s] = INT_MISSING if np.issubdtype(arr.dtype, np.integer) else np.nan
        getattr(d, VALID_MASK_KEY)._run_data[s] = 0
    feedback_finish(stub, d)
    keys = (list(meas_specs) + list(bayesian_feedback_remesh.resolve_host_data(p))
            + [VALID_MASK_KEY])
    arrays = SimpleNamespace(**{k: np.asarray(getattr(d, k)._run_data).copy() for k in keys})
    q = copy.copy(p)
    q.feedback_fractional_initial_offset = np.asarray(offsets, dtype=float)
    ad = SimpleNamespace(p=q, data=arrays, run_info=SimpleNamespace(run_id=4343),
                         xvarnames=['feedback_fractional_initial_offset'], xvardims=[n])
    return ad, T, runs, recs


@pytest.mark.parametrize('lev, split', [(8, 0), (0, 0), (8, 1)])
def test_remesh_replay_matches_the_experiment_side(lev, split, capsys):
    """The replay of a remesh run file (streams + the finish hook's
    containers) against what produced it. The file comes from the float64
    emulation, so this checks the replay's plumbing and engines, not the
    QUA semantics (2^-28 rounding, Math.argmax's tie rule). The fixed-point
    replay reproduces the file's posterior, s_z, grids, decisions and
    trigger values to float64 rounding, in both control modes, with the
    actual pulse starts (after the pole pulse later than the drawn schedule)
    or the recomputed schedule. The double-precision replay agrees in P0 to
    < 1e-4 (measured 3-9e-6: the <= 3 Hz integer-Hz drive offset) and its
    argmax differs only at exact ties of the recorded posterior. Every shot
    fires, forced at pulse 6 (unforced firing: the oracle test's last case
    and test_remesh_replay_unforced_triggers)."""
    p = _params(N=16, m=21, span=2.5, offset=0.0, t_raman_pulse_n_levels=lev,
                opx_feedback_split_update=split, **RM)
    c = _const(p)
    offsets = [-2.0, 0.5, 1.5, 0.0]
    seeds = [21, 22, 23, 24]
    ad, T, runs, recs = _synthetic_remesh_run(p, offsets, seeds, detune=0.6)
    capsys.readouterr()
    fired = np.array([o['remesh_pulse'] for o in runs])
    assert np.all(fired >= 0)                      # force 6: every shot fires by pulse 6
    fr = FeedbackOPXReplay(ad)
    assert fr.remesh and fr.remesh_ratio == 4
    # compatibility: the replay's applied frequencies = the finish hook's omega_raman
    np.testing.assert_allclose(fr.omega_applied_rr, ad.data.omega_raman, rtol=0, atol=1e-6)
    P_rec = ad.data.probabilities[:, 1:]
    mesh_rec = ad.data.omega_raman_mesh[:, 1:]
    rec_metric = ad.data.remesh_trigger_metric.reshape(-1)
    for mode in ('measured', 'recomputed'):
        for actual in (True, False):
            res = fr.emulate_fixed_point(True).replay_measured(control_omega_source=mode,
                                                                use_actual_timestamps=actual)
            # identical up to the pole pulse; after it the file's tables came
            # from the drawn starts and the replay's from the later actual /
            # scheduled ones -- the same intervals, but the phase tables are
            # formed from absolute times (f t ~ 4e4 turns), so they round
            # differently at ~1e-11 turns (an error of the shift itself would
            # be O(1): 0.48 turns per cycle)
            for s in range(4):
                pp = int(fired[s])
                np.testing.assert_allclose(res.P0_rr[s, :pp + 1], P_rec[s, :pp + 1], atol=1e-15,
                                           err_msg=f"{mode} {actual} {s}")
            np.testing.assert_allclose(res.P0_rr, P_rec, atol=1e-11, err_msg=f"{mode} {actual}")
            np.testing.assert_allclose(res.s_z_rr, ad.data.s_z, atol=1e-11)
            np.testing.assert_allclose(res.mesh_rr, mesh_rec, rtol=0, atol=1e-3)
            rm = res.remesh
            assert rm['n_agree'] == rm['n_valid'] == 4, (mode, actual, rm)
            np.testing.assert_array_equal(rm['played']['pulse'], fired)
            assert rm['s0_max_abs_diff'] < 1e-12 and rm['n_s0_compared'] == 4
            np.testing.assert_allclose(rm['recorded']['trigger_metric'], rec_metric, rtol=1e-12)
            np.testing.assert_allclose(rm['played']['trigger_metric'], rec_metric, rtol=1e-9)
            np.testing.assert_allclose(rm['replay']['trigger_metric'], rec_metric, rtol=1e-9)
            np.testing.assert_array_equal(rm['replay']['s_z_on_grid'], ad.data.s_z_on_grid)
            np.testing.assert_array_equal(rm['recorded']['s_z_on_grid'], ad.data.s_z_on_grid)
            np.testing.assert_allclose(res.slip_rr, 0.0, atol=1e-15)
            np.testing.assert_allclose(res.t_raman_pulse_rr, ad.data.t_raman_pulse, atol=1e-15)
            rep = fr.compare_with_opx(res, verbose=False)
            assert rep['max_abs_dP'] < 1e-11 and rep['argmax_agreement_fraction'] == 1.0
            assert rep['n_argmax_ties_disagree'] == 0
            assert rep['remesh_decisions_agree'] == 4
    # the schedule the OPX kept: the drawn one up to the pole pulse, later by
    # (d_pole - d_drawn) + t_opx_remesh_hold after it
    t_sched = fr.scheduled_starts_rr()
    for s in range(4):
        pp = int(fired[s])
        shift = (int(T.pole_d_cc[runs[s]['remesh_pole_level']]) - int(T.d_cc[s, pp])
                 + c.remesh_hold_cc) * CLOCK_NS * 1e-9
        np.testing.assert_allclose(t_sched[s, :pp + 1], T.t_start_s[s, :pp + 1], atol=1e-15)
        np.testing.assert_allclose(t_sched[s, pp + 1:], T.t_start_s[s, pp + 1:] + shift,
                                   atol=1e-15)
    # the double-precision replay following the recording ('measured': the
    # recorded decisions, driven at the applied integer-Hz frequency, <= 3 Hz
    # from the grid point): the same trajectory to 1e-4, the replay's own
    # remesh decisions and trigger values = the recorded ones, and the only
    # argmax flips are EXACT ties of the recorded posterior (pulse 0 from the
    # pole: hypotheses d +- k are symmetric; the OPX takes the first index,
    # the double posterior's 1e-5 differences can take the other)
    res2 = fr.emulate_fixed_point(False).replay_measured(control_omega_source='measured')
    rep2 = fr.compare_with_opx(res2, verbose=False)
    assert rep2['max_abs_dP'] < 1e-4, rep2['summary']
    assert rep2['argmax_agreement_fraction'] == 1.0, rep2['summary']
    assert rep2['remesh_decisions_agree'] == 4, rep2['summary']
    np.testing.assert_allclose(res2.remesh['played']['trigger_metric'], rec_metric, rtol=1e-4)
    np.testing.assert_allclose(res2.s_z_rr, ad.data.s_z, atol=1e-4)
    np.testing.assert_array_equal(res2.remesh['replay']['s_z_on_grid'], ad.data.s_z_on_grid)
    flips = np.argwhere(res2.P0_rr.argmax(-1) != P_rec.argmax(-1))
    for s, i in flips:
        top = np.sort(P_rec[s, i])[-2:]
        assert top[1] - top[0] < 1e-9, (s, i, top)
    # its next drive is the next recorded applied drive (<= 3 Hz), except
    # after an exact tie
    far = np.abs(res2.omega_recomputed_rr[:, :-1] - fr.omega_applied_rr[:, 1:]) > 2 * np.pi * 3.5
    for s, i in np.argwhere(far):
        top = np.sort(P_rec[s, i])[-2:]
        assert top[1] - top[0] < 1e-9, (s, i, top)
    # the double-precision closed loop on its own ('recomputed') reproduces the
    # recorded drives up to the first exact tie, where it may break the other
    # way and then (the readings belonging to other drives) diverge
    res4 = fr.emulate_fixed_point(False).replay_measured(control_omega_source='recomputed')
    for s in range(4):
        diff = np.flatnonzero(np.abs(res4.omega_control_rr[s] - fr.omega_applied_rr[s])
                              > 2 * np.pi * 10.0)
        if diff.size:
            i = int(diff[0])
            assert i >= 1
            top = np.sort(P_rec[s, i - 1])[-2:]
            assert top[1] - top[0] < 1e-9, (s, i, top)
    # the double-precision engine against the test oracle, both following
    # shot 0's recorded decisions at the recorded applied frequency; the
    # oracle uses the DRAWN schedule, the replay the actual (later after the
    # pole pulse) starts -- equal because the remesh resets to the z axis
    rec = iter(runs[0]['p_meas'])
    follow = dict(drives=ad.data.drive_index[0], remesh_pulse=int(runs[0]['remesh_pulse']),
                  remesh_n0=int(runs[0]['remesh_n0']), pole_level=int(runs[0]['remesh_pole_level']),
                  omega=fr.omega_applied_rr[0])
    rows, orc = _oracle_remesh_shot(p, c, _one_shot(T, 0), lambda i, w: next(rec), follow=follow)
    assert orc['s0'] == pytest.approx(float(res2.remesh['replay']['s0'][0]), abs=1e-12)
    for i, r in enumerate(rows):
        np.testing.assert_allclose(res2.P0_rr[0, i], r['P0'], atol=1e-9, err_msg=f"pulse {i}")
        np.testing.assert_allclose(res2.mesh_rr[0, i], r['grid'], rtol=0, atol=1e-6)
    # what-ifs: a model edit moves both engines alike and never changes what
    # was played; a structural edit is refused
    base_f = fr.emulate_fixed_point(True).replay_measured().P0_rr
    base_d = fr.emulate_fixed_point(False).replay_measured().P0_rr
    for key, val in (('t_raman_pi_pulse', p.t_raman_pi_pulse * 1.01),
                     ('t_raman_pulse_offset_opx', p.t_raman_pulse_offset_opx + 8e-9),
                     ('back_action_coherence', 0.5)):
        old = getattr(fr.p, key)
        setattr(fr.p, key, val)
        rf = fr.emulate_fixed_point(True).replay_measured()
        rd = fr.emulate_fixed_point(False).replay_measured()
        for r_ in (rf, rd):
            np.testing.assert_allclose(r_.t_raman_pulse_rr, ad.data.t_raman_pulse, atol=1e-15)
            np.testing.assert_allclose(r_.omega_control_rr, fr.omega_applied_rr, rtol=0,
                                       atol=2 * np.pi * 3.5)
        moved = float(np.nanmax(np.abs(rf.P0_rr - base_f)))
        assert moved > 1e-4, key
        assert float(np.nanmax(np.abs((rf.P0_rr - base_f) - (rd.P0_rr - base_d)))) \
            < 0.05 * moved + 2e-5, key
        setattr(fr.p, key, old)
    for key, val in (('opx_remesh_ratio', 2), ('opx_remesh_pole_levels', 33),
                     ('opx_remesh_enable', 0), ('t_opx_remesh_hold', 4e-6)):
        old = getattr(fr.p, key)
        setattr(fr.p, key, val)
        for fp in (True, False):
            with pytest.raises(ValueError, match='was edited'):
                fr.emulate_fixed_point(fp).replay_measured()
        setattr(fr.p, key, old)
    with pytest.raises(ValueError, match='override'):
        fr.simulate_counterfactual(control_omega_source='override',
                                   omega_control_rr=ad.data.omega_raman)
    with pytest.raises(ValueError, match='return_full_state'):
        fr.replay_measured(return_full_state=True)
    with pytest.raises(NotImplementedError):
        fr.simulate_feedback_run_apd()


def _one_shot(T, s):
    """Shot s of a FeedbackShotTables as a one-shot view (the oracle reads row 0)."""
    view = copy.copy(T)
    for name in ('d_s', 'd_cc', 't_start_s', 't_start_ext_cc', 'omega_grid', 'w_grid',
                 'd_init', 'lat_w', 'a', 'b', 'dphi0', 'ddphi', 'zidx', 'n_res'):
        setattr(view, name, np.asarray(getattr(T, name))[s:s + 1])
    return view


UNFORCED = [(mode, method, source) for mode in (0, 1) for method in (0, 1) for source in (0, 1)]


@pytest.mark.parametrize('mode, method, source', UNFORCED)
def test_remesh_replay_unforced_triggers(mode, method, source, capsys):
    """No forcing: the shots fire on their trigger metric (posterior std or
    alias margin) or not at all, and every branch of the decision rules --
    trigger mode, pole-angle method, s0 source; continuous and level
    durations -- runs through FeedbackOPXReplay in both engines against the
    recording. (In margin mode not every shot fires: with continuous
    durations the posterior keeps an alias beyond +-1 step within ~0.3 nats
    of the MAP for 10 pulses on most of these shots.)"""
    lev = 8 if (mode + method + source) % 2 else 0
    thr = (dict(feedback_reinit_std_threshold_Omega=1.2) if mode == 0
           else dict(feedback_reinit_margin_nats=0.25))
    p = _params(N=12, m=21, span=2.5, offset=0.0, t_raman_pulse_n_levels=lev,
                feedback_reinit_force_pulse=0, feedback_reinit_trigger_mode=mode,
                feedback_reinit_method=method, feedback_reinit_state_source=source,
                **thr, **RM)
    c = _const(p)
    ad, T, runs, recs = _synthetic_remesh_run(p, [-1.0, 0.5, 1.5, 0.0], [41, 42, 43, 44],
                                              detune=0.4)
    capsys.readouterr()
    fired = np.array([o['remesh_pulse'] for o in runs])
    on = fired >= 0
    assert np.sum(on) >= 2, fired
    assert np.all(fired[on] >= c.reinit_min_pulse), fired      # on the metric, no forcing
    rec_metric = ad.data.remesh_trigger_metric.reshape(-1)
    assert np.all(np.isnan(rec_metric[~on]))
    if mode == 0:
        assert np.all(rec_metric[on] < 1.2)
    else:
        assert np.all(rec_metric[on] >= 0.25)
    fr = FeedbackOPXReplay(ad)
    P_rec = ad.data.probabilities[:, 1:]
    for how in ('measured', 'recomputed'):
        res = fr.emulate_fixed_point(True).replay_measured(control_omega_source=how)
        np.testing.assert_allclose(res.P0_rr, P_rec, atol=1e-11, err_msg=how)
        np.testing.assert_allclose(res.s_z_rr, ad.data.s_z, atol=1e-11)
        rm = res.remesh
        np.testing.assert_array_equal(rm['replay']['pulse'], fired)
        assert rm['n_agree'] == 4
        assert rm['n_s0_compared'] == int(np.sum(on)) and rm['s0_max_abs_diff'] < 1e-11
        np.testing.assert_allclose(rm['replay']['trigger_metric'], rec_metric, rtol=1e-9)
    res2 = fr.emulate_fixed_point(False).replay_measured()
    rep2 = fr.compare_with_opx(res2, verbose=False)
    assert rep2['max_abs_dP'] < 1e-4, rep2['summary']
    np.testing.assert_allclose(res2.remesh['played']['trigger_metric'], rec_metric,
                               rtol=1e-3, atol=1e-4)


def test_remesh_replay_follows_perturbed_decisions(capsys):
    """A recording with decisions the emulation would not have made (as a
    QUA rounding or tie flip could): the pole level +1 (shot 0), the fine
    grid moved one lattice step (shot 1), the pole pulse one pulse later
    (shot 2), shot 3 unchanged. Following the recording, the fixed-point
    replay reproduces it exactly and plays the recorded decisions; the
    replay's own decisions are reported and differ; recomputing, the
    replay makes its own and differs from the recording."""
    p = _params(N=16, m=21, span=2.5, offset=0.0, t_raman_pulse_n_levels=8, **RM)

    def perturb(s, out):
        k, n0, pp = out['remesh_pole_level'], out['remesh_n0'], out['remesh_pulse']
        assert pp >= 0
        if s == 0:
            return dict(drives=None, remesh_pulse=pp, remesh_n0=n0, pole_level=(k + 1) % 17)
        if s == 1:
            return dict(drives=None, remesh_pulse=pp, remesh_n0=n0 - 1 if n0 > 0 else n0 + 1,
                        pole_level=k)
        if s == 2:
            return dict(drives=None, remesh_pulse=pp + 1, remesh_n0=n0, pole_level=k)
        return None
    ad, T, runs, recs = _synthetic_remesh_run(p, [0.0, 0.5, -0.5, 1.0], [51, 52, 53, 54],
                                              detune=0.3, perturb=perturb)
    capsys.readouterr()
    fr = FeedbackOPXReplay(ad)
    P_rec = ad.data.probabilities[:, 1:]
    res = fr.emulate_fixed_point(True).replay_measured()          # following
    np.testing.assert_allclose(res.P0_rr, P_rec, atol=1e-12)
    np.testing.assert_allclose(res.s_z_rr, ad.data.s_z, atol=1e-12)
    rm = res.remesh
    for k in ('pulse', 'n0', 'pole_level'):
        np.testing.assert_array_equal(rm['played'][k], rm['recorded'][k])
    np.testing.assert_array_equal(rm['decisions_agree_r'], [False, False, False, True])
    assert rm['replay']['pole_level'][0] != rm['recorded']['pole_level'][0]
    assert rm['replay']['n0'][1] != rm['recorded']['n0'][1]
    assert rm['replay']['pulse'][2] == rm['recorded']['pulse'][2] - 1
    res_r = fr.emulate_fixed_point(True).replay_measured(control_omega_source='recomputed')
    for s in range(3):
        assert np.nanmax(np.abs(res_r.P0_rr[s] - P_rec[s])) > 1e-3, s
    np.testing.assert_allclose(res_r.P0_rr[3], P_rec[3], atol=1e-12)
    res2 = fr.emulate_fixed_point(False).replay_measured()
    for k in ('pulse', 'n0', 'pole_level'):
        np.testing.assert_array_equal(res2.remesh['played'][k], res2.remesh['recorded'][k])
    assert fr.compare_with_opx(res2, verbose=False)['max_abs_dP'] < 1e-4


def test_remesh_replay_excludes_impossible_decisions_and_invalid_shots(capsys):
    """A shot the OPX did not run (streams INT_MISSING / NaN, valid 0) is
    NaN in the finish hook's containers and skipped by the replay; a valid
    shot whose recorded decisions the sequence cannot have made (level -1
    on a fired shot -- -1 is also INT_MISSING --, a fine grid off the
    lattice, a pole pulse with no pulse after it) is excluded from the
    replay with the count and reason printed, never indexed."""
    p = _params(N=12, m=21, span=2.5, offset=0.0, t_raman_pulse_n_levels=8, **RM)
    ad, T, runs, recs = _synthetic_remesh_run(p, [0.0, 0.5, -0.5, 1.0, 1.5],
                                              [61, 62, 63, 64, 65], detune=0.3, invalid=(4,))
    capsys.readouterr()
    for key in ('omega_raman', 't_pulse_start', 't', 's_z_on_grid'):
        assert np.all(np.isnan(getattr(ad.data, key)[4])), key
    assert np.isnan(ad.data.remesh_trigger_metric.reshape(-1)[4])
    assert np.all(np.isfinite(ad.data.omega_raman[:4]))
    ad.data.remesh_pole_level.reshape(-1)[0] = -1
    ad.data.remesh_n0.reshape(-1)[1] = 99
    ad.data.remesh_pulse.reshape(-1)[2] = 11
    fr = FeedbackOPXReplay(ad)
    out = capsys.readouterr().out
    assert out.count('excluded from the replay') == 3
    assert fr.valid_r.tolist() == [False, False, False, True, False]
    assert np.all(np.isnan(fr.omega_applied_rr[[0, 1, 2, 4]]))
    for fp in (True, False):
        res = fr.emulate_fixed_point(fp).replay_measured()
        assert res.remesh['n_valid'] == 1 and res.remesh['n_agree'] == 1
        assert np.all(np.isnan(res.P0_rr[[0, 1, 2, 4]]))
        np.testing.assert_allclose(res.P0_rr[3], ad.data.probabilities[3, 1:],
                                   atol=1e-12 if fp else 1e-4)
        rep = fr.compare_with_opx(res, verbose=False)
        assert rep['remesh_n_excluded'] == 3 and 'EXCLUDED' in rep['summary']


def test_pole_pulse_brings_the_true_state_to_the_predicted_s_z():
    """The physics of the pole rule, shared by every implementation (so a
    sign or frame error common to all would pass the consistency tests):
    noise-free readings, resonance on a grid point, method 0 (the MAP
    hypothesis) and state source 1 (s0 = the model's S_z at the played
    level). When the MAP is the true hypothesis, the TRUE Bloch vector after
    the pole pulse has the predicted S_z; the mirrored level misses."""
    p = _params(N=12, m=21, span=2.5, offset=0.0, feedback_reinit_method=0,
                feedback_reinit_state_source=1, **RM)
    c = _const(p, sincos_lut_bits=0, exp_lut_bits=0)
    n_ok, worst, miss = 0, 0.0, 0.0
    for seed in range(20):
        T = _tables_for(p, [seed], sincos_lut_bits=0, exp_lut_bits=0)
        j_true = 7 + seed % 7
        detune = float(T.w_grid[0, j_true])

        def run(level_map=None):
            meas, on_pole, rec = _remesh_detector(p, c, T, 0, detune, seed, noise=False,
                                                  level_map=level_map)
            out = run_shot_fixed_point_emulation(
                T.w_grid[0], int(T.zidx[0]), T.a[0], T.b[0], T.dphi0[0], T.ddphi[0], c, meas,
                d_init=int(T.d_init[0]), remesh=_rm_tables(T), on_pole=on_pole)
            return out, rec
        out, rec = run()
        pp = int(out['remesh_pulse'])
        if pp < 0 or int(out['d_used'][pp]) != j_true:
            continue                                # the MAP is not the truth at the trigger
        n_ok += 1
        worst = max(worst, abs(rec['hz'][pp] - out['remesh_s0']))
        k = int(out['remesh_pole_level'])
        _out2, rec2 = run(level_map=lambda kk, _km=c.n_pole - 1 - k: _km)
        miss = max(miss, abs(rec2['hz'][pp] - out['remesh_s0']))
    assert n_ok >= 10, n_ok
    assert worst < 1e-6, worst
    assert miss > 0.1, miss


def test_remesh_replay_handles_a_shot_that_never_fires():
    """No forcing and a threshold the posterior cannot reach in the one-pulse
    trigger window (N = 4: only pulse 1): no pole pulse anywhere; the replay
    agrees and keeps the run grid throughout."""
    p = _params(N=4, m=21, span=2.5, offset=0.0, t_raman_pulse_n_levels=8,
                feedback_reinit_std_threshold_Omega=0.01, feedback_reinit_force_pulse=0, **RM)
    ad, T, runs, recs = _synthetic_remesh_run(p, [0.0, 1.0], [31, 32], detune=0.3)
    assert all(o['remesh_pulse'] == -1 for o in runs)
    np.testing.assert_array_equal(ad.data.remesh_pole_level.reshape(-1), [-1, -1])
    assert np.all(np.isnan(ad.data.remesh_trigger_metric))
    np.testing.assert_array_equal(ad.data.s_z_on_grid, 1.0)
    fr = FeedbackOPXReplay(ad)
    for fp in (True, False):
        res = fr.emulate_fixed_point(fp).replay_measured()
        assert res.remesh['n_agree'] == 2
        np.testing.assert_allclose(res.mesh_rr, np.repeat(T.omega_grid[:, None, :], 4, axis=1),
                                   rtol=0, atol=1e-3)
        np.testing.assert_allclose(fr.scheduled_starts_rr(), T.t_start_s, atol=1e-15)
        assert fr.compare_with_opx(res, verbose=False)['max_abs_dP'] < (1e-12 if fp else 1e-4)
