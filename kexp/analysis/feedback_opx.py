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
    P_MEAS_CLAMP, LOG_WEIGHT_SCALE)
from kexp.control.opx.units import CLOCK_NS

__all__ = [
    'FeedbackOPXReplay', 'FeedbackOPXReplayResult',
    'FixedPointState', 'FixedPointRangeError',
    'posterior_update_fixed_point_emulation',
    'run_shot_fixed_point_emulation', 'true_bloch_step',
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


def run_shot_fixed_point_emulation(w_grid, zidx, a, b, dphi0, ddphi, c,
                                   measure: Callable[[int, float], float],
                                   d_init=None, d_sched=None) -> Dict[str, np.ndarray]:
    """One shot of the OPX loop in the float64 emulation.

    a, b, dphi0, ddphi: (N,) per-pulse tables. measure(i, w_d) -> p_meas of
    pulse i under the drive w_d = w_grid[d] (a recorded value, or a
    synthetic detector stepping the true state). Closed loop when d_sched
    is None (first drive index d_init, then d_next); open loop drives
    d_sched[i] and still runs the posterior. Returns per-pulse arrays:
    w_used, d_used, p_meas, s_z, L (N, m; the saved max-normalised L/s),
    P0 (N, m), w_next, d_next, flat, n_floored.
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
    for i in range(N):
        if d_sched is not None:
            d = int(d_sched[i])
        p_meas = float(measure(i, float(w_grid[d])))
        u = posterior_update_fixed_point_emulation(
            st, d, p_meas, a[i], b[i], dphi0[i], ddphi[i], w_grid, c, zidx=zidx)
        out['w_used'][i] = w_grid[d]
        out['d_used'][i] = d
        out['p_meas'][i] = p_meas
        out['s_z'][i] = u['s_z']
        out['L'][i] = u['L']
        out['P0'][i] = u['P0']
        out['w_next'][i] = u['w_next']
        out['d_next'][i] = u['d_next']
        out['flat'][i] = u['flat']
        out['n_floored'][i] = u['n_floored']
        if d_sched is None:
            d = int(u['d_next'])
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
        N = int(p.N_pulses)
        m = int(p.feedback_grid_size)

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
        sequence computed it (step gaps from the pulse-time list)."""
        return scheduled_pulse_starts_s(self.p, self.t_raman_pulse_rr)

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
        """Re-run Feedback's initialisation on the (possibly edited) self.p."""
        p = self.p
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
        schedule slip. Prints one line."""
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
        am_r = np.argmax(result.P0_rr[valid], axis=-1)
        am_o = np.argmax(result.P0_opx_rr[valid], axis=-1)
        fin = np.isfinite(dP)
        out['max_abs_dP'] = float(np.max(dP[fin])) if fin.any() else np.nan
        out['mean_abs_dP'] = float(np.mean(dP[fin])) if fin.any() else np.nan
        frac = float(np.mean(am_r == am_o)) if am_r.size else np.nan
        out['argmax_agreement_fraction'] = frac
        out['argmax_ok'] = bool(np.isfinite(frac) and frac >= ARGMAX_AGREEMENT_EXPECTED)
        out['n_argmax_disagree'] = int(np.sum(am_r != am_o)) if am_r.size else 0
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
            f"({out['n_argmax_disagree']} of {am_r.size} pulses differ; "
            f">= {100 * ARGMAX_AGREEMENT_EXPECTED:.0f}% expected"
            + ("" if out['argmax_ok'] else ", BELOW that")
            + ")"
            + (f", max slip {out['slip_max_cycles']:.1f} cycles"
               if 'slip_max_cycles' in out and np.isfinite(out['slip_max_cycles']) else '')
            + (" [fixed-point emulation]" if result.metadata.get('fixed_point_emulation') else ''))
        if verbose:
            print(out['summary'])
        return out
