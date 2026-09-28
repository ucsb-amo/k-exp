"""Replay and emulation of the OPX Bayesian feedback loop ("reset" model).

Usage::

    from kexp import atomdata
    from kexp.analysis import FeedbackOPXReplay

    ad = atomdata(run_id, roi_id='auto')
    fr = FeedbackOPXReplay(ad)              # actual pulse timestamps by default
    res = fr.replay_measured()              # double-precision posterior, phase 0
    fr.compare_with_opx(res)                # how far the OPX's own posterior is
    res_fp = fr.emulate_fixed_point(True).replay_measured()   # the OPX numerics

    fr.p.frequency_lightshift = 45.e3       # what-if on a model constant
    res_cf = fr.simulate_counterfactual()
    synth = fr.simulate_feedback_run_apd(detuning_offset_Omega=0.37, seed=1)

Two engines, one physics:

* ``replay_measured`` / ``simulate_counterfactual`` step the double-precision
  ARTIQ posterior (kexp.base.feedback.Feedback.generate_posterior) with
  ``phase_raman_pulse_start = 0`` and the pulse start times the OPX recorded
  (or scheduled), feeding it ``k = N_photons * p_meas`` so the existing
  likelihood in photon units is reused exactly (sigma/N = sigma_p). The
  drive of pulse i is, by default (``control_omega_source='measured'``), the
  EXACT frequency the atoms saw: 2 * (if_150[d] - if_80[d]) from the
  streamed drive index and the run's integer IF table (if_table_hz).
* ``posterior_update_fixed_point_emulation`` is the algorithm the OPX runs
  (kexp/experiments/opx_sequences/feedback.py: grid-index drive with the
  axis tables, co-rotating azimuth frame, L/s log weights with the lazy
  floor, sincos table, argmax control law or the flat rule when
  feedback_flat_rule_bool = 1), in float64 with its unit scalings -- NOT
  bit-exact fixed point (QUA fixed rounds every product to 2^-28; that
  rounding is not modelled and shows up as ~1 % near-tie argmax
  disagreements, which is why compare_with_opx expects >= 99 % agreement).
  ``emulate_fixed_point(True)`` switches the replay to it; on synthetic data
  produced by the same function it round-trips exactly.

Remesh runs (bayesian_feedback_remesh): both engines replay the pole pulse
and the grid change. control_omega_source='measured' follows the recorded
decisions (drives, pole pulse, its level, the fine grid) and recomputes
everything continuous, reporting the replay's own decisions next to the
recorded ones (result.remesh; compare_with_opx adds the agreement);
'recomputed' decides everything itself. What the OPX PLAYED (durations,
grid and lattice frequencies, pole-level durations, the schedule with the
pole step's shift) is rebuilt once, with the sequence's
build_feedback_shot_tables, from the saved seeds and the run's OWN params;
the model (fr.p: resonance, t_raman_pi_pulse, the *_opx calibration, noise,
light shift, coherence, the decision rules) is applied to it alike in both
engines, and edits of structural keys are refused
(STRUCTURAL_KEYS_REMESH). Recorded decisions the sequence cannot have made
exclude their shot, with the count and reason printed. The fixed-point
replay reproduces a run the emulation produced to float64 rounding; the
double-precision replay agrees to the applied-drive offset (<= 3 Hz), and
a closed loop it recomputes itself can break an exact tie of the posterior
(pulse 0 from the pole) the other way and then diverge.

Everything is in units of the run's ExptParams (the OPX calibration:
v_apd_all_up_opx / v_apd_all_down_opx in OPX volts, std_photon_fraction_opx,
t_raman_pulse_offset_opx; the flags feedback_flat_rule_bool,
feedback_log_weight_scale, opx_sincos_lut_bits, t_raman_pulse_n_levels are
read from ad.p and mirrored exactly). Shapes follow FeedbackReplayResult:
(N_repeat = n_shots, N_step = N_pulses).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import numpy as np

from kexp.base.feedback import Feedback, feedback_grid_omega
from kexp.analysis.feedback import FeedbackReplayResult
from kexp.experiments.opx_sequences.feedback import (
    feedback_constants, FeedbackConstants, log_weights_to_probabilities,
    timestamps_cc_to_seconds, scheduled_pulse_starts_s, exp_lut_emulation,
    sincos_lut_emulation, axis_tables, corotating_phase_tables,
    feedback_step_gaps_cc, nearest_grid_index, applied_frequency_hz,
    P_MEAS_CLAMP, LOG_WEIGHT_SCALE, build_feedback_shot_tables,
    lattice_frame_advances, spacing_frame_advances)
from kexp.control.opx.units import CLOCK_NS

__all__ = [
    'FeedbackOPXReplay', 'FeedbackOPXReplayResult',
    'FixedPointState', 'FixedPointRangeError',
    'posterior_update_fixed_point_emulation',
    'run_shot_fixed_point_emulation', 'true_bloch_step',
    'remesh_trigger_fixed_point_emulation', 'remesh_apply_fixed_point_emulation',
    'apd_volts_to_photon_fraction', 'ARGMAX_AGREEMENT_EXPECTED',
]

# fraction of pulses on which the double-precision replay's argmax is
# expected to agree with the OPX's: QUA's 2^-28 rounding flips ~1 % of
# near-tie decisions (brainstorm synth_runs.py E1, quantisation)
ARGMAX_AGREEMENT_EXPECTED = 0.99


# ---------------------------------------------------------------------------
# the fixed-point algorithm, emulated in float64
# ---------------------------------------------------------------------------

def _cos2pi(x):
    return np.cos(2.0 * np.pi * np.asarray(x, dtype=float))


def _sin2pi(x):
    return np.sin(2.0 * np.pi * np.asarray(x, dtype=float))


@dataclass
class FixedPointState:
    """The per-shot OPX state: Bloch vectors (co-rotating azimuth frame of
    each hypothesis), L/s log-weights per grid point and M, the previous
    pulse's maximum that the lazy normalisation subtracts.
    ``uniform(m)``: spin up, uniform prior (L = 0, M = 0)."""
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    L: np.ndarray
    M: float = 0.0

    @classmethod
    def uniform(cls, m):
        m = int(m)
        return cls(np.zeros(m), np.zeros(m), np.ones(m), np.zeros(m), 0.0)


def apd_volts_to_photon_fraction(v, v_up, v_down):
    """OPX APD volts -> photon fraction p_meas = (v - v_down)/(v_up - v_down)."""
    return (np.asarray(v, dtype=float) - float(v_down)) / (float(v_up) - float(v_down))


class FixedPointRangeError(ValueError):
    """An intermediate of the emulated update left the QUA fixed range."""


def _check_range(check, name, value):
    if not check:
        return
    v = np.asarray(value, dtype=float)
    # QUA fixed is [-8, 8): -8.0 itself is representable
    if np.any(~np.isfinite(v)) or np.any(v < -8.0) or np.any(v >= 8.0):
        raise FixedPointRangeError(
            f"fixed-point emulation: {name} = {np.min(v):g} .. {np.max(v):g} "
            f"leaves the QUA fixed range [-8, 8)")


def posterior_update_fixed_point_emulation(state: FixedPointState, d, p_meas,
                                           a_i, b_i, dphi0_i, ddphi_i, w_grid, c,
                                           zidx=None, check_ranges=True
                                           ) -> Dict[str, object]:
    """One pulse of the OPX update, float64, in place.

    state: FixedPointState (mutated). d: the drive of this pulse as a GRID
    INDEX (the OPX only ever drives grid points). p_meas: measured photon
    fraction. a_i = (d_i - t_off)/(2 t_pi), b_i = d_i/(2 t_pi) (turns per
    unit), dphi0_i / ddphi_i the co-rotating frame advance seeds (turns,
    corotating_phase_tables). w_grid (m,) Omega units, descending. c: a
    FeedbackConstants (phi_LS, C, mid_m_half, inv_sigma_p_s, L_floor,
    scale, k_exp, flat_rule, flat_threshold4, exp_lut_bits, sincos_lut_bits,
    n_levels). Returns a dict: P0 (normalised, from the max-normalised L as
    the host derives it), L (the saved L/s, max-normalised), jmax, flat,
    w_mean, w_next, d_next (the next drive index), n_floored, s_z (when
    zidx is given), p_meas_used, M.

    Statement order and every scaling follow the QUA text in
    kexp/experiments/opx_sequences/feedback.py, including the sincos
    interpolation table (c.sincos_lut_bits > 0, continuous durations) and
    the flat-rule exp table; only the 2^-28 rounding of QUA fixed is
    absent. check_ranges=True (default) raises FixedPointRangeError if any
    intermediate leaves [-8, 8) -- the float64 emulation doubles as the
    range checker for the QUA program.
    """
    w_grid = np.asarray(w_grid, dtype=float)
    m = w_grid.size
    if isinstance(d, (bool, np.bool_)) or not isinstance(d, (int, np.integer)):
        raise TypeError(f"the OPX drive is a grid index (int), got {d!r}")
    d = int(d)
    if not 0 <= d < m:
        raise ValueError(f"drive index {d} outside the grid [0, {m})")
    x, y, z, L = state.x, state.y, state.z, state.L
    M_prev = float(state.M)
    ck = bool(check_ranges)
    C = float(c.C)

    pm = float(np.clip(p_meas, P_MEAS_CLAMP[0], P_MEAS_CLAMP[1]))
    wq = w_grid * 0.25
    dw = float(w_grid[0] - w_grid[1])
    dwq, ndwq = -dw / 4.0, dw / 4.0
    _check_range(ck, 'w_grid', w_grid)

    # axis geometry of hypothesis j from the k = j - d tables
    ax = axis_tables(dw, m)
    kk = np.arange(m) + (m - 1 - d)
    h, ux, uz = ax['h'][kk], ax['ux'][kk], ax['uz'][kk]
    ux2, uxuz = ax['ux2'][kk], ax['uxuz'][kk]

    # per-pulse seeds: the drive-dependent z-rotation parts, the host's
    # frame advances, C folded into the seed phasor
    b4 = 4.0 * float(b_i)
    a4 = -4.0 * float(a_i)
    _check_range(ck, 'b4', b4)
    _check_range(ck, 'a4', a4)
    dwd = dwq * d
    beta = b4 * dwd + float(c.phi_LS)
    dbeta = b4 * ndwq
    _check_range(ck, 'beta', beta)
    _check_range(ck, 'dbeta', dbeta)
    cb, sb = float(_cos2pi(beta)), float(_sin2pi(beta))
    cdb, sdb = float(_cos2pi(dbeta)), float(_sin2pi(dbeta))
    c0, s0 = float(_cos2pi(dphi0_i)), float(_sin2pi(dphi0_i))
    cd, sd = float(_cos2pi(ddphi_i)), float(_sin2pi(ddphi_i))
    cg0 = C * (c0 * cb - s0 * sb)
    sg0 = C * (s0 * cb + c0 * sb)
    cdg = cd * cdb - sd * sdb
    sdg = sd * cdb + cd * sdb
    cg = np.empty(m); sg = np.empty(m)
    for j in range(m):
        cg[j], sg[j] = cg0, sg0
        cg0, sg0 = cg0 * cdg - sg0 * sdg, sg0 * cdg + cg0 * sdg

    th = a4 * h
    _check_range(ck, 'theta (turns)', th)
    sbits = int(getattr(c, 'sincos_lut_bits', 0) or 0)
    if sbits and int(getattr(c, 'n_levels', 0) or 0) == 0:
        cth, sth = sincos_lut_emulation(th, sbits)
    else:
        cth, sth = _cos2pi(th), _sin2pi(th)
    omc = 1.0 - cth
    A1 = omc * ux2
    Cc = omc * uxuz
    Am = cth + A1
    if int(getattr(c, 'n_levels', 0) or 0) > 0:
        E = (1.0 + cth) - Am          # the tabled form
    else:
        E = 1.0 - A1
    B = sth * uz
    D = sth * ux
    t1 = Am * x - B * y
    _check_range(ck, 'x2 partial', t1)
    x2 = t1 + Cc * z
    t2 = B * x + cth * y
    _check_range(ck, 'y2 partial', t2)
    y2 = t2 - D * z
    t3 = Cc * x + D * y
    _check_range(ck, 'z2 partial', t3)
    z2 = t3 + E * z
    _check_range(ck, 'rotated state', np.concatenate([x2, y2, z2]))
    x[:] = cg * x2 - sg * y2
    y[:] = sg * x2 + cg * y2
    z[:] = z2

    # likelihood, lazy max-normalisation with the floor, one multiply
    if float(c.mid_m_half) != 0.0:
        p1 = 0.5 * (1.0 + z2) + float(c.mid_m_half) * (1.0 - z2 * z2)
    else:
        p1 = 0.5 * (1.0 + z2)
    q = (pm - p1) * float(c.inv_sigma_p_s)
    _check_range(ck, 'q', q)
    _check_range(ck, 'q*q', q * q)
    t = L - M_prev
    _check_range(ck, 'L - M_prev', t)
    floor = float(c.L_floor)
    floored = t < floor
    n_floored = int(np.sum(floored))
    L[:] = np.where(floored, floor, t) - q * q
    _check_range(ck, 'L (updated)', L)

    jmax = int(np.argmax(L))
    M = float(L[jmax])
    Ln = L - M                                # what the saves emit
    _check_range(ck, 'L - M', Ln)
    s = int(c.scale)
    P = np.exp(s * Ln)                        # the host's P0: exact from L
    S = float(np.sum(P))

    flat = False
    w_mean = np.nan
    d_next = jmax
    if bool(getattr(c, 'flat_rule', False)):
        # the ARTIQ flat rule from the OPX-side weights: exp from the table
        # (or Math.exp), s = 2^k squarings, P/4 sums, the mean snapped to
        # the nearest grid index
        bits = int(getattr(c, 'exp_lut_bits', 0) or 0)
        e = exp_lut_emulation(Ln, bits) if bits else np.exp(Ln)
        for _ in range(int(c.k_exp)):
            e = e * e
        P4 = e * 0.25
        S4 = float(np.sum(P4))
        _check_range(ck, 'S4 = sum(P/4)', S4)
        invS4 = 1.0 / S4
        _check_range(ck, 'inv(S4)', invS4)
        flat = bool(S4 > float(c.flat_threshold4))
        dot4 = float(np.dot(P4, wq))
        _check_range(ck, 'dot(P/4, w/4)', dot4)
        mean4 = dot4 * invS4
        _check_range(ck, 'mean/4', mean4)
        w_mean = 4.0 * mean4
        jmean = int(np.argmin(np.abs(wq - mean4)))
        d_next = jmean if flat else jmax
        state.M = 0.0                          # explicitly normalised on the OPX
        L[:] = Ln
    else:
        state.M = M
    w_next = float(w_grid[d_next])

    out = dict(P0=P / S, L=Ln.copy(), S=S, jmax=jmax, flat=flat,
               w_mean=w_mean, w_next=w_next, d_next=int(d_next),
               n_floored=n_floored, p_meas_used=pm, M=M)
    if zidx is not None:
        out['s_z'] = float(z[int(zidx)])
    return out


def remesh_trigger_fixed_point_emulation(state: FixedPointState, jmax, pulse, c,
                                         pole_a, wq=None, level=None,
                                         check_ranges=True) -> Dict[str, object]:
    """The OPX remesh trigger after pulse ``pulse``'s update, as the QUA
    trigger_block (kexp/experiments/opx_sequences/feedback.py) computes it:
    the weights exp(L - M) (exp table + squarings) / 32, the trigger metric
    (std: var(w/4) S^2 = A S - B^2 against (thr/4)^2 S^2; margin: M - max L
    beyond +-excl, L/s units), the pole angle theta* in turns in [0, 1/2)
    from the stored co-rotating state (a = y, b = z), its level and the
    predicted S_z at the level's angle. ``pole_a`` (n_pole,): the levels'
    rotation in turns; ``wq`` (m,): the run grid's w/4 (std trigger).
    ``level``: predict S_z at this level instead of the chosen one (a
    replay following a recorded level). The divisions are Math.inv(8 S) products as
    in the QUA, range-checked like every intermediate (check_ranges).
    Returns ok (the metric passes), in_window, forced, mrec (OPX units:
    var(w/4), or the margin in L/s), metric (std in Omega, or the margin in
    nats), theta, kstar, szp."""
    ck = check_ranges
    L, x, y, z = state.L, state.x, state.y, state.z
    M = float(state.M)
    m = L.size
    n_pole = int(c.n_pole)
    sums = dict(S=0.0, A=0.0, B=0.0, SAA=0.0, SBB=0.0, SAB=0.0, SZ=0.0, SY=0.0)
    inv8S = None
    if c.remesh_weights:
        tt = L - M
        bits = int(getattr(c, 'exp_lut_bits', 0) or 0)
        e = exp_lut_emulation(tt, bits) if bits else np.exp(tt)
        for _ in range(int(c.k_exp)):
            e = e * e
        P = e * (1.0 / 32.0)
        # running sums, as the QUA accumulates them (checked at every step)
        cs = np.cumsum
        sums['S'] = float(np.sum(P))
        _check_range(ck, 'Sw', cs(P))
        if c.reinit_trigger_mode == 0:
            wq = np.asarray(wq, dtype=float)
            sums['B'] = float(np.sum(P * wq))
            sums['A'] = float(np.sum(P * (wq * wq)))
            _check_range(ck, 'Bw, Aw', np.concatenate([cs(P * wq), cs(P * (wq * wq))]))
        if c.reinit_method == 1:
            sums['SAA'] = float(np.sum(P * (y * y)))
            sums['SBB'] = float(np.sum(P * (z * z)))
            sums['SAB'] = float(np.sum(P * (y * z)))
            sums['SZ'] = float(np.sum(P * z))
            sums['SY'] = float(np.sum(P * y))
            _check_range(ck, 'SAA..SY', np.concatenate(
                [cs(P * (y * y)), cs(P * (z * z)), cs(P * (y * z)), cs(P * z), cs(P * y)]))
        S = sums['S']
        _check_range(ck, '8 Sw', 8.0 * S)
        if not 8.0 * S > 0.125:
            raise FixedPointRangeError(f"fixed-point emulation: Math.inv(8 Sw) with "
                                       f"8 Sw = {8.0 * S:g} <= 1/8")
        inv8S = 1.0 / (8.0 * S)
        _check_range(ck, 'inv(8 Sw)', inv8S)
    if c.reinit_trigger_mode == 0:
        S = sums['S']
        _check_range(ck, 'A S, B^2', [sums['A'] * S, sums['B'] * sums['B']])
        mtr = sums['A'] * S - sums['B'] * sums['B']
        _check_range(ck, 'var S^2', mtr)
        _check_range(ck, '(thr/4)^2 S^2', (float(c.reinit_std_thr) / 4.0) ** 2 * (S * S))
        ok = bool(mtr < (float(c.reinit_std_thr) / 4.0) ** 2 * (S * S))
        _check_range(ck, 'var S/8, var/64', [mtr * inv8S, mtr * inv8S * inv8S])
        mrec = ((mtr * inv8S) * inv8S) * 64.0
        _check_range(ck, 'var(w/4)', mrec)
        metric = 4.0 * np.sqrt(max(mrec, 0.0))
    else:
        j = np.arange(m)
        out_mask = np.abs(j - int(jmax)) > int(c.reinit_margin_excl)
        Lout = float(np.max(L[out_mask])) if np.any(out_mask) else -8.0
        Lout = max(Lout, -8.0)
        mtr = M - Lout
        _check_range(ck, 'M - Lout', mtr)
        ok = bool(mtr >= float(c.reinit_margin_s))
        mrec = mtr
        metric = mrec * float(c.scale)
    if c.reinit_method == 0:
        aT, bT = float(y[int(jmax)]), float(z[int(jmax)])
        th = -np.arctan2(aT, bT) / (2.0 * np.pi)
    else:
        _check_range(ck, '-2 SAB, SBB - SAA', [-2.0 * sums['SAB'], sums['SBB'] - sums['SAA']])
        th = 0.5 * np.arctan2(-2.0 * sums['SAB'], sums['SBB'] - sums['SAA']) / (2.0 * np.pi)
    if th < 0.0:
        th += 0.5
    if th >= 0.5:
        th -= 0.5
    # floor(2 (n-1) (theta + 1/(4 (n-1)))): the QUA bit shift of the 4.28
    # pattern, exact for 2 (n-1) a power of two (the sequence refuses others)
    kstar = int(np.floor(2 * (n_pole - 1) * (th + 1.0 / (4.0 * (n_pole - 1)))))
    kstar = min(max(kstar, 0), n_pole - 1)
    # the predicted S_z at the chosen level (or at a given one: a replay
    # following a recorded pole level)
    k_sz = kstar if level is None else int(level)
    ang = float(np.asarray(pole_a, dtype=float)[k_sz])
    cp, sp = float(_cos2pi(ang)), float(_sin2pi(ang))
    if c.reinit_method == 0:
        szp = bT * cp - aT * sp
    else:
        num8 = (sums['SZ'] * cp - sums['SY'] * sp) * 8.0
        _check_range(ck, '8 (SZ c - SY s)', num8)
        szp = num8 * inv8S
        _check_range(ck, 'szp', szp)
    pulse = int(pulse)
    in_window = (int(c.reinit_min_pulse) - 1 <= pulse <= int(c.N) - 3)
    forced = int(c.reinit_force_pulse) > 0 and pulse >= int(c.reinit_force_pulse) - 1
    return dict(ok=ok, in_window=in_window, forced=forced, mrec=float(mrec),
                metric=float(metric), theta=float(th), kstar=kstar, szp=float(szp))


def remesh_apply_fixed_point_emulation(state: FixedPointState, jmax, p_meas_used, sz_pred,
                                       c, n0=None, check_ranges=True) -> Dict[str, object]:
    """The OPX remesh after the pole pulse's update, as the QUA
    remesh_block: s0 (measured 2 p - 1 clamped, or the predicted S_z), the
    fine grid's point 0 n0 = clamp(jmax R - (m-1)//2, 0, (m-1)(R-1)) on the
    lattice, the log-weights interpolated linearly in L from the run grid
    (fine point n0 + j at run index (n0 + j)/R), every state reset to
    (0, 0, s0), M = max(L). ``state`` is mutated. ``n0``: play this fine
    grid instead of the rule's (a replay following a recorded run). Returns
    n0 (the one used), n0_rule, s0, jmax (the fine grid's MAP)."""
    ck = check_ranges
    L = state.L
    m = L.size
    R = int(c.remesh_ratio)
    if int(c.reinit_state_source) == 0:
        _check_range(ck, 'p_meas * 2 - 1', 2.0 * float(p_meas_used) - 1.0)
        s0 = min(max(2.0 * float(p_meas_used) - 1.0, -1.0), 1.0)
    else:
        s0 = float(sz_pred)
    n0_max = (m - 1) * (R - 1)
    n0_rule = min(max(int(jmax) * R - (m - 1) // 2, 0), n0_max)
    if n0 is None:
        n0 = n0_rule
    elif not 0 <= int(n0) <= n0_max:
        raise ValueError(f"recorded fine grid point 0 {n0} outside [0, {n0_max}]")
    n0 = int(n0)
    pos = n0 + np.arange(m)
    kq = pos // R
    fr = pos - kq * R
    kq1 = np.minimum(kq + 1, m - 1)
    _check_range(ck, 'L[k+1] - L[k]', L[kq1] - L[kq])
    Lnew = L[kq] + (fr / R) * (L[kq1] - L[kq])
    _check_range(ck, 'L (interpolated)', Lnew)
    L[:] = Lnew
    state.x[:] = 0.0
    state.y[:] = 0.0
    state.z[:] = s0
    jnew = int(np.argmax(L))
    state.M = float(L[jnew])
    return dict(n0=n0, n0_rule=n0_rule, s0=s0, jmax=jnew)


def run_shot_fixed_point_emulation(w_grid, zidx, a, b, dphi0, ddphi, c,
                                   measure: Callable[[int, float], float],
                                   d_init=None, d_sched=None,
                                   remesh: Optional[Dict[str, np.ndarray]] = None,
                                   follow: Optional[Dict[str, object]] = None,
                                   on_pole: Optional[Callable[[int, int], None]] = None
                                   ) -> Dict[str, np.ndarray]:
    """One shot of the OPX loop in the float64 emulation.

    a, b, dphi0, ddphi: (N,) per-pulse tables. measure(i, w_d) -> p_meas of
    pulse i under the drive w_d = w_grid[d] (a recorded value, or a
    synthetic detector stepping the true state). Closed loop when d_sched
    is None (first drive index d_init, then d_next); open loop drives
    d_sched[i] and still runs the posterior. Returns per-pulse arrays:
    w_used, d_used, p_meas, s_z, L (N, m; the saved max-normalised L/s),
    P0 (N, m), w_next, d_next, flat, n_floored.

    remesh (c.remesh, closed loop): a dict of one shot's host tables --
    lat_w (n_lat,), lat_adv (n_lat, N), fine_adv (N,), pole_a, pole_b
    (n_pole,), n_res, wq (m,) -- as build_feedback_shot_tables makes them;
    the loop then runs the OPX's trigger / pole pulse / remesh exactly as
    the sequence orders them (update, remesh if this was the pole pulse,
    saves, trigger, next drive). Extra outputs: grid (N, m) the grid of
    each saved row, a_used (N,), remesh_pulse, remesh_n0, remesh_pole_level,
    remesh_s0, remesh_trigger, theta (the trigger's pole angle, turns).

    follow (with remesh; a replay of a recorded run): the recorded discrete
    decisions -- drives (N,) grid indices of the grid in effect at each
    pulse, remesh_pulse (-1 = none), remesh_n0, pole_level -- are played
    instead of the emulation's own; every continuous quantity is still
    computed (s0 from the measured pole readout or from the model at the
    recorded level). The emulation's own decisions on the
    followed trajectory are reported as own_trigger_pulse (the pulse after
    whose update it would have fired first, -1 = never), own_pole_level (its
    level there), own_n0 (its fine-grid point 0 at the recorded pole pulse)
    and own_trigger_metric; remesh_trigger / remesh_trigger_metric are the
    values at the recorded trigger pulse (OPX units / std in Omega or
    margin in nats).

    on_pole(i, level) (with remesh): called just before pulse i's reading
    when pulse i is the pole pulse -- a synthetic detector uses it to play
    the level's duration and to shift the later pulse starts by the pole
    step's extra time, as the OPX does.
    """
    w_grid = np.asarray(w_grid, dtype=float)
    N = int(np.asarray(a).size)
    m = w_grid.size
    st = FixedPointState.uniform(m)
    out = dict(w_used=np.empty(N), d_used=np.empty(N, dtype=int), p_meas=np.empty(N),
               s_z=np.empty(N), L=np.empty((N, m)), P0=np.empty((N, m)),
               w_next=np.empty(N), d_next=np.empty(N, dtype=int),
               flat=np.zeros(N, dtype=bool), n_floored=np.zeros(N, dtype=int))
    if d_sched is None:
        if d_init is None:
            raise ValueError("closed loop needs d_init")
        d = int(d_init)
    rm = remesh
    if rm is not None:
        if d_sched is not None:
            raise ValueError("the remesh is closed-loop only")
        R = int(c.remesh_ratio)
        out.update(grid=np.empty((N, m)), a_used=np.empty(N), remesh_pulse=-1,
                   remesh_n0=0, remesh_pole_level=-1, remesh_s0=0.0,
                   remesh_trigger=0.0, remesh_trigger_metric=np.nan,
                   theta=np.full(N, np.nan), s_z_on_grid=np.ones(N, dtype=bool))
        n0, sp, pole_now, fired, pole_k, sz_lat = 0, 0, False, False, 0, 0.0
        n_res = int(rm['n_res'])
        n_pole = int(np.asarray(rm['pole_a']).size)
        if follow is not None:
            f_drives = follow.get('drives')
            f_p = int(follow['remesh_pulse'])
            f_n0 = int(follow.get('remesh_n0', 0))
            f_k = int(follow.get('pole_level', -1))
            if f_p >= 0 and not 0 <= f_k < n_pole:
                raise ValueError(f"recorded pole level {f_k} outside [0, {n_pole})")
            own_fired = False
            out.update(own_trigger_pulse=-1, own_pole_level=-1, own_n0=-1,
                       own_trigger_metric=np.nan)
    elif follow is not None:
        raise ValueError("follow= is for remesh replays")
    for i in range(N):
        if d_sched is not None:
            d = int(d_sched[i])
        if rm is not None and follow is not None:
            if f_drives is not None:
                d = int(f_drives[i])
            pole_now = (i == f_p)
            if pole_now:
                pole_k = f_k
        if rm is None:
            grid = w_grid
            a_i, b_i, d0_i, dd_i = a[i], b[i], dphi0[i], ddphi[i]
            zj = zidx
        else:
            grid = w_grid if sp == 0 else np.asarray(rm['lat_w'])[n0 + np.arange(m)]
            if pole_now:
                a_i, b_i = rm['pole_a'][pole_k], rm['pole_b'][pole_k]
            else:
                a_i, b_i = a[i], b[i]
            d0_i = dphi0[i] if sp == 0 else rm['lat_adv'][n0, i]
            dd_i = ddphi[i] if sp == 0 else rm['fine_adv'][i]
            zj = None
            out['a_used'][i] = a_i
            if pole_now and on_pole is not None:
                on_pole(i, int(pole_k))
        p_meas = float(measure(i, float(grid[d])))
        u = posterior_update_fixed_point_emulation(
            st, d, p_meas, a_i, b_i, d0_i, dd_i, grid, c, zidx=zj)
        out['w_used'][i] = grid[d]
        out['d_used'][i] = d
        out['p_meas'][i] = p_meas
        d_next = int(u['d_next'])
        if rm is not None:
            jmax = int(u['jmax'])
            if pole_now:
                n0_force = None if follow is None else f_n0
                r = remesh_apply_fixed_point_emulation(st, jmax, u['p_meas_used'], sz_lat, c,
                                                       n0=n0_force)
                if follow is not None:
                    out['own_n0'] = r['n0_rule']
                n0, sp, jmax, pole_now = r['n0'], 1, r['jmax'], False
                out.update(remesh_pulse=i, remesh_n0=n0, remesh_pole_level=pole_k,
                           remesh_s0=r['s0'])
                grid = np.asarray(rm['lat_w'])[n0 + np.arange(m)]
                d_next = jmax
            Ln = st.L - st.M
            out['L'][i] = Ln
            P = np.exp(int(c.scale) * Ln)
            out['P0'][i] = P / np.sum(P)
            if sp == 0:
                jr = zidx
            else:
                jr = min(max(n_res - n0, 0), m - 1)
                out['s_z_on_grid'][i] = 0 <= n_res - n0 <= m - 1
            out['s_z'][i] = float(st.z[int(jr)])
            out['grid'][i] = grid
            if follow is None:
                if not fired:
                    t = remesh_trigger_fixed_point_emulation(st, jmax, i, c, rm['pole_a'],
                                                             rm.get('wq'))
                    out['theta'][i] = t['theta']
                    if t['in_window'] and (t['ok'] or t['forced']):
                        pole_now, fired, pole_k, sz_lat = True, True, t['kstar'], t['szp']
                        out['remesh_trigger'] = t['mrec']
                        out['remesh_trigger_metric'] = t['metric']
            elif f_p < 0 or i < f_p:
                # the recorded trajectory has not fired yet after this update:
                # the emulation's own trigger on it (reported), and the model
                # S_z at the recorded level for the recorded pole pulse
                lev = f_k if i == f_p - 1 else None
                t = remesh_trigger_fixed_point_emulation(st, jmax, i, c, rm['pole_a'],
                                                         rm.get('wq'), level=lev)
                out['theta'][i] = t['theta']
                if not own_fired and t['in_window'] and (t['ok'] or t['forced']):
                    own_fired = True
                    out['own_trigger_pulse'] = i
                    out['own_pole_level'] = t['kstar']
                    out['own_trigger_metric'] = t['metric']
                if i == f_p - 1:
                    sz_lat = t['szp']
                    out['remesh_trigger'] = t['mrec']
                    out['remesh_trigger_metric'] = t['metric']
            out['w_next'][i] = grid[d_next]
        else:
            out['s_z'][i] = u['s_z']
            out['L'][i] = u['L']
            out['P0'][i] = u['P0']
            out['w_next'][i] = u['w_next']
        out['d_next'][i] = d_next
        out['flat'][i] = u['flat']
        out['n_floored'][i] = u['n_floored']
        if d_sched is None:
            d = d_next
    out['state'] = st
    return out


def true_bloch_step(s, omega_ctrl, omega_true, dt_ideal, dt_eff, t_in, Omega,
                    omega_LS, t_img, C):
    """Step the TRUE Bloch vector s = (sx, sy, sz) through one pulse of the
    reset model: drive phase 0 at the pulse start, hypothesis azimuth
    -omega_true * t_in. Exactly analysis/feedback.py's synthetic-shot step
    (generate_posterior's rotation for one hypothesis) with
    phase_tracker = 0. Returns (hz_measured, s_after) where hz is the z the
    APD sees (before the light-shift rotation and back-action, which never
    touch z)."""
    sx, sy, sz = (float(v) for v in s)
    delta_omega = omega_ctrl - omega_true
    norm_H = np.sqrt(Omega * Omega + delta_omega * delta_omega)
    inv_norm_H = 1.0 / norm_H
    Omega_over_H = Omega * inv_norm_H
    u_z = delta_omega * inv_norm_H
    theta = -dt_ideal * norm_H
    sin_H, cos_H = np.sin(theta), np.cos(theta)
    phi = -omega_true * t_in
    u_x = Omega_over_H * np.cos(phi)
    u_y = Omega_over_H * np.sin(phi)
    omc = 1.0 - cos_H
    hx = ((cos_H + omc * u_x * u_x) * sx + (omc * u_x * u_y - sin_H * u_z) * sy
          + (omc * u_x * u_z + sin_H * u_y) * sz)
    hy = ((omc * u_x * u_y + sin_H * u_z) * sx + (cos_H + omc * u_y * u_y) * sy
          + (omc * u_y * u_z - sin_H * u_x) * sz)
    hz = ((omc * u_x * u_z - sin_H * u_y) * sx + (omc * u_y * u_z + sin_H * u_x) * sy
          + (cos_H + omc * u_z * u_z) * sz)
    alpha_z = dt_eff * (omega_true - omega_ctrl) - omega_LS * t_img
    cos_z, sin_z = np.cos(alpha_z), np.sin(alpha_z)
    nsx = (cos_z * hx + sin_z * hy) * C
    nsy = (-sin_z * hx + cos_z * hy) * C
    return float(hz), (nsx, nsy, float(hz))


# ---------------------------------------------------------------------------
# result container
# ---------------------------------------------------------------------------

@dataclass
class FeedbackOPXReplayResult(FeedbackReplayResult):
    """FeedbackReplayResult plus what the OPX itself recorded per pulse.

    t_pulse_start_rr: actual pulse starts (s from pulse 0) from the
        timestamps; slip_rr: t_pulse_start - t_pulse_scheduled (s);
        log_weights_opx_rr / P0_opx_rr: the OPX's own L/s (log_weight_scale)
        and the posterior derived from it; drive_index_rr: the grid index
        the OPX drove; max_abs_dP_r: per shot, max |P0_replay - P0_opx|;
        valid_r: shots the OPX ran (opx_data_valid). Rows of shots the OPX
        did not run are NaN.
    """
    t_pulse_start_rr: Optional[np.ndarray] = None
    slip_rr: Optional[np.ndarray] = None
    log_weights_opx_rr: Optional[np.ndarray] = None
    log_weight_scale: float = float(LOG_WEIGHT_SCALE)
    P0_opx_rr: Optional[np.ndarray] = None
    drive_index_rr: Optional[np.ndarray] = None
    max_abs_dP_r: Optional[np.ndarray] = None
    valid_r: Optional[np.ndarray] = None
    # the exact applied drive (2 pi * 2 * (if_150[d] - if_80[d])) and the
    # recomputed schedule
    omega_applied_rr: Optional[np.ndarray] = None
    t_scheduled_rr: Optional[np.ndarray] = None
    # remesh runs: the grid of every replayed row (rad/s; the grid changes at
    # the pole pulse). Row k = the grid of P0_rr[:, k] (after pulse k's
    # update) = the RECORDED omega_raman_mesh row k + 1 (fr.mesh_rr, N + 1
    # rows, row 0 = the prior's grid). omega_guess_list / zidx are shot 0's
    # run grid only. remesh: the decisions -- recorded, played, the replay's
    # own -- with the trigger values in physical units (std in Omega or
    # margin in nats), s_z_on_grid (0: the saved s_z is the fine grid's edge
    # hypothesis, resonance off the fine grid) and the excluded shots
    mesh_rr: Optional[np.ndarray] = None
    remesh: Optional[Dict[str, object]] = None

    @property
    def log_weights4_opx_rr(self):
        """Pass-2 name: the OPX log weights in L/4 units."""
        if self.log_weights_opx_rr is None:
            return None
        return self.log_weights_opx_rr * (float(self.log_weight_scale) / 4.0)


# ---------------------------------------------------------------------------
# the replay
# ---------------------------------------------------------------------------

def _per_shot_column(ad, key, n_shots):
    """ad.p.<key> as an (n_shots,) column in the data's (unshuffled) shot
    order: a scalar broadcast, a scanned parameter broadcast along its xvar
    axis over xvardims, or an array already of length n_shots."""
    arr = np.asarray(getattr(ad.p, key), dtype=float).reshape(-1)
    if arr.size == 1:
        return np.full(n_shots, float(arr[0]))
    xvarnames = list(getattr(ad, 'xvarnames', []) or [])
    xvardims = [int(d) for d in np.atleast_1d(getattr(ad, 'xvardims', []) or [])]
    if key in xvarnames and len(xvardims) == len(xvarnames):
        k = xvarnames.index(key)
        if arr.size == xvardims[k]:
            shape = [1] * len(xvardims)
            shape[k] = xvardims[k]
            full = np.broadcast_to(arr.reshape(shape), xvardims).reshape(-1)
            if full.size == n_shots:
                return full.astype(float)
    if arr.size == n_shots:
        return arr.astype(float)
    raise ValueError(f"ad.p.{key} has {arr.size} values; cannot map onto "
                     f"{n_shots} shots.")


class FeedbackOPXReplay(Feedback):
    """Replay of an OPX feedback run (see the module docstring).

    Constructor: (ad, use_actual_timestamps=True, lut_size=2**20).
    ``self.p`` is a copy of ``ad.p`` with the OPX calibration mapped onto
    the names Feedback reads (v_apd_all_up/down <- *_opx,
    n_photons_per_shot <- N_PHOTONS_REF and std_n_photons_per_shot <-
    std_photon_fraction_opx * N_PHOTONS_REF so that sigma/N = sigma_p,
    t_raman_pulse_offset <- t_raman_pulse_offset_opx); edit ``fr.p.<name>``
    before a replay for a what-if (light shift, coherence, midpoint,
    std_photon_fraction_opx, endpoints).
    """

    # host-side sin/cos LUT of generate_posterior: 2^20 entries make the
    # linear interpolation exact to ~4e-12 (the kernel's 4096 costs ~1e-3
    # in P0); this replay is the reference, so it uses the exact one
    LUT_SIZE = 1 << 20
    # The OPX carries only sigma_p = sigma/N, so the photon number is a
    # free scale here. generate_posterior truncates n = int(N_photons) while
    # k = N_photons * p_meas stays a float: with the ARTIQ 1336.2 that is a
    # 1.5e-4 scale mismatch worth ~1e-3 in P0. An integer reference makes
    # the likelihood exp(-(p_meas - p1)^2 / 2 sigma_p^2) exactly.
    N_PHOTONS_REF = 1000.0

    def __init__(self, ad, use_actual_timestamps=True, lut_size=LUT_SIZE):
        self.ad = ad
        self._run_id = int(getattr(getattr(ad, 'run_info', None), 'run_id', -1))
        self.use_actual_timestamps = bool(use_actual_timestamps)
        self._fixed_point = False
        self._lut_size = int(lut_size)

        p = copy.copy(ad.p)
        self.p = p
        # the run's own params, never edited: what the OPX PLAYED (durations,
        # grid, lattice, pole levels, schedule) is rebuilt from these, while
        # fr.p is the replay's MODEL and may be edited for a what-if
        self._p_run = copy.copy(ad.p)
        N = int(p.N_pulses)
        m = int(p.feedback_grid_size)
        self.remesh = int(np.asarray(getattr(p, 'opx_remesh_enable', 0)).reshape(-1)[0]) != 0

        # --- containers, (n_shots, ...) in the data's shot order ---
        data = ad.data
        apd = np.asarray(data.apd, dtype=float)
        n_shots = int(apd.size // N)
        self.n_shots, self.N_step = n_shots, N

        def rows(key, shape, required=True):
            if not hasattr(data, key):
                if required:
                    raise ValueError(f"ad.data.{key} is required for the OPX replay.")
                return None
            return np.asarray(getattr(data, key), dtype=float).reshape(n_shots, *shape)

        self.apd_rr = rows('apd', (N,))
        # the exact applied two-photon frequency from the streamed drive
        # index and the run's integer IF table (both AOs +1 order, double
        # pass); pass-2 files: 2 * dif_hz; older: the omega_raman container
        didx = rows('drive_index', (N,), required=False)
        if_tab = rows('if_table_hz', (m, 2), required=False)
        self.drive_index_rr = None
        if didx is not None and if_tab is not None:
            didx = didx.astype(np.int64)
            self.drive_index_rr = didx
            self.if_table_rr = if_tab
            self.omega_applied_rr = 2.0 * np.pi * applied_frequency_hz(if_tab, didx)
        else:
            self.if_table_rr = None
            dif = rows('dif_hz', (N,), required=False)
            if dif is not None:
                f_app = 2.0 * dif.astype(float)
                f_app[dif < 0] = np.nan                       # INT_MISSING
                self.omega_applied_rr = 2.0 * np.pi * f_app
            else:
                self.omega_applied_rr = rows('omega_raman', (N,), required=False)
        if self.remesh:
            # the recorded decisions (one per shot) and the lattice IF table;
            # the applied frequency of every pulse from its lattice point (run
            # grid index d -> d R up to the pole pulse, fine index d -> n0 + d
            # after it), exactly as the finish hook derives omega_raman
            R = int(round(float(np.asarray(p.opx_remesh_ratio, dtype=float).reshape(-1)[0])))
            self.remesh_ratio = R
            n_lat = (m - 1) * R + 1

            def one(key):
                return rows(key, (1,)).reshape(-1)
            self.remesh_pulse_r = one('remesh_pulse').astype(np.int64)
            self.remesh_n0_r = one('remesh_n0').astype(np.int64)
            self.remesh_pole_level_r = one('remesh_pole_level').astype(np.int64)
            self.remesh_s0_r = one('remesh_s0')
            self.remesh_trigger_r = one('remesh_trigger')
            # the fine grid's drives index the lattice: without its IF table
            # the applied frequencies after the pole pulse are unknown
            self.if_lattice_rr = rows('if_lattice_hz', (n_lat, 2))
            self.s_z_on_grid_rr = rows('s_z_on_grid', (N,), required=False)
            if self.drive_index_rr is None:
                raise ValueError("[opx replay] a remesh run needs drive_index.")
        self.s_z_opx_rr = rows('s_z', (N,), required=False)
        Lw, scale = None, float(getattr(p, 'feedback_log_weight_scale', LOG_WEIGHT_SCALE))
        if hasattr(data, 'log_weights'):
            Lw = np.asarray(data.log_weights, dtype=float).reshape(n_shots, -1, m)
        elif hasattr(data, 'log_weights4'):
            Lw = np.asarray(data.log_weights4, dtype=float).reshape(n_shots, -1, m)
            scale = 4.0
        self.log_weight_scale = float(np.asarray(scale, dtype=float).reshape(-1)[0])
        self.L_prior_rr = None
        if Lw is not None and Lw.shape[1] == N + 1:
            self.L_prior_rr, Lw = Lw[:, 0, :], Lw[:, 1:, :]
        self.L_opx_rr = Lw
        prob = rows('probabilities', (N + 1, m), required=False)
        if self.L_opx_rr is not None:
            self.P0_opx_rr = log_weights_to_probabilities(self.L_opx_rr, self.log_weight_scale)
        elif prob is not None:
            self.P0_opx_rr = prob[:, 1:, :]
        else:
            self.P0_opx_rr = None
        self.t_raman_pulse_rr = rows('t_raman_pulse', (N,))
        seed = rows('t_raman_pulse_seed', (1,), required=False)
        self.t_raman_pulse_seed_r = (seed.reshape(-1).astype(np.int64)
                                     if seed is not None else None)
        valid = rows('opx_data_valid', (1,), required=False)
        self.valid_r = (valid.reshape(-1) > 0) if valid is not None \
            else np.ones(n_shots, dtype=bool)
        self.valid_r &= np.all(np.isfinite(self.apd_rr), axis=1)
        t_start = rows('t_pulse_start', (N,), required=False)
        if t_start is None and hasattr(data, 't_pulse_start_cc'):
            t_start = timestamps_cc_to_seconds(
                np.asarray(data.t_pulse_start_cc).reshape(n_shots, N),
                valid=self.valid_r)
        self.t_actual_rr = t_start
        self.mesh_rr = rows('omega_raman_mesh', (N + 1, m), required=False)

        # --- calibration in the names Feedback reads ---
        p.v_apd_all_up = float(p.v_apd_all_up_opx)
        p.v_apd_all_down = float(p.v_apd_all_down_opx)
        p.n_photons_per_shot = float(self.N_PHOTONS_REF)
        p.std_n_photons_per_shot = float(p.std_photon_fraction_opx) * p.n_photons_per_shot
        p.t_raman_pulse_offset = float(p.t_raman_pulse_offset_opx)
        p.t_raman_pulse = float(np.asarray(p.t_raman_pulse, dtype=float).reshape(-1)[0])
        p.t_raman_pulse_ideal = p.t_raman_pulse - p.t_raman_pulse_offset
        p.feedback_apd_map_enabled = False       # OPX endpoints are used as-is
        p.feedback_remesh_threshold_Omega = 0.0
        p.feedback_grid_size = m
        p.N_pulses = N
        # the initial offset / span may be scanned: keep the per-shot columns
        # and hand Feedback.__init__ shot 0's scalar
        self.offset_r = _per_shot_column(ad, 'feedback_fractional_initial_offset', n_shots)
        self.span_r = _per_shot_column(ad, 'feedback_guess_span_Omega', n_shots)
        if self.remesh:
            self._init_remesh_played()
        if self.omega_applied_rr is not None:
            # invalid shots carry no applied frequency (as the finish hook)
            self.omega_applied_rr = np.array(self.omega_applied_rr, dtype=float)
            self.omega_applied_rr[~self.valid_r] = np.nan
        if self.t_actual_rr is not None:
            self.t_actual_rr = np.array(self.t_actual_rr, dtype=float)
            self.t_actual_rr[~self.valid_r] = np.nan
        p.feedback_fractional_initial_offset = float(self.offset_r[0])
        p.feedback_guess_span_Omega = float(self.span_r[0])
        for key in ('frequency_raman_transition', 't_raman_pi_pulse', 't_img_pulse',
                    'frequency_lightshift', 'back_action_coherence',
                    'feedback_measurement_midpoint_fraction'):
            setattr(p, key, float(np.asarray(getattr(p, key), dtype=float).reshape(-1)[0]))

        Feedback.__init__(self, lut_size=self._lut_size, expt_params=p)
        self._omega_resonance_rad_s = 2.0 * np.pi * float(p.frequency_raman_transition)

        # the grid the OPX recorded vs the one rebuilt here
        if self.mesh_rr is not None:
            g0, _ = self._grid_for_shot(0)
            if self.valid_r[0] and not np.allclose(self.mesh_rr[0, 0], g0, rtol=0, atol=1e-6):
                print("[opx replay] WARNING: the recorded omega_raman_mesh of shot 0 "
                      "differs from the grid rebuilt from ad.p (feedback_grid_omega); "
                      "the replay uses the rebuilt grid.")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def emulate_fixed_point(self, enable=True):
        """Replay with the OPX emulation instead of generate_posterior
        (float64 with the OPX scalings, tables, floor and control law; not
        bit-exact fixed point). Returns self, so
        fr.emulate_fixed_point(True).replay_measured()."""
        self._fixed_point = bool(enable)
        return self

    def constants(self) -> FeedbackConstants:
        """The run's fixed-point constants from the current self.p (so a
        fr.p edit is honoured), including the flags the sequence read
        (feedback_flat_rule_bool, feedback_log_weight_scale,
        opx_sincos_lut_bits, opx_exp_lut_bits, t_raman_pulse_n_levels;
        module defaults for a file without them)."""
        p = self.p
        return feedback_constants(lambda k: getattr(p, k))

    def _grid_for_shot(self, r):
        return feedback_grid_omega(
            self.p, fractional_initial_offset=float(self.offset_r[r]),
            guess_span_Omega=float(self.span_r[r]))

    def scheduled_starts_rr(self):
        """The schedule the OPX was held to (s from pulse 0), recomputed
        from the saved durations and the current self.p exactly as the
        sequence computed it (step gaps from the pulse-time list). Remesh
        runs: from the run's own params and the APPLIED durations (the pole
        pulse's level duration at its index), with the pole step's extra
        hold (remesh_pulse_starts_cc) -- the pulses after the pole pulse
        start later than the drawn schedule."""
        if self.remesh:
            return scheduled_pulse_starts_s(self._p_run, self._applied_durations_rr(),
                                            pole_pulse=self._played_pole_pulse_r())
        return scheduled_pulse_starts_s(self.p, self.t_raman_pulse_rr)

    # ------------------------------------------------------------------
    # remesh runs
    # ------------------------------------------------------------------

    def _lattice_index_rr(self, didx):
        """Lattice index of every pulse's drive (INT_MISSING stays < 0)."""
        R = self.remesh_ratio
        dd = np.asarray(didx).astype(np.int64)
        N = dd.shape[1]
        fired = self.remesh_pulse_r >= 0
        after = fired[:, None] & (np.arange(N)[None, :] > self.remesh_pulse_r[:, None])
        lat = np.where(after, self.remesh_n0_r[:, None] + dd, dd * R)
        return np.where(dd < 0, -1, lat)

    def _host_col(self, key):
        """(n_shots,) column of a RUN param for build_feedback_shot_tables:
        the scanned offset / span per shot, every other key the run's own
        (unedited) value."""
        if key == 'feedback_fractional_initial_offset':
            return np.asarray(self.offset_r, dtype=float)
        if key == 'feedback_guess_span_Omega':
            return np.asarray(self.span_r, dtype=float)
        return np.full(self.n_shots, float(np.asarray(getattr(self._p_run, key),
                                                      dtype=float).reshape(-1)[0]))

    def remesh_host_tables(self, c=None):
        """The per-shot host tables of what the OPX PLAYED (drawn durations,
        grid, lattice, pole-level durations, schedule), built once with the
        sequence's own build_feedback_shot_tables from the saved seeds and
        the run's own params -- a fr.p edit never changes them. (``c`` is
        ignored; kept for callers of the first version.)"""
        return self._T_run

    def _init_remesh_played(self):
        """Remesh runs: build the played tables and check every valid shot's
        recorded decisions against them. A shot whose decisions the sequence
        cannot have made (pole pulse outside [min_pulse, N-2], level outside
        [0, n_pole), fine grid outside the lattice, a drive index outside the
        grid, 'not fired' with a level, durations the seed does not
        reproduce) is EXCLUDED from the replay, with the count and the reason
        printed and kept in self.remesh_excluded."""
        pr = self._p_run
        self._c_run = cr = feedback_constants(
            lambda k: float(np.asarray(getattr(pr, k), dtype=float).reshape(-1)[0]))
        if self.t_raman_pulse_seed_r is None:
            raise ValueError("[opx replay] the remesh replay needs the saved "
                             "t_raman_pulse_seed.")
        self._T_run = T = build_feedback_shot_tables(self._host_col, self.n_shots, cr,
                                                     seeds=self.t_raman_pulse_seed_r)
        N, m, R, n_pole = self.N_step, int(cr.m), int(cr.remesh_ratio), int(cr.n_pole)
        rp, n0, lev = self.remesh_pulse_r, self.remesh_n0_r, self.remesh_pole_level_r
        didx = self.drive_index_rr
        d_rec = np.asarray(self.t_raman_pulse_rr, dtype=float)
        pole_d = T.pole_d_cc.astype(float) * CLOCK_NS * 1e-9
        reasons: Dict[str, list] = {}
        for r in np.flatnonzero(self.valid_r):
            fired = rp[r] >= 0
            why = None
            if fired and not int(cr.reinit_min_pulse) <= rp[r] <= N - 2:
                why = "pole pulse outside [feedback_reinit_min_pulse, N-2]"
            elif fired and not 0 <= lev[r] < n_pole:
                why = "pole level outside [0, opx_remesh_pole_levels)"
            elif fired and not 0 <= n0[r] <= (m - 1) * (R - 1):
                why = "fine grid point 0 outside [0, (m-1)(R-1)]"
            elif not fired and (rp[r] != -1 or lev[r] != -1):
                why = "not fired, but remesh_pulse / remesh_pole_level not -1"
            elif np.any((didx[r] < 0) | (didx[r] > m - 1)):
                why = "a drive index outside [0, feedback_grid_size)"
            else:
                keep = np.ones(N, dtype=bool)
                if fired:
                    keep[rp[r]] = False
                if not np.allclose(T.d_s[r, keep], d_rec[r, keep], rtol=0, atol=1e-12):
                    why = "t_raman_pulse differs from the durations drawn from the seed"
                elif fired and not (abs(d_rec[r, rp[r]] - pole_d[lev[r]]) < 1e-12
                                    or abs(d_rec[r, rp[r]] - T.d_s[r, rp[r]]) < 1e-12):
                    # the finish hook writes the level's duration (a file
                    # without the hook keeps the drawn one)
                    why = "the pole pulse's t_raman_pulse is neither its level's nor the drawn one"
            if why is not None:
                reasons.setdefault(why, []).append(int(r))
        n_valid = int(np.sum(self.valid_r))
        n_bad = sum(len(v) for v in reasons.values())
        if n_valid and n_bad == n_valid and any('seed' in k for k in reasons):
            raise ValueError("[opx replay] the durations re-drawn from the saved seeds do "
                             "not reproduce t_raman_pulse on any shot: the run's params "
                             "or seeds are not the file's.")
        for why, shots in reasons.items():
            self.valid_r[shots] = False
            print(f"[opx replay] NOTE: {len(shots)} shot(s) excluded from the replay: "
                  f"{why} (shots {shots[:10]}{' ...' if len(shots) > 10 else ''}).")
        self.remesh_excluded = reasons
        lat = self._lattice_index_rr(didx)
        lat[~self.valid_r] = -1
        self.omega_applied_rr = 2.0 * np.pi * applied_frequency_hz(self.if_lattice_rr, lat)

    def _played_pole_pulse_r(self):
        """(n_shots,) the recorded pole pulse of every valid shot, -1 else."""
        return np.where(self.valid_r, self.remesh_pulse_r, -1)

    def _applied_durations_rr(self):
        """(n_shots, N) the durations the OPX played: drawn from the seed,
        the pole pulse's level duration at its index (valid fired shots)."""
        T = self._T_run
        d = T.d_s.copy()
        pole_d = T.pole_d_cc.astype(float) * CLOCK_NS * 1e-9
        rp = self._played_pole_pulse_r()
        for r in np.flatnonzero(rp >= 0):
            d[r, rp[r]] = pole_d[int(self.remesh_pole_level_r[r])]
        return d

    def _drawn_durations_rr(self, T=None):
        """The drawn pulse durations (s), re-drawn from the seeds (checked
        against t_raman_pulse at construction)."""
        return self._T_run.d_s.copy()

    # keys that define what the OPX played or how the sequence was
    # structured: a replay rebuilds those from the run's own params, so an
    # edit of them in fr.p cannot mean anything and is refused. (The grid's
    # offset and span are always the run's per-shot columns: _reinit_params
    # resets them in fr.p on every replay.)
    STRUCTURAL_KEYS_REMESH = (
        'N_pulses', 'feedback_grid_size', 'opx_remesh_enable', 'opx_remesh_ratio',
        'opx_remesh_pole_levels', 'feedback_grid_center_exact_offset', 't_img_pulse',
        't_raman_pulse_random_bool', 't_raman_pulse_block_bool', 't_raman_pulse_n_levels',
        't_raman_pulse_min_frac_pi', 't_raman_pulse_max_frac_pi',
        'opx_feedback_split_update', 't_feedback_extra_gap', 't_opx_remesh_hold',
        'feedback_flat_rule_bool')

    def _check_structure(self):
        for key in self.STRUCTURAL_KEYS_REMESH:
            if not (hasattr(self.p, key) or hasattr(self._p_run, key)):
                continue
            a = np.asarray(getattr(self.p, key, np.nan), dtype=float).reshape(-1)
            b = np.asarray(getattr(self._p_run, key, np.nan), dtype=float).reshape(-1)
            if a.shape != b.shape or not np.array_equal(a, b, equal_nan=True):
                raise ValueError(
                    f"[opx replay] fr.p.{key} was edited: it defines what the OPX played "
                    f"or the sequence's structure, which a replay rebuilds from the run's "
                    f"own params. A remesh replay's what-ifs are model keys (light shift, "
                    f"coherence, midpoint, std_photon_fraction_opx, t_raman_pi_pulse, "
                    f"frequency_raman_transition, *_opx calibrations, the feedback_reinit_* "
                    f"decision rules). Restore it to {b.tolist()}.")

    def _remesh_shot_inputs(self, r, t_ext):
        """One shot's inputs for both engines: what was PLAYED (the frozen
        run tables: absolute grid and lattice frequencies, durations, pole
        durations) expressed in the current MODEL (fr.p: resonance, Omega =
        pi / t_raman_pi_pulse, the switch offset). Returns w_grid (m,), a, b
        (N,), dphi0, ddphi (N,), rm (the remesh dict of
        run_shot_fixed_point_emulation plus lat_abs and pole_d_s)."""
        T, cr = self._T_run, self._c_run
        R = int(cr.remesh_ratio)
        Om = float(self.Omega)
        wres = float(self._omega_resonance_rad_s)
        t_pi = float(self.p.t_raman_pi_pulse)
        t_off = float(self.p.t_raman_pulse_offset)
        grid_abs = np.asarray(T.omega_grid[r], dtype=float)
        lat_abs = cr.omega_res + cr.Omega * np.asarray(T.lat_w[r], dtype=float)
        pole_d = T.pole_d_cc.astype(float) * CLOCK_NS * 1e-9
        d = np.asarray(T.d_s[r], dtype=float)
        dphi0, ddphi = corotating_phase_tables(grid_abs / (2.0 * np.pi), t_ext)
        fine_hz = cr.Omega * float(T.dw[r]) / R / (2.0 * np.pi)
        w_grid = (grid_abs - wres) / Om
        rm = dict(lat_w=(lat_abs - wres) / Om, lat_abs=lat_abs,
                  lat_adv=lattice_frame_advances(lat_abs / (2.0 * np.pi), t_ext),
                  fine_adv=spacing_frame_advances([fine_hz], t_ext)[0],
                  pole_a=(pole_d - t_off) / (2.0 * t_pi), pole_b=pole_d / (2.0 * t_pi),
                  pole_d_s=pole_d, n_res=int(T.n_res[r]), wq=w_grid / 4.0)
        return w_grid, (d - t_off) / (2.0 * t_pi), d / (2.0 * t_pi), dphi0, ddphi, rm

    def _t_input_rr(self, use_actual):
        if use_actual is None:
            use_actual = self.use_actual_timestamps
        if use_actual:
            if self.t_actual_rr is None:
                raise ValueError("no pulse timestamps (t_pulse_start / "
                                 "t_pulse_start_cc) in the run file; use "
                                 "use_actual_timestamps=False.")
            return np.asarray(self.t_actual_rr, dtype=float), 'actual'
        return self.scheduled_starts_rr(), 'scheduled'

    def _corotating_tables(self, grid, t_in, d, c):
        """(a, b, dphi0, ddphi) of one shot for the emulation: the frame
        advances over the N+1-row schedule (row N one scheduled gap after
        the last pulse start, whether the starts are actual or scheduled)."""
        t_off = float(self.p.t_raman_pulse_offset)
        a = (d - t_off) / (2.0 * self.p.t_raman_pi_pulse)
        b = d / (2.0 * self.p.t_raman_pi_pulse)
        d_cc = np.rint(d / (CLOCK_NS * 1e-9)).astype(np.int64)
        gap_last = int(feedback_step_gaps_cc(d_cc[-1:], c.t_img_cc, c.budget_cc,
                                             c.overhead_cc, c.extra_gap_cc, c.edge_cc)[0])
        t_ext = np.concatenate([t_in, [t_in[-1] + gap_last * CLOCK_NS * 1e-9]])
        dphi0, ddphi = corotating_phase_tables(grid / (2.0 * np.pi), t_ext)
        return a, b, dphi0, ddphi

    def _normalize_apd(self, apd_rr):
        p1 = np.clip(apd_volts_to_photon_fraction(apd_rr, self.v_apd_all_up,
                                                  self.v_apd_all_down), 0.0, 1.0)
        if not self.feedback_measurement_midpoint_remap_enabled:
            return 2.0 * p1 - 1.0
        delta = float(self.feedback_measurement_midpoint_fraction) - 0.5
        if abs(delta) < 1e-15:
            return 2.0 * p1 - 1.0
        disc = np.maximum(0.25 - 4.0 * delta * (p1 - (delta + 0.5)), 0.0)
        return np.clip((0.5 - np.sqrt(disc)) / (2.0 * delta), -1.0, 1.0)

    def _reinit_params(self):
        """Re-run Feedback's initialisation on the (possibly edited) self.p.
        The OPX calibration is re-mapped from its *_opx names on every
        replay, so an edit of v_apd_all_up_opx / v_apd_all_down_opx /
        t_raman_pulse_offset_opx reaches both engines alike (the copied
        names are outputs of this mapping, not inputs)."""
        p = self.p
        p.v_apd_all_up = float(p.v_apd_all_up_opx)
        p.v_apd_all_down = float(p.v_apd_all_down_opx)
        p.t_raman_pulse_offset = float(p.t_raman_pulse_offset_opx)
        p.t_raman_pulse_ideal = float(p.t_raman_pulse) - float(p.t_raman_pulse_offset)
        # an edited std_photon_fraction_opx reaches the likelihood through
        # sigma/N (N is the fixed integer reference)
        p.n_photons_per_shot = float(self.N_PHOTONS_REF)
        p.std_n_photons_per_shot = float(p.std_photon_fraction_opx) * p.n_photons_per_shot
        p.feedback_fractional_initial_offset = float(self.offset_r[0])
        p.feedback_guess_span_Omega = float(self.span_r[0])
        Feedback.__init__(self, lut_size=self._lut_size, expt_params=p)
        self._omega_resonance_rad_s = 2.0 * np.pi * float(p.frequency_raman_transition)

    # ------------------------------------------------------------------
    # replay engine
    # ------------------------------------------------------------------

    def _run(self, *, apd_rr, omega_override_rr, control_omega_source,
             use_actual_timestamps, include_photon_noise, update_raman_frequency,
             return_full_state) -> FeedbackOPXReplayResult:
        if control_omega_source not in ('measured', 'recomputed', 'override'):
            raise ValueError("control_omega_source must be measured (the applied "
                             "frequency), recomputed or override")
        self._reinit_params()
        if self.remesh:
            return self._run_remesh(apd_rr=apd_rr, control_omega_source=control_omega_source,
                                    use_actual_timestamps=use_actual_timestamps,
                                    include_photon_noise=include_photon_noise,
                                    update_raman_frequency=update_raman_frequency,
                                    return_full_state=return_full_state)
        n_shots, N, m = self.n_shots, self.N_step, int(self.m)
        Omega = float(self.Omega)
        omega_res = float(self._omega_resonance_rad_s)
        t_img = float(self.p.t_img_pulse)
        t_off = float(self.p.t_raman_pulse_offset)
        n_photons = float(self.N_photons_per_shot)

        t_in_rr, t_source = self._t_input_rr(use_actual_timestamps)
        d_rr = np.asarray(self.t_raman_pulse_rr, dtype=float)
        apd_rr = np.asarray(apd_rr, dtype=float)
        p_meas_rr = apd_volts_to_photon_fraction(apd_rr, self.v_apd_all_up, self.v_apd_all_down)
        k_rr = n_photons * p_meas_rr

        if control_omega_source == 'measured':
            omega_ctrl_rr = self.omega_applied_rr
            if omega_ctrl_rr is None:
                raise ValueError("no applied drive frequency (drive_index + "
                                 "if_table_hz / dif_hz / omega_raman) in the run file.")
        elif control_omega_source == 'override':
            if omega_override_rr is None:
                raise ValueError("control_omega_source='override' needs omega_control_rr")
            omega_ctrl_rr = np.asarray(omega_override_rr, dtype=float)
            if omega_ctrl_rr.ndim == 1:
                omega_ctrl_rr = np.tile(omega_ctrl_rr, (n_shots, 1))
        else:
            omega_ctrl_rr = None
        if update_raman_frequency is None:
            update_raman_frequency = bool(getattr(self.p, 'update_raman_frequency_bool', 1))

        valid = self.valid_r & np.all(np.isfinite(apd_rr), axis=1) \
            & np.all(np.isfinite(t_in_rr), axis=1)
        s_z_rr = np.full((n_shots, N), np.nan)
        P0_rr = np.full((n_shots, N, m), np.nan)
        omega_control_rr = np.full((n_shots, N), np.nan)
        omega_recomputed_rr = np.full((n_shots, N), np.nan)
        t_s_z_rr = np.full((n_shots, N), np.nan)
        state_rr = np.full((n_shots, N, 3), np.nan) if return_full_state else None
        n_floored = np.zeros((n_shots, N), dtype=int)
        control_snap = 0.0      # largest |w_control - nearest grid point| (emulation)

        c = self.constants() if self._fixed_point else None
        grid0, zidx0 = self._grid_for_shot(0)

        for r in range(n_shots):
            if not valid[r]:
                continue
            grid, zidx = self._grid_for_shot(r)
            w_grid = (grid - omega_res) / Omega
            t_in = t_in_rr[r]
            d = d_rr[r]
            t_s_z_rr[r] = t_in + d + t_img

            if self._fixed_point:
                a, b, dphi0, ddphi = self._corotating_tables(grid, t_in, d, c)
                st = FixedPointState.uniform(m)
                d_idx = nearest_grid_index(w_grid, float(self.offset_r[r]))
                for i in range(N):
                    if omega_ctrl_rr is not None:
                        w_c = (float(omega_ctrl_rr[r, i]) - omega_res) / Omega
                        d_idx = nearest_grid_index(w_grid, w_c)
                        control_snap = max(control_snap, abs(w_c - w_grid[d_idx]))
                    u = posterior_update_fixed_point_emulation(
                        st, d_idx, float(p_meas_rr[r, i]), a[i], b[i], dphi0[i],
                        ddphi[i], w_grid, c, zidx=zidx)
                    s_z_rr[r, i] = u['s_z']
                    P0_rr[r, i] = u['P0']
                    omega_control_rr[r, i] = omega_res + Omega * w_grid[d_idx]
                    omega_recomputed_rr[r, i] = omega_res + Omega * u['w_next']
                    n_floored[r, i] = u['n_floored']
                    if state_rr is not None:
                        state_rr[r, i] = (st.x[zidx], st.y[zidx], st.z[zidx])
                    if omega_ctrl_rr is None and update_raman_frequency:
                        d_idx = int(u['d_next'])
                continue

            self.omega_guess_list = grid
            self.omega_sq_list = grid * grid
            self.reset_feedback_state()
            self.omega_raman = omega_res + Omega * float(self.offset_r[r])
            for i in range(N):
                if omega_ctrl_rr is not None:
                    self.omega_raman = float(omega_ctrl_rr[r, i])
                omega_ctrl = float(self.omega_raman)
                self.t_raman_pulse_current = float(d[i])
                self.t_raman_pulse_ideal_current = float(d[i]) - t_off
                omega_new, _mn, _std = self.generate_posterior(
                    float(k_rr[r, i]), float(t_in[i]),
                    phase_raman_pulse_start=0.0,
                    update_raman_frequency=1 if update_raman_frequency else 0,
                    update_rabi_frequency=0,
                    include_photon_noise=1 if include_photon_noise else 0)
                self.omega_raman = float(omega_new)
                s_z_rr[r, i] = float(self.state_z[zidx])
                P0_rr[r, i] = self.P0
                omega_control_rr[r, i] = omega_ctrl
                omega_recomputed_rr[r, i] = float(self.omega_raman)
                if state_rr is not None:
                    state_rr[r, i] = (self.state_x[zidx], self.state_y[zidx],
                                      self.state_z[zidx])

        max_abs_dP = np.full(n_shots, np.nan)
        if self.P0_opx_rr is not None:
            dP = np.abs(P0_rr - self.P0_opx_rr)
            with np.errstate(invalid='ignore'):
                max_abs_dP = np.nanmax(dP.reshape(n_shots, -1), axis=1) \
                    if dP.size else max_abs_dP
            max_abs_dP[~valid] = np.nan

        # the schedule the OPX was held to, recomputed; the slip against the
        # actual starts (0 when the OPX kept to it)
        t_sched_rr = self.scheduled_starts_rr()
        slip = None
        if self.t_actual_rr is not None:
            slip = np.asarray(self.t_actual_rr, dtype=float) - t_sched_rr
        dT = np.full((n_shots, N), np.nan)
        dT[:, :-1] = np.diff(t_in_rr, axis=1) * 1e9

        return FeedbackOPXReplayResult(
            s_z_rr=s_z_rr, P0_rr=P0_rr, omega_control_rr=omega_control_rr,
            omega_recomputed_rr=omega_recomputed_rr, t_input_rr=t_in_rr,
            t_s_z_rr=t_s_z_rr, k_rr=k_rr, apd_rr=apd_rr,
            apd_norm_rr=self._normalize_apd(apd_rr), omega_guess_list=grid0,
            zidx=int(zidx0), state_rr=state_rr, t_raman_pulse_rr=d_rr,
            dT_mu_rr=dT,
            metadata={
                'run_id': self._run_id, 'N_repeat': n_shots, 'N_step': N,
                'feedback_grid_size': m, 'phase_model': 'reset',
                'phase_raman_pulse_start': 0.0, 't_source': t_source,
                'control_omega_source': control_omega_source,
                'fixed_point_emulation': bool(self._fixed_point),
                'update_raman_frequency': bool(update_raman_frequency),
                'include_photon_noise': bool(include_photon_noise),
                'n_floored': n_floored,
                'control_snap_Omega': float(control_snap),
                'n_valid': int(np.sum(valid)),
                't_raman_pulse_seed': (self.t_raman_pulse_seed_r.tolist()
                                       if self.t_raman_pulse_seed_r is not None else None),
            },
            t_pulse_start_rr=self.t_actual_rr, slip_rr=slip,
            log_weights_opx_rr=self.L_opx_rr, log_weight_scale=self.log_weight_scale,
            P0_opx_rr=self.P0_opx_rr, drive_index_rr=self.drive_index_rr,
            max_abs_dP_r=max_abs_dP, valid_r=valid,
            omega_applied_rr=self.omega_applied_rr, t_scheduled_rr=t_sched_rr)

    def _run_remesh(self, *, apd_rr, control_omega_source, use_actual_timestamps,
                    include_photon_noise, update_raman_frequency, return_full_state
                    ) -> FeedbackOPXReplayResult:
        """The remesh replay. control_omega_source 'measured': the recorded
        decisions (drives, pole pulse, its level, the fine grid) are played
        and every continuous quantity recomputed -- the replay's own
        decisions on that trajectory are reported next to the recorded ones;
        'recomputed': the replay decides everything from the recorded APD.
        Both engines: the fixed-point emulation (run_shot_fixed_point_emulation
        with remesh / follow) and the double-precision posterior
        (_double_remesh_shot). What was PLAYED (durations, grid and lattice
        frequencies, pole durations, schedule) comes from the run's own
        params and the saved seeds; the MODEL (resonance, Omega, the switch
        offset, noise, light shift, coherence, the decision rules) from
        fr.p, alike in both engines. Structural edits are refused
        (STRUCTURAL_KEYS_REMESH)."""
        if control_omega_source == 'override':
            raise ValueError("control_omega_source='override' is not available for "
                             "remesh runs (the grid changes mid-shot).")
        if update_raman_frequency is not None and not update_raman_frequency:
            raise ValueError("the remesh is closed-loop only.")
        if return_full_state:
            raise ValueError("[opx replay] return_full_state is not available for remesh "
                             "runs (the hypothesis set changes at the pole pulse).")
        self._check_structure()
        n_shots, N, m = self.n_shots, self.N_step, int(self.m)
        Omega = float(self.Omega)
        omega_res = float(self._omega_resonance_rad_s)
        t_img = float(self.p.t_img_pulse)
        c = self.constants()                  # the model: decision rules, noise, numerics
        T, cr = self._T_run, self._c_run      # what was played
        t_in_rr, t_source = self._t_input_rr(use_actual_timestamps)
        apd_rr = np.asarray(apd_rr, dtype=float)
        p_meas_rr = apd_volts_to_photon_fraction(apd_rr, self.v_apd_all_up, self.v_apd_all_down)
        follow_mode = control_omega_source == 'measured'
        valid = self.valid_r & np.all(np.isfinite(apd_rr), axis=1) \
            & np.all(np.isfinite(t_in_rr), axis=1)
        s_z_rr = np.full((n_shots, N), np.nan)
        on_grid_rr = np.full((n_shots, N), np.nan)
        P0_rr = np.full((n_shots, N, m), np.nan)
        mesh_rr = np.full((n_shots, N, m), np.nan)
        om_ctrl_rr = np.full((n_shots, N), np.nan)
        om_next_rr = np.full((n_shots, N), np.nan)
        d_applied_rr = np.full((n_shots, N), np.nan)
        n_floored = np.zeros((n_shots, N), dtype=int)
        dec = {k: np.full(n_shots, -1, dtype=np.int64) for k in
               ('pulse', 'n0', 'pole_level', 'own_pulse', 'own_n0', 'own_pole_level')}
        s0_r = np.full(n_shots, np.nan)
        metric_r = np.full(n_shots, np.nan)       # trigger value at the played trigger pulse
        own_metric_r = np.full(n_shots, np.nan)   # at the replay's own trigger pulse
        pole_d = T.pole_d_cc.astype(float) * CLOCK_NS * 1e-9
        for r in range(n_shots):
            if not valid[r]:
                continue
            t_in = t_in_rr[r]
            gap_last = int(feedback_step_gaps_cc(T.d_cc[r, -1:], cr.t_img_cc, cr.budget_cc,
                                                 cr.overhead_cc, cr.extra_gap_cc,
                                                 cr.edge_cc)[0])
            t_ext = np.concatenate([t_in, [t_in[-1] + gap_last * CLOCK_NS * 1e-9]])
            w_grid, a, b, dphi0, ddphi, rm = self._remesh_shot_inputs(r, t_ext)
            follow = None
            if follow_mode:
                follow = dict(drives=self.drive_index_rr[r],
                              remesh_pulse=int(self.remesh_pulse_r[r]),
                              remesh_n0=int(self.remesh_n0_r[r]),
                              pole_level=int(self.remesh_pole_level_r[r]))
            if self._fixed_point:
                out = run_shot_fixed_point_emulation(
                    w_grid, int(T.zidx[r]), a, b, dphi0, ddphi, c,
                    lambda i, w_d, _r=r: float(p_meas_rr[_r, i]), d_init=int(T.d_init[r]),
                    remesh=rm, follow=follow)
                out['omega_control'] = omega_res + Omega * out['w_used']
                out['mesh'] = omega_res + Omega * out['grid']
                out['omega_next'] = omega_res + Omega * out['w_next']
                n_floored[r] = out['n_floored']
            else:
                out = self._double_remesh_shot(r, t_in, t_ext, p_meas_rr[r], rm, follow, c,
                                               include_photon_noise)
            P0_rr[r], s_z_rr[r], mesh_rr[r] = out['P0'], out['s_z'], out['mesh']
            on_grid_rr[r] = out['s_z_on_grid']
            om_ctrl_rr[r], om_next_rr[r] = out['omega_control'], out['omega_next']
            fired_r = out['remesh_pulse'] >= 0
            dec['pulse'][r] = out['remesh_pulse']
            dec['n0'][r] = out['remesh_n0'] if fired_r else -1
            dec['pole_level'][r] = out['remesh_pole_level']
            s0_r[r] = out['remesh_s0'] if fired_r else np.nan
            metric_r[r] = out['remesh_trigger_metric']
            if follow_mode:
                dec['own_pulse'][r] = (out['own_trigger_pulse'] + 1
                                       if out['own_trigger_pulse'] >= 0 else -1)
                dec['own_n0'][r] = out['own_n0']
                dec['own_pole_level'][r] = out['own_pole_level']
                own_metric_r[r] = out['own_trigger_metric']
            else:
                dec['own_pulse'][r] = dec['pulse'][r]
                dec['own_n0'][r] = dec['n0'][r]
                dec['own_pole_level'][r] = dec['pole_level'][r]
                own_metric_r[r] = metric_r[r]
            d_app = np.asarray(T.d_s[r], dtype=float).copy()
            if fired_r:
                d_app[out['remesh_pulse']] = pole_d[out['remesh_pole_level']]
            d_applied_rr[r] = d_app

        # recorded vs the replay's own decisions (a shot that never fired
        # records pulse -1; n0 / level are compared only where it fired)
        rec_p = np.where(valid, self.remesh_pulse_r, -1)
        rec_fired = rec_p >= 0
        agree = (dec['own_pulse'] == rec_p) & (~rec_fired | (
            (dec['own_pole_level'] == self.remesh_pole_level_r)
            & (dec['own_n0'] == self.remesh_n0_r)))
        agree &= valid
        # the recorded trigger value in physical units (the run's trigger
        # mode: var(w/4) -> std in Omega; L/s -> nats), as the finish hook
        raw = np.where(rec_fired, self.remesh_trigger_r, np.nan)
        if int(cr.reinit_trigger_mode) == 0:
            rec_metric = 4.0 * np.sqrt(np.maximum(raw, 0.0))
        else:
            rec_metric = raw * float(cr.scale)
        # the recorded s_z's meaning: 0 where the OPX saved the fine grid's
        # edge hypothesis (resonance off the fine grid), as the finish hook
        rec_on = np.full((n_shots, N), np.nan)
        for r in np.flatnonzero(valid):
            rec_on[r] = 1.0
            if rec_p[r] >= 0 and not 0 <= int(T.n_res[r]) - int(self.remesh_n0_r[r]) <= m - 1:
                rec_on[r, rec_p[r]:] = 0.0
        # s0 is compared only where the replay played the recorded pole pulse
        same = rec_fired & valid & (dec['pulse'] == rec_p)
        remesh_info = dict(
            recorded=dict(pulse=rec_p, n0=np.where(rec_fired, self.remesh_n0_r, -1),
                          pole_level=np.where(rec_fired, self.remesh_pole_level_r, -1),
                          s0=np.where(rec_fired, self.remesh_s0_r, np.nan),
                          trigger=raw, trigger_metric=rec_metric, s_z_on_grid=rec_on),
            replay=dict(pulse=dec['own_pulse'], n0=dec['own_n0'],
                        pole_level=dec['own_pole_level'], s0=s0_r,
                        trigger_metric=own_metric_r, s_z_on_grid=on_grid_rr),
            played=dict(pulse=dec['pulse'], n0=dec['n0'], pole_level=dec['pole_level'],
                        trigger_metric=metric_r),
            decisions_agree_r=agree,
            n_agree=int(np.sum(agree)), n_valid=int(np.sum(valid)),
            s0_max_abs_diff=(float(np.nanmax(np.abs(s0_r - self.remesh_s0_r)[same]))
                             if np.any(same) else np.nan),
            n_s0_compared=int(np.sum(same)),
            excluded=dict(getattr(self, 'remesh_excluded', {})))

        max_abs_dP = np.full(n_shots, np.nan)
        if self.P0_opx_rr is not None:
            dP = np.abs(P0_rr - self.P0_opx_rr)
            with np.errstate(invalid='ignore'):
                max_abs_dP = np.nanmax(dP.reshape(n_shots, -1), axis=1) if dP.size else max_abs_dP
            max_abs_dP[~valid] = np.nan
        t_sched_rr = self.scheduled_starts_rr()
        slip = (np.asarray(self.t_actual_rr, dtype=float) - t_sched_rr
                if self.t_actual_rr is not None else None)
        dT = np.full((n_shots, N), np.nan)
        dT[:, :-1] = np.diff(t_in_rr, axis=1) * 1e9
        return FeedbackOPXReplayResult(
            s_z_rr=s_z_rr, P0_rr=P0_rr, omega_control_rr=om_ctrl_rr,
            omega_recomputed_rr=om_next_rr, t_input_rr=t_in_rr,
            t_s_z_rr=t_in_rr + d_applied_rr + t_img,
            k_rr=float(self.N_photons_per_shot) * p_meas_rr,
            apd_rr=apd_rr, apd_norm_rr=self._normalize_apd(apd_rr),
            omega_guess_list=T.omega_grid[0], zidx=int(T.zidx[0]), state_rr=None,
            t_raman_pulse_rr=d_applied_rr, dT_mu_rr=dT,
            metadata={
                'run_id': self._run_id, 'N_repeat': n_shots, 'N_step': N,
                'feedback_grid_size': m, 'phase_model': 'reset',
                'phase_raman_pulse_start': 0.0, 't_source': t_source,
                'control_omega_source': control_omega_source,
                'fixed_point_emulation': bool(self._fixed_point),
                'update_raman_frequency': True,
                'include_photon_noise': bool(include_photon_noise),
                'n_floored': n_floored,
                'control_snap_Omega': 0.0,      # the drives are recorded grid indices
                'n_valid': int(np.sum(valid)), 'remesh': True,
                't_raman_pulse_seed': (self.t_raman_pulse_seed_r.tolist()
                                       if self.t_raman_pulse_seed_r is not None else None),
            },
            t_pulse_start_rr=self.t_actual_rr, slip_rr=slip,
            log_weights_opx_rr=self.L_opx_rr, log_weight_scale=self.log_weight_scale,
            P0_opx_rr=self.P0_opx_rr, drive_index_rr=self.drive_index_rr,
            max_abs_dP_r=max_abs_dP, valid_r=valid,
            omega_applied_rr=self.omega_applied_rr, t_scheduled_rr=t_sched_rr,
            mesh_rr=mesh_rr, remesh=remesh_info)

    def _double_remesh_shot(self, r, t_in, t_ext, p_meas, rm, follow, c,
                            include_photon_noise=True):
        """One remesh shot with the double-precision posterior
        (generate_posterior, phase 0) and exact math for the trigger and
        the pole angle -- from the lab-frame state rotated into the next
        pulse's drive frame (Rz(-phi_{j,i+1}), phi = -omega_j t_{i+1}) --
        and the OPX's grid / interpolation / reset rules. rm: the shot's
        inputs from _remesh_shot_inputs (played frequencies and durations,
        model pole rotations). follow: the recorded decisions, played with
        the recorded APPLIED frequency (the integer-Hz drive, as the
        non-remesh measured replay)."""
        T = self._T_run
        m, N, R = int(self.m), self.N_step, int(self._c_run.remesh_ratio)
        n_pole = int(np.asarray(rm['pole_a']).size)
        Omega = float(self.Omega)
        omega_res = float(self._omega_resonance_rad_s)
        t_off = float(self.p.t_raman_pulse_offset)
        n_ph = float(self.N_photons_per_shot)
        grid = np.asarray(T.omega_grid[r], dtype=float).copy()
        self.omega_guess_list = grid
        self.omega_sq_list = grid * grid
        self.reset_feedback_state()
        pole_d_s = np.asarray(rm['pole_d_s'], dtype=float)
        pole_a = np.asarray(rm['pole_a'], dtype=float)
        zidx0, n_res = int(T.zidx[r]), int(rm['n_res'])
        n0, sp, pole_now, fired, pole_k, sz_lat = 0, 0, False, False, 0, 0.0
        out = dict(P0=np.full((N, m), np.nan), s_z=np.full(N, np.nan),
                   s_z_on_grid=np.ones(N, dtype=bool),
                   mesh=np.full((N, m), np.nan), omega_control=np.full(N, np.nan),
                   omega_next=np.full(N, np.nan), remesh_pulse=-1, remesh_n0=0,
                   remesh_pole_level=-1, remesh_s0=0.0, remesh_trigger_metric=np.nan,
                   own_trigger_pulse=-1, own_pole_level=-1, own_n0=-1,
                   own_trigger_metric=np.nan)
        f_p = int(follow['remesh_pulse']) if follow is not None else None
        d = int(T.d_init[r])
        own_fired = False
        for i in range(N):
            if follow is not None:
                d = int(follow['drives'][i])
                pole_now = (i == f_p)
                if pole_now:
                    pole_k = int(follow['pole_level'])
                omega_ctrl = float(self.omega_applied_rr[r, i])
            else:
                omega_ctrl = float(grid[d])
            dur = pole_d_s[pole_k] if pole_now else float(T.d_s[r, i])
            self.omega_raman = omega_ctrl
            self.t_raman_pulse_current = dur
            self.t_raman_pulse_ideal_current = dur - t_off
            self.generate_posterior(n_ph * float(p_meas[i]), float(t_in[i]),
                                    phase_raman_pulse_start=0.0, update_raman_frequency=1,
                                    update_rabi_frequency=0,
                                    include_photon_noise=1 if include_photon_noise else 0)
            out['omega_control'][i] = omega_ctrl
            jmax = int(np.argmax(self.P0))
            if pole_now:
                pmu = float(np.clip(p_meas[i], P_MEAS_CLAMP[0], P_MEAS_CLAMP[1]))
                s0 = (float(np.clip(2.0 * pmu - 1.0, -1.0, 1.0))
                      if int(c.reinit_state_source) == 0 else sz_lat)
                n0_rule = int(np.clip(jmax * R - (m - 1) // 2, 0, (m - 1) * (R - 1)))
                n0 = int(follow['remesh_n0']) if follow is not None else n0_rule
                lp = np.log(np.maximum(self.P0, 1e-300))
                pos = n0 + np.arange(m)
                k, f = pos // R, (pos % R) / R
                k1 = np.minimum(k + 1, m - 1)
                Ln = lp[k] + f * (lp[k1] - lp[k])
                Pn = np.exp(Ln - np.max(Ln))
                self.P0[:] = Pn / np.sum(Pn)
                self.state_x[:] = 0.0
                self.state_y[:] = 0.0
                self.state_z[:] = s0
                grid = np.asarray(rm['lat_abs'], dtype=float)[n0 + np.arange(m)]
                self.omega_guess_list = grid
                self.omega_sq_list = grid * grid
                jmax = int(np.argmax(self.P0))
                sp, pole_now = 1, False
                out.update(remesh_pulse=i, remesh_n0=n0, remesh_pole_level=pole_k, remesh_s0=s0,
                           own_n0=n0_rule)
            out['P0'][i] = self.P0
            out['mesh'][i] = grid
            if sp == 0:
                jr = zidx0
            else:
                jr = min(max(n_res - n0, 0), m - 1)
                out['s_z_on_grid'][i] = 0 <= n_res - n0 <= m - 1
            out['s_z'][i] = float(self.state_z[jr])
            active = (not fired) if follow is None else (f_p < 0 or i < f_p)
            if active:
                P = np.asarray(self.P0, dtype=float)
                w = (grid - omega_res) / Omega
                if int(c.reinit_trigger_mode) == 0:
                    mean = float(np.sum(P * w))
                    metric = float(np.sqrt(max(float(np.sum(P * w * w)) - mean * mean, 0.0)))
                    ok = metric < float(c.reinit_std_thr)
                else:
                    outside = np.abs(np.arange(m) - jmax) > int(c.reinit_margin_excl)
                    pout = float(np.max(P[outside])) if outside.any() else 0.0
                    metric = float(np.log(P[jmax] / pout)) if pout > 0 else 100.0
                    ok = metric >= float(c.reinit_margin_s) * float(c.scale)
                forced = int(c.reinit_force_pulse) > 0 and i >= int(c.reinit_force_pulse) - 1
                window = int(c.reinit_min_pulse) - 1 <= i <= N - 3
                phi = 2.0 * np.pi * np.mod(-(grid / (2.0 * np.pi)) * t_ext[i + 1], 1.0)
                a = -np.sin(phi) * self.state_x + np.cos(phi) * self.state_y
                b = np.asarray(self.state_z, dtype=float)
                if int(c.reinit_method) == 0:
                    th = -np.arctan2(a[jmax], b[jmax]) / (2.0 * np.pi)
                else:
                    th = 0.5 * np.arctan2(-2.0 * np.sum(P * a * b),
                                          np.sum(P * b * b) - np.sum(P * a * a)) / (2.0 * np.pi)
                th = th + 0.5 if th < 0.0 else th
                th = th - 0.5 if th >= 0.5 else th
                kst = int(np.clip(np.floor(2 * (n_pole - 1) * (th + 1.0 / (4.0 * (n_pole - 1)))),
                                  0, n_pole - 1))
                k_sz = kst if follow is None or i != f_p - 1 else int(follow['pole_level'])
                cp, sp_ = np.cos(2.0 * np.pi * pole_a[k_sz]), np.sin(2.0 * np.pi * pole_a[k_sz])
                szp = (float(b[jmax] * cp - a[jmax] * sp_) if int(c.reinit_method) == 0
                       else float(np.sum(P * (b * cp - a * sp_))))
                would = window and (ok or forced)
                if follow is None:
                    if would:
                        pole_now, fired, pole_k, sz_lat = True, True, kst, szp
                        out['remesh_trigger_metric'] = metric
                else:
                    if would and not own_fired:
                        own_fired = True
                        out['own_trigger_pulse'] = i
                        out['own_pole_level'] = kst
                        out['own_trigger_metric'] = metric
                    if i == f_p - 1:
                        sz_lat = szp
                        out['remesh_trigger_metric'] = metric
            out['omega_next'][i] = float(grid[jmax])
            if follow is None:
                d = jmax
        return out

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def replay_measured(self, *, control_omega_source='measured',
                        use_actual_timestamps=None, include_photon_noise=True,
                        update_raman_frequency=None, return_full_state=False
                        ) -> FeedbackOPXReplayResult:
        """Replay the recorded run: measured APD, the drive per pulse from
        the exact applied integer-Hz frequency ('measured') or the replay's
        own choice ('recomputed'), pulse starts from the actual timestamps
        (default) or the recomputed schedule. Compares against the OPX's own
        posterior (max_abs_dP_r)."""
        return self._run(apd_rr=self.apd_rr, omega_override_rr=None,
                         control_omega_source=control_omega_source,
                         use_actual_timestamps=use_actual_timestamps,
                         include_photon_noise=include_photon_noise,
                         update_raman_frequency=update_raman_frequency,
                         return_full_state=return_full_state)

    def simulate_counterfactual(self, *, apd_input_rr=None, omega_control_rr=None,
                                control_omega_source='recomputed',
                                use_actual_timestamps=None,
                                include_photon_noise=True,
                                update_raman_frequency=None,
                                return_full_state=False) -> FeedbackOPXReplayResult:
        """What-if with modified self.p values and/or substituted inputs:
        apd_input_rr (volts, (n_shots, N) or (N,)) replaces the recorded
        APD; omega_control_rr (rad/s) with control_omega_source='override'
        replaces the drive schedule (the emulation snaps it to the nearest
        grid index; metadata['control_snap_Omega'] records how far)."""
        apd = self.apd_rr if apd_input_rr is None else np.asarray(apd_input_rr, dtype=float)
        if apd.ndim == 1:
            apd = np.tile(apd, (self.n_shots, 1))
        return self._run(apd_rr=apd, omega_override_rr=omega_control_rr,
                         control_omega_source=control_omega_source,
                         use_actual_timestamps=use_actual_timestamps,
                         include_photon_noise=include_photon_noise,
                         update_raman_frequency=update_raman_frequency,
                         return_full_state=return_full_state)

    def simulate_feedback_run_apd(self, *, detuning_offset_Omega=0.0, seed=0,
                                  noise_scale=1.0, include_photon_noise=True,
                                  omega_control_rr=None, use_actual_timestamps=None,
                                  fixed_point=None) -> Dict[str, object]:
        """Synthetic closed-loop run with a known injected resonance
        (detuning_offset_Omega away from p.frequency_raman_transition), the
        reset model and this run's pulse schedule: the true Bloch vector is
        stepped with drive phase 0 (true_bloch_step), a photon fraction is
        drawn with sigma_p * noise_scale, and the controller (the
        double-precision posterior, or the OPX emulation when fixed_point /
        emulate_fixed_point is on) picks the next drive.
        omega_control_rr (rad/s) forces an open-loop drive schedule.
        Returns apd_rr (OPX volts), omega_control_rr, s_z_true_rr,
        p_meas_rr, omega_true_rad_s, detuning_offset_Omega."""
        if self.remesh:
            raise NotImplementedError(
                "simulate_feedback_run_apd does not simulate the remesh (pole pulse, "
                "grid change); run_shot_fixed_point_emulation(..., remesh=...) with a "
                "synthetic measure does.")
        self._reinit_params()
        n_shots, N, m = self.n_shots, self.N_step, int(self.m)
        Omega = float(self.Omega)
        omega_res = float(self._omega_resonance_rad_s)
        t_img = float(self.p.t_img_pulse)
        t_off = float(self.p.t_raman_pulse_offset)
        use_fp = self._fixed_point if fixed_point is None else bool(fixed_point)
        c = self.constants() if use_fp else None
        omega_true = omega_res + Omega * float(detuning_offset_Omega)
        sigma_p = float(self.std_n_photons_per_shot) / float(self.N_photons_per_shot)
        sigma_p *= float(noise_scale)
        v_up, v_down = float(self.v_apd_all_up), float(self.v_apd_all_down)
        t_in_rr, _src = self._t_input_rr(use_actual_timestamps)
        d_rr = np.asarray(self.t_raman_pulse_rr, dtype=float)
        rng = np.random.default_rng(int(seed))
        fixed = None
        if omega_control_rr is not None:
            fixed = np.asarray(omega_control_rr, dtype=float)
            if fixed.ndim == 1:
                fixed = np.tile(fixed, (n_shots, 1))

        apd_rr = np.full((n_shots, N), np.nan)
        omega_ctrl_out = np.full((n_shots, N), np.nan)
        s_z_true_rr = np.full((n_shots, N), np.nan)
        p_meas_rr = np.full((n_shots, N), np.nan)
        for r in range(n_shots):
            t_in = t_in_rr[r]
            if not np.all(np.isfinite(t_in)):
                continue
            grid, zidx = self._grid_for_shot(r)
            w_grid = (grid - omega_res) / Omega
            d = d_rr[r]
            s = (0.0, 0.0, 1.0)
            if use_fp:
                st = FixedPointState.uniform(m)
                a, b, dphi0, ddphi = self._corotating_tables(grid, t_in, d, c)
                d_idx = nearest_grid_index(w_grid, float(self.offset_r[r]))
                omega_ctrl = omega_res + Omega * float(w_grid[d_idx])
            else:
                self.omega_guess_list = grid
                self.omega_sq_list = grid * grid
                self.reset_feedback_state()
                omega_ctrl = omega_res + Omega * float(self.offset_r[r])
            for i in range(N):
                if fixed is not None:
                    omega_ctrl = float(fixed[r, i])
                    if use_fp:
                        d_idx = nearest_grid_index(w_grid, (omega_ctrl - omega_res) / Omega)
                        omega_ctrl = omega_res + Omega * float(w_grid[d_idx])
                hz, s = true_bloch_step(s, omega_ctrl, omega_true, d[i] - t_off, d[i],
                                        t_in[i], Omega, self.omega_z_lightshift,
                                        t_img, self.back_action_coherence)
                p1 = float(self.expected_photon_fraction(hz))
                p_meas = p1 + (rng.normal(0.0, sigma_p) if include_photon_noise
                               and sigma_p > 0 else 0.0)
                v = v_down + p_meas * (v_up - v_down)
                apd_rr[r, i], omega_ctrl_out[r, i] = v, omega_ctrl
                s_z_true_rr[r, i], p_meas_rr[r, i] = hz, p_meas
                if use_fp:
                    u = posterior_update_fixed_point_emulation(
                        st, d_idx, p_meas, a[i], b[i], dphi0[i], ddphi[i], w_grid, c,
                        zidx=zidx)
                    if fixed is None:
                        d_idx = int(u['d_next'])
                        omega_ctrl = omega_res + Omega * float(w_grid[d_idx])
                else:
                    self.omega_raman = omega_ctrl
                    self.t_raman_pulse_current = float(d[i])
                    self.t_raman_pulse_ideal_current = float(d[i]) - t_off
                    omega_new, _mn, _std = self.generate_posterior(
                        float(self.N_photons_per_shot) * p_meas, float(t_in[i]),
                        phase_raman_pulse_start=0.0,
                        update_raman_frequency=0 if fixed is not None else 1,
                        update_rabi_frequency=0,
                        include_photon_noise=1 if include_photon_noise else 0)
                    if fixed is None:
                        omega_ctrl = float(omega_new)
        return {'apd_rr': apd_rr, 'omega_control_rr': omega_ctrl_out,
                's_z_true_rr': s_z_true_rr, 'p_meas_rr': p_meas_rr,
                'omega_true_rad_s': omega_true,
                'detuning_offset_Omega': float(detuning_offset_Omega)}

    def compare_with_opx(self, result: Optional[FeedbackOPXReplayResult] = None,
                         verbose=True) -> Dict[str, object]:
        """How far the replay's posterior is from the OPX's own (P0 derived
        from log_weights): max/mean |dP|, the argmax agreement fraction
        (>= ARGMAX_AGREEMENT_EXPECTED = 99 % is the expected outcome: QUA's
        2^-28 rounding flips ~1 % of near-tie decisions against a
        double-precision replay), the worst shot and pulse, the largest
        schedule slip. Pulses where the OPX's saved posterior has an EXACT
        tie at its maximum (pulse 0 of a uniform prior is symmetric about the
        drive) are decided by the tie rule alone -- Math.argmax's is assumed
        to be the first index, unverified -- so they are counted separately
        (n_argmax_exact_ties) and left out of the agreement fraction. Prints
        one line."""
        if result is None:
            result = self.replay_measured()
        out = {'n_shots': self.n_shots, 'n_valid': int(np.sum(result.valid_r)),
               'argmax_agreement_expected': ARGMAX_AGREEMENT_EXPECTED}
        if result.P0_opx_rr is None:
            out['summary'] = "[opx replay] no OPX posterior in the run file to compare with"
            if verbose:
                print(out['summary'])
            return out
        valid = result.valid_r
        dP = np.abs(result.P0_rr[valid] - result.P0_opx_rr[valid])
        P_o = result.P0_opx_rr[valid]
        am_r = np.argmax(result.P0_rr[valid], axis=-1)
        am_o = np.argmax(P_o, axis=-1)
        # an exact tie at the maximum of the OPX's own posterior (its L are
        # 2^-28 multiples, so a tie is equality of the saved values)
        top = np.max(P_o, axis=-1, keepdims=True)
        tied = np.sum(P_o == top, axis=-1) > 1
        fin = np.isfinite(dP)
        out['max_abs_dP'] = float(np.max(dP[fin])) if fin.any() else np.nan
        out['mean_abs_dP'] = float(np.mean(dP[fin])) if fin.any() else np.nan
        keep = ~tied
        frac = float(np.mean(am_r[keep] == am_o[keep])) if np.any(keep) else np.nan
        out['argmax_agreement_fraction'] = frac
        out['argmax_ok'] = bool(np.isfinite(frac) and frac >= ARGMAX_AGREEMENT_EXPECTED)
        out['n_argmax_disagree'] = int(np.sum((am_r != am_o) & keep)) if am_r.size else 0
        out['n_argmax_exact_ties'] = int(np.sum(tied))
        out['n_argmax_ties_disagree'] = int(np.sum((am_r != am_o) & tied))
        if fin.any():
            worst = np.unravel_index(int(np.nanargmax(np.where(fin, dP, -1.0))), dP.shape)
            out['worst_shot'] = int(np.flatnonzero(valid)[worst[0]])
            out['worst_pulse'] = int(worst[1])
        if result.slip_rr is not None:
            s = result.slip_rr[valid]
            s = s[np.isfinite(s)]
            out['slip_max_cycles'] = float(np.max(np.abs(s)) / 4e-9) if s.size else np.nan
        out['summary'] = (
            f"[opx replay] run {self._run_id}: {out['n_valid']}/{out['n_shots']} shots, "
            f"max |dP| = {out['max_abs_dP']:.2e}, mean |dP| = {out['mean_abs_dP']:.2e}, "
            f"argmax agreement {100 * frac:.1f}% "
            f"({out['n_argmax_disagree']} of {int(np.sum(keep))} untied pulses differ; "
            f">= {100 * ARGMAX_AGREEMENT_EXPECTED:.0f}% expected"
            + ("" if out['argmax_ok'] else ", BELOW that")
            + (f"; {out['n_argmax_exact_ties']} exact tie(s) in the OPX posterior, "
               f"{out['n_argmax_ties_disagree']} decided differently -- tie rule "
               f"unverified" if out['n_argmax_exact_ties'] else '')
            + ")"
            + (f", max slip {out['slip_max_cycles']:.1f} cycles"
               if 'slip_max_cycles' in out and np.isfinite(out['slip_max_cycles']) else '')
            + (" [fixed-point emulation]" if result.metadata.get('fixed_point_emulation') else ''))
        if result.remesh is not None:
            rm = result.remesh
            out['remesh_decisions_agree'] = int(rm['n_agree'])
            out['remesh_n_valid'] = int(rm['n_valid'])
            out['remesh_s0_max_abs_diff'] = rm['s0_max_abs_diff']
            n_exc = sum(len(v) for v in rm.get('excluded', {}).values())
            out['remesh_n_excluded'] = n_exc
            out['summary'] += (
                f"; remesh decisions (pole pulse, level, fine grid) of the replay = the "
                f"recorded ones on {rm['n_agree']}/{rm['n_valid']} shots"
                + (f", max |s0 - recorded| {rm['s0_max_abs_diff']:.1e} over "
                   f"{rm['n_s0_compared']} shot(s)"
                   if np.isfinite(rm['s0_max_abs_diff']) else '')
                + (f", {n_exc} shot(s) EXCLUDED for impossible recorded decisions"
                   if n_exc else ''))
        if verbose:
            print(out['summary'])
        return out
