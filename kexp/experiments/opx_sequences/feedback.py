"""Bayesian frequency feedback on the OPX ("reset" phase model).

The per-shot body of HF_experiments/feedback/base_expt_feedback.py's
feedback_loop, moved from the ARTIQ kernel onto the OPX: ARTIQ prepares one
spin-polarised ensemble and hands off; the OPX then runs N_pulses cycles of

    [Raman pulse of a host-drawn random duration at the current drive
     frequency] -> [imaging exposure integrated on the APD] -> [Bayesian
    update of the m-point posterior in QUA fixed point] -> [next drive =
    the posterior argmax grid point]

and hands back. The physics and every sign convention are those of
kexp/base/feedback.py::Feedback.generate_posterior (the oracle); the
fixed-point form below (design spec section 4.4 as amended by the pass-3b
speed pass) is emulated in float64 by
kexp.analysis.feedback_opx.posterior_update_fixed_point_emulation, which
the offline tests compare against generate_posterior.

Phase model (D4, "reset")
-------------------------
Immediately before every pulse both Raman analog drives get reset_if_phase,
applied by align(raman_80, raman_150, raman_switch), and the 'pass' play is
the next statement on the switch element. The two-photon drive phase at the
start of every pulse is therefore 0 (plus a hardware constant common to all
pulses, which a z-rotation-invariant measurement of a pole-initialised state
cannot see). The posterior uses phase_raman_pulse_start = 0 and the
hypothesis term phi_{j,i} = -omega_j * t_i, with t_i the start of pulse i
from the start of pulse 0. No phase tracker runs on the OPX.

In the frame rotating at hypothesis j the state is STATIC between pulses:
only the pulse start times enter the model, through the azimuth of the
rotation axis, and the z rotations (light shift, drive-frame return)
commute with that free precession. Gaps between a pulse's end and the
imaging exposure, or between the exposure and the next pulse, therefore do
not enter the model at all -- what must be exact is t_i.

CONSEQUENCE. Between pulses the atom-drive relative phase advances at the
transition frequency: 119.4639 MHz * 4 ns = 0.4779 turns per OPX clock
cycle. One cycle of unplanned delay anywhere in the loop rotates the
hypothesis axis by almost half a turn, so the pulse-start times must be
known EXACTLY in clock cycles. Three things make that true:

1. Every per-step interval comes from the drawn pulse-time list, on the
   host, exactly as ARTIQ's compute_t_between_pulses_mu does per step:

       gap_i = d_i + EDGE + t_img_cc + EDGE + budget_cc + overhead_cc + extra_gap_cc
       t_0 = 0,  t_{i+1} = t_i + gap_i

   (feedback_step_gaps_cc / kexp.base.feedback.schedule_pulse_starts) and
   the OPX is held to it: the wait issued on the Raman switch element after
   pulse i is the per-step table entry

       wait_i = gap_i - d_i - EDGE - overhead_cc  = t_img_cc + EDGE + budget_cc + extra_gap_cc

   shipped as an int shot array and indexed by the pulse counter. On the
   Raman switch element the statements per pulse are exactly

       align(raman_80, raman_150, raman_switch)    # the phase reset lands here
       play('pass', 'raman_switch', duration=d_i)   # Raman exposure, d_i cycles
       play('block', 'raman_switch')                # re-block, EDGE cycles (16 ns)
       align('raman_switch', 'imaging_switch')      # imaging exposure follows the pulse
       wait(wait_i, 'raman_switch')                 # per-step hold

   and nothing else. The imaging exposure ('pass' t_img, 'block') runs on
   imaging_switch, the ADC window on apd (ctx.measure aligns those two).
   The align does NOT stall the Raman switch (imaging_switch is idle when
   it is reached), so the hold starts right after the Raman block and the
   exposure runs CONCURRENTLY with its first t_img + EDGE cycles -- which
   is why the hold contains them (measured on the simulator: a hold of
   budget + extra alone makes every interval exactly t_img + EDGE short).
   overhead_cc is the constant sync cost of the aligns and the frequency
   update (t_opx_feedback_align_overhead, measured on the QOP simulator
   from the pulse timestamps, see expt_params_feedback_opx.py);
   extra_gap_cc (t_feedback_extra_gap) is a free knob to lengthen every
   step, like ARTIQ's delta_t_mu. The Raman pulse play is emitted with
   min_cc (its host-known minimum duration), so no per-shot if_ guard --
   which would add an implicit align and non-deterministic cycles -- sits
   in front of it; the schedule assumes that. The posterior update (one
   loop over the grid) is issued after the measure statement; the OPX's
   measure blocks the program thread until the ADC result exists, so the
   update cannot overlap the exposure (measured) and the budget must
   cover the whole update. If the OPX needs longer than the budget the
   next pulse slips and the schedule is wrong by the overrun. Which is
   why:

2. The ACTUAL start of every pulse is recorded with a timestamp stream
   (t_pulse_start_cc, the Raman 'pass' play) -- the only timestamp the
   model needs, since nothing but the pulse starts enters it. The analysis
   (FeedbackOPXReplay) uses the actual pulse times by default; the finish
   hook recomputes the schedule from the saved durations and the params
   (schedule_pulse_starts) and prints a *** line with the largest
   scheduled-vs-actual deviation if any pulse is off it.

3. The real-time loop uses the SCHEDULED times: the hypothesis-phase
   tables are precomputed on the host from the schedule and shipped per
   shot, so the OPX computes no phase at all.

The control law and the drive (ideas G and A of the speed pass)
---------------------------------------------------------------
The next drive is ALWAYS the argmax grid point (feedback_flat_rule_bool =
0, the default on the OPX). ARTIQ's flat rule (drive the posterior mean
when max P0 < 1.15/m) never fired in 6000 synthetic pulses of any
model-consistent scenario (brainstorm flat_rule_check.py: the flattest
posterior, after pulse 1, has max P0 * m >= 1.18 against the 1.15
threshold); it fires only when readings are >= 3x noisier than the model.
Dropping it removes the whole exp / sum / inv / dot pass. With the flag on
the ARTIQ rule is restored (an exp pass from an interpolation table with
2^opx_exp_lut_bits nodes, weights summed as P/4, the mean from Math.dot)
with one documented difference: the mean is snapped to the NEAREST GRID
INDEX (Math.argmin of |w_j - mean|), because the drive is an index.

The drive of every pulse is a grid index d, so the drive-hypothesis
detuning delta_j = w_d - w_j = (j - d) * dw depends only on k = j - d and
the axis geometry comes from run tables of length 2m - 1 indexed by
j + (m - 1 - d): h_k = sqrt(1/16 + (k dw/4)^2) = |H|/(4 Omega),
ux_k = Omega/|H| = 1/(4 h_k), uz_k = delta/|H|, and the products ux_k^2,
ux_k uz_k (no Math.inv_sqrt per point). The INITIAL drive is the grid
point nearest feedback_fractional_initial_offset: with the default grid
(offset 0, span 5, m = 21) that is the offset itself; with the simulator
config (offset 2, span 3) the snapped grid moves it 2.0 -> 2.1 (at most
dw/2 in general). The snapped value is what pulse 0 streams in
drive_index. The two integer IFs of every grid point are host tables
(if_table_hz, exact Hz: IF0_el + round(slope_el * w_j * Omega/2pi) from
ctx.transition_offset_terms, +15/46 and -8/46 of the RamanBeamPair split)
applied with update_frequency, and the drive index is streamed per pulse;
the finish hook derives the two-photon frequency the atoms saw,

    frequency_drive_applied = 2 * (if_150[d] - if_80[d])   # double pass, both +1 orders

(asserted at trace time to reproduce the run transition from the IF0s
within 3 Hz) and omega_raman = 2 pi * that, so the replay knows the OPX's
control EXACTLY (not to a 1 Hz rounding as with a streamed difference).
Hardware resolution: the QM documentation gives no finite NCO frequency
quantum -- the QUA overview
(https://docs.quantum-machines.co/latest/docs/Introduction/qua_overview/,
"Sub-Hz resolution") states the element frequency is a double and
update_frequency
(https://docs.quantum-machines.co/latest/docs/API_references/qua/dsl_main/)
takes an integer "In steps of 1" in Hz down to pHz; the hardware page
(https://docs.quantum-machines.co/latest/docs/Hardware/OPX_hardware/)
lists only the 16-bit DAC and the +-350 MHz bandwidth. The integer Hz we
command is therefore taken as the applied frequency.

Co-rotating azimuth frame (idea D)
----------------------------------
The rotation axis of hypothesis j is u = Rz(phi_{j,i}) u0 with u0 =
(ux, 0, uz), so R(u, theta) = Rz(phi) R(u0, theta) Rz(-phi). The state of
hypothesis j is kept in the frame where its axis lies in the x-z plane,
s~_i = Rz(-phi_{j,i}) s_i; then

    s~_{i+1} = C_xy Rz(gamma_{j,i}) R(u0, theta) s~_i,
    gamma_{j,i} = phi_{j,i} - phi_{j,i+1} - alpha_{j,i},

with alpha the light-shift + drive-frame-return z rotation of
generate_posterior. gamma is linear in j: gamma_0 = dphi0_i + 4 b_i (wq_d
- wq_0) + phi_LS, step dgamma = ddphi_i + 4 b_i dw/4, where the host ships
cos/sin of dphi0_i = (phi0_i - phi0_{i+1}) mod 1 and ddphi_i = (dphi_i -
dphi_{i+1}) mod 1 over the N+1-row schedule (row N: a would-be pulse N
after gap_{N-1}); the OPX forms cos/sin of the drive-dependent parts (4
trig calls per pulse; per (level, d) tables with discrete durations) and
multiplies the phasors, folding the back-action damping C into the seed
(C cos gamma_0, C sin gamma_0): one phasor recurrence per point, a
5-entry rotation matrix (u_y = 0: R00 = c + omc ux^2, R10 = -R01 = s uz,
R02 = R20 = omc ux uz, R21 = -R12 = s ux, R11 = c, R22 = 1 - omc ux^2)
and one z rotation. z, s_z and the likelihood are identical to the lab
frame (verified to <= 1e-12 against the pass-2 oracle); x, y are the same
vector in a different frame. The spin-up initial state is frame-invariant.

Fixed-point numerics (spec 4.4, amended; ideas F, F')
------------------------------------------------------
Everything on the OPX lives in QUA fixed [-8, 8). Frequencies are in units
of Omega = pi/t_pi (w = (omega - omega_res)/Omega) and are shipped as w/4.
Rotation angles are turns: theta = -4 a_i h_k (a_i = (d_i - t_off)/2 t_pi).
cos/sin of theta come from a sine table with 2^opx_sincos_lut_bits nodes
per turn extended by a quarter turn (cos read at index + n/4, no modulo;
index and fraction from the 4.28 bit pattern of the angle, so negative
angles wrap correctly) and linear interpolation -- 12 bits: 5122 entries,
<= 2.9e-7 on the trig values, <= 2.3e-5 on P0 (brainstorm synth_runs.py
E1), 7 cycles per grid point faster than Math.cos2pi + Math.sin2pi on the
simulator (table below); 0 = the Math calls, exact. The likelihood is
kept as log-weights L/s with s = feedback_log_weight_scale = 32:
dL/32 = -((p_meas - p1) / sigma_p / 8)^2, one multiply, NO clamp per
point, because with p_meas clamped ONCE per pulse to [-2, 3] and p1 in
[0, 1] the decrement is >= -(3/sigma_p/8)^2 = -5.55 for sigma_p = 0.159.
The max-normalisation is lazy: pulse i's loop reads t = L_j - M_{i-1}
(M_{i-1} the previous argmax value, 0 at shot start), floors it at F = -8
- dL_min (= -2.45, i.e. -78.5 nats; derived, not a free parameter) and
adds the decrement, so L stays in [-8, 0] by construction; Math.argmax
then gives jmax and M_i = L[jmax], and the saves emit L_j - M_i. p1 =
(1 + z)/2 + (mid - 1/2)(1 - z^2) is monotonic and maps [-1, 1] onto
[0, 1] exactly for mid in (0.25, 0.75), asserted at trace time, so the p1
clamps are gone too. Against the unclamped double-precision posterior the
L/32 scheme agrees to 8e-34 at nominal noise and 2e-8 at 4x noise, where
the pass-2 L/4 + 7.9 sigma clamp changed 32 % of the decisions
(brainstorm l32_vs_exact.py). The only approximations left relative to
the double-precision ARTIQ posterior are the -78.5 nat floor, the sincos
table, and QUA's 2^-28 rounding (not modelled by the emulation; it causes
~1 % argmax disagreements on near-ties, brainstorm E1). The APD reading
enters as a photon fraction p_meas = (raw - raw_down)/(raw_up -
raw_down); only sigma_p = std_n_photons/N_photons is needed.

Discrete pulse durations (ideas B + E, OPTION, t_raman_pulse_n_levels)
-----------------------------------------------------------------------
With t_raman_pulse_n_levels = n > 0 every pulse duration is drawn
uniformly from n levels equally spaced on [min, max] * t_pi
(kexp.base.feedback.draw_t_raman_pulse_list_levels, a pure function of
the seed like the continuous draw), and the per-point rotation matrix
entries (R00, s uz, omc ux uz, s ux, c) come from per-(level, k) run
tables (n * (2m - 1) entries each), as do the per-pulse phasor seeds
(cos/sin of 4 b_l (wq_d - wq_0) + phi_LS per (level, d), cos/sin of
4 b_l dw/4 per level): NO trig anywhere in the real-time loop. Physics:
2 (and 3) levels alias measurably (+5-7 % wrong-grid-point rate, 3
sigma); 4-16 levels sit within +0.6..+3 % of the continuous draw at 1000
seeds (<= 2 sigma, brainstorm b_alias_ongrid.py) -- fewer than 4 levels
are refused, >= 8 (better 16) are recommended, and the few-% question is
open (a 10k-seed run of b_alias_ongrid.py). Default 0 = continuous.

Data (per shot; N = N_pulses, m = feedback_grid_size)
------------------------------------------------------
Only what the existing replay (FeedbackReplay conventions) needs, plus
the one thing the reset model cannot reconstruct (the actual pulse starts):

streams:   apd (N) volts (demod2volts, like every ctx.measure key);
           drive_index (N) int, the grid index driven at each pulse (pulse
           0: the snapped initial drive); s_z (N) = z[zidx] after the
           update, the model's S_z under the on-resonance hypothesis (as
           ARTIQ); log_weights (N, m) = L/s after the max-normalisation
           (s = feedback_log_weight_scale, saved with the params);
           t_pulse_start_cc (N) the Raman 'pass' play timestamps (OPX
           clock cycles).
host_data: t_raman_pulse (N) the drawn durations rounded to 4 ns cycles
           (what ran); t_raman_pulse_seed (1); omega_raman_mesh (N+1, m)
           rad/s, every row the shot's grid; if_table_hz (m, 2) the
           integer IFs [raman_80, raman_150] of every grid point.
finish:    omega_raman (N) rad/s = 2 pi * 2 * (if_150[d] - if_80[d]);
           probabilities (N+1, m) (row 0 uniform) = exp(s L)/sum;
           t_pulse_start (N) s from pulse 0 (actual timestamps); t (N) =
           t_pulse_start + d + t_img (the ARTIQ convention, for plots).

Everything else (the schedule, the per-step gaps, the phase tables, the
axis tables, the open-loop drive schedule) is a pure function of these
and the params and is recomputed where needed (feedback_finish,
FeedbackOPXReplay). The ARTIQ container names (apd, omega_raman, s_z, t,
probabilities, omega_raman_mesh, t_raman_pulse, t_raman_pulse_seed) are
kept so the existing analysis conventions carry over.

QUA statement costs (QOP simulator, 2026-09-25, brainstorm/hbench_run.py)
-------------------------------------------------------------------------
One-statement loop bodies bracketed by timestamped plays, per-iteration
cost = (lat(42) - lat(21))/21 in clock cycles. Bodies cheaper than ~10 cc
(empty, array read/write, add, mul, cond, expression index) came back
inconsistent or negative: when the loop is shorter than the play pipeline
the second bracket play is issued as soon as the element is free, so
those sit BELOW the floor of this method and only the compute-bound rows
are quoted:

    Math.cos2pi                              21.4
    Math.cos2pi + Math.sin2pi                27.7
    Math.inv_sqrt                            64.3
    Math.exp                                 60.2
    exp interpolation block (5 statements)   16.1
    sincos LUT block (6 statements, 1024 or 4096 nodes: same)   24.2
    Math.argmax over 64 entries             224.7   (~3.5 per entry)
    matvec (5-entry matrix + z rotation)     22.3
    current Rodrigues (as emitted)           35.9
    NEW per-point body, Math trig            82.0   (A + D + F, 3 axis tables)
    NEW per-point body, sincos LUT           75.0
    NEW per-point body, 5 axis tables        77.0   (products tabled, Math trig)
    NEW per-point body, (level, k) tables    32.7   (B + E: no trig)

Adopted: the sincos LUT (12 bits), the 5 axis tables, B + E as the
option above.

Per-pulse compute (QOP simulator, 2026-09-25, m = 21, N_pulses = 6, a DC
level on the APD input, budget collapsed to 16 ns so the interval is
compute-bound; the number is the excess of each interval over
d_i + EDGE + t_img + EDGE, i.e. readback + posterior + sync after the
imaging exposure; identical on every one of the 5 intervals of each run;
scratchpad run_sim_3b.py):

    pass 2, fused loop, inv_sqrt + exp table (previous)   4875 cc = 19.50 us
    pass 3b, continuous durations, exact trig             2043 cc =  8.17 us
    pass 3b, continuous durations, sincos LUT (default)   1938 cc =  7.75 us
    pass 3b, 16 duration levels (B + E)                   1074 cc =  4.30 us

With the real budget (10 us) every interval equals the schedule plus a
constant sync overhead of 82 cc (continuous) / 86 cc (levels); the params
file carries both (t_opx_feedback_align_overhead[_levels]), and with them
the simulated slip is 0 on every pulse. The flat-rule structure has not
been timed. Exact trig and the LUT gave identical decisions.

*** NOT YET RUN ON HARDWARE. Placeholder calibrations are listed in
expt_params_feedback_opx.py; prerequisites M1-M3 in feedback_opx.py. ***
"""

import math
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from kexp.control.opx import OPXSequence, KexpShotContext
from kexp.control.opx.sequence import Stream
from kexp.control.opx.units import (s_to_cc, demod2volts, CLOCK_NS,
                                    MIN_PULSE_CC, QUA_FIXED_LIMIT)
from kexp.control.opx.opx_config import T_DIGITAL_EDGE_NS
from kexp.base.feedback import (feedback_grid_omega, hypothesis_phase_tables,
                                schedule_pulse_starts, draw_t_raman_pulse_list,
                                draw_t_raman_pulse_list_levels,
                                t_raman_pulse_level_set, new_t_raman_pulse_seed)

# length of the 'block' level-set play that re-blocks after an exposure
BLOCK_EDGE_CC = int(T_DIGITAL_EDGE_NS // CLOCK_NS)

# host-side clamp of the measured photon fraction, applied ONCE per pulse
# before it enters the likelihood; with p1 in [0, 1] it bounds |p_meas - p1|
# by P_MEAS_SPAN_MAX, which sets the log-weight floor
P_MEAS_CLAMP = (-2.0, 3.0)
P_MEAS_SPAN_MAX = 3.0

# headroom left between the largest decrement and the fixed-point floor
L_FLOOR_MARGIN = 2.0 ** -16

# largest |w_d - w_j| the axis tables tolerate (h_k^2 = 1/16 + (k dw/4)^2 < 8)
MAX_ABS_DELTA = 10.9

# the two-photon inverse of the drive split must give the run transition
# back from the config IF0s to this precision (integer-Hz IF0s: 2 Hz max)
F_APPLIED_TOL_HZ = 3.0

# exp(L) on the OPX (flat rule ON only): a host table with 2^bits nodes per
# unit of L/s and linear interpolation, then log2(s) squarings. 0 = Math.exp.
EXP_LUT_BITS = 8

# cos/sin of the per-point rotation angle from a sine table with 2^bits
# nodes per turn (12: 5122 entries) -- see the module docstring. 0 = the
# Math.cos2pi / Math.sin2pi calls (exact).
SINCOS_LUT_BITS = 12
SINCOS_LUT_MAX_BITS = 14

# log-weight scale s (L/s is what the OPX keeps): the module default when a
# params object lacks feedback_log_weight_scale
LOG_WEIGHT_SCALE = 32

# fewer discrete pulse-duration levels than this alias measurably
MIN_PULSE_LEVELS = 4

SEQUENCE_NAME = 'bayesian_feedback'
SEQUENCE_NAME_OPEN_LOOP = 'bayesian_feedback_open_loop'

# per-shot data keys (ARTIQ names kept where the meaning is the same)
STREAM_KEYS = ('apd', 'drive_index', 's_z', 'log_weights', 't_pulse_start_cc')
HOST_KEYS = ('t_raman_pulse', 't_raman_pulse_seed', 'omega_raman_mesh', 'if_table_hz')
HOST_KEYS_OPEN_LOOP = ()
DERIVED_KEYS = ('omega_raman', 'probabilities', 't_pulse_start', 't')

# elements of the Raman pair, in the order the transition split names them;
# if_table_hz columns are in this order
RAMAN_EL_80 = 'raman_80'
RAMAN_EL_150 = 'raman_150'
IF_TABLE_COLUMNS = (RAMAN_EL_80, RAMAN_EL_150)


# ---------------------------------------------------------------------------
# small conversions shared with the analysis
# ---------------------------------------------------------------------------

def volts2raw(v, t_integration_s):
    """Inverse of kexp.control.opx.units.demod2volts: mean volts over the
    integration window -> raw integration units (raw = V * duration_ns / 4096)."""
    duration_ns = float(t_integration_s) * 1e9
    return np.asarray(v, dtype=float) * duration_ns / 4096.0


def log_weights_to_probabilities(L, scale):
    """L/scale log-weights (..., m), max-normalised on the OPX -> normalised
    posterior P0 (..., m) in float64: P0 = exp(scale * L) / sum. NaN rows
    stay NaN."""
    L = np.asarray(L, dtype=float)
    P = np.exp(float(scale) * L)
    S = np.sum(P, axis=-1, keepdims=True)
    with np.errstate(invalid='ignore', divide='ignore'):
        return P / S


def log_weights4_to_probabilities(L4):
    """Pass-2 files (log_weights4 = L/4): P0 = exp(4 L4)/sum."""
    return log_weights_to_probabilities(L4, 4.0)


def timestamps_cc_to_seconds(t_cc, valid=None, t_ref_cc=None):
    """Per-shot OPX timestamps (n_shots, N) int cycles -> seconds from the
    shot's reference: its first entry, or ``t_ref_cc`` (n_shots,) when
    given. Differences are taken modulo 2^32, which is the identity for a
    monotonic int64 stream and repairs a 32-bit wrap inside a shot (a shot
    is ~1 ms; 2^32 cycles is 17 s). Entries < 0 (INT_MISSING /
    TIMESTAMP_SKIPPED placeholders) and rows with valid == 0 come back NaN."""
    t = np.asarray(t_cc)
    n_shots = t.shape[0]
    out = np.full(t.shape, np.nan, dtype=float)
    ok = t >= 0
    if valid is not None:
        ok &= np.asarray(valid, dtype=bool).reshape(n_shots, 1)
    if t_ref_cc is None:
        ref = t[:, :1].astype(np.int64)
        ref_ok = ok[:, 0]
    else:
        ref = np.asarray(t_ref_cc).reshape(n_shots, 1).astype(np.int64)
        ref_ok = (ref[:, 0] >= 0)
    ok &= ref_ok.reshape(n_shots, 1)
    rel = np.mod(t.astype(np.int64) - ref, np.int64(2) ** 32)
    out[ok] = rel[ok].astype(float) * (CLOCK_NS * 1e-9)
    return out


def open_loop_drive_indices(m, N):
    """Grid indices driven at each pulse of the open-loop grid sweep: the
    monotonic sweep of deterministic_bayesian.get_new_pulse_list,
    rint(linspace(0, m-1, N)) clipped to the grid."""
    idx = np.rint(np.linspace(0.0, m - 1, int(N)))
    return np.clip(idx, 0, m - 1).astype(int)


def feedback_step_gaps_cc(d_cc, t_img_cc, budget_cc, overhead_cc, extra_gap_cc=0,
                          edge_cc=BLOCK_EDGE_CC):
    """Per-step interval from pulse i start to pulse i+1 start, in cycles,
    from the drawn durations -- ARTIQ's compute_t_between_pulses_mu per
    step: d_i + edge + t_img + edge + budget + overhead + extra_gap."""
    d = np.asarray(d_cc).astype(np.int64)
    return d + np.int64(2 * int(edge_cc) + int(t_img_cc) + int(budget_cc)
                        + int(overhead_cc) + int(extra_gap_cc))


def nearest_grid_index(w_grid, w):
    """Index of the grid point nearest w (first minimum on a tie; the grid
    is descending in j). w_grid (m,) or (n, m) with w scalar or (n,)."""
    g = np.asarray(w_grid, dtype=float)
    w = np.asarray(w, dtype=float)
    if g.ndim == 1:
        return int(np.argmin(np.abs(g - float(w))))
    return np.argmin(np.abs(g - w.reshape(-1, 1)), axis=1).astype(np.int64)


def if_tables_hz(w_grid, f_Omega_hz, terms):
    """The integer IFs the OPX applies for every grid point: (m, 2) int64,
    columns IF_TABLE_COLUMNS = (raman_80, raman_150), if_el[j] = IF0_el +
    round(slope_el * w_j * f_Omega_hz) from ctx.transition_offset_terms.
    The applied two-photon frequency of index j is 2 * (col1 - col0)."""
    w = np.asarray(w_grid, dtype=float).reshape(-1)
    out = np.empty((w.size, 2), dtype=np.int64)
    for k, el in enumerate(IF_TABLE_COLUMNS):
        if0, slope = terms[el]
        out[:, k] = int(if0) + np.rint(float(slope) * w * float(f_Omega_hz)).astype(np.int64)
    return out


def applied_frequency_hz(if_table, drive_index):
    """The two-photon frequency (Hz) driven at the given grid indices:
    if_table (..., m, 2), drive_index (..., N) int (>= 0; negatives ->
    NaN)."""
    tab = np.asarray(if_table, dtype=float)
    d = np.asarray(drive_index)
    ok = d >= 0
    dd = np.where(ok, d, 0).astype(int)
    f80 = np.take_along_axis(tab[..., 0], dd, axis=-1)
    f150 = np.take_along_axis(tab[..., 1], dd, axis=-1)
    f = 2.0 * (f150 - f80)
    f[~ok] = np.nan
    return f


def exp_lut_table(bits):
    """The exp(L) interpolation table of the flat-rule path (L in [-8, 0]):
    node n = exp(-(8*2^bits - n) / 2^bits) for n = 0 .. 8*2^bits + 1."""
    n_lut = 8 * (2 ** int(bits))
    step = 2.0 ** (-int(bits))
    return np.array([math.exp(-(n_lut - n) * step) for n in range(n_lut + 2)])


def exp_lut_emulation(L, bits):
    """exp(L) exactly as the OPX interpolates it (float64 emulation of the
    index / fraction arithmetic on the 4.28 bit pattern), for L in [-8, 0]."""
    L = np.asarray(L, dtype=float)
    lut = exp_lut_table(bits)
    n_lut = 8 * (2 ** int(bits))
    scaled = L * (2 ** int(bits))
    k = np.floor(scaled)
    frac = scaled - k
    n = (k + n_lut).astype(int)
    n = np.clip(n, 0, n_lut)
    return lut[n] + frac * (lut[n + 1] - lut[n])


def sincos_lut_table(bits):
    """The sine table the OPX carries for opx_sincos_lut_bits = bits:
    sin(2 pi k / n) for k = 0 .. n + n/4 + 1 (n = 2^bits), so cos is read
    a quarter turn up without a modulo."""
    n = 2 ** int(bits)
    return np.sin(2.0 * np.pi * np.arange(n + n // 4 + 2) / n)


def sincos_lut_emulation(turns, bits):
    """(cos, sin) of an angle in turns exactly as the OPX interpolates them
    (index = the top `bits` fraction bits of the 4.28 angle, the rest the
    fraction; negative angles wrap)."""
    t = np.asarray(turns, dtype=float)
    n = 2 ** int(bits)
    tab = sincos_lut_table(bits)
    fr = t - np.floor(t)
    y = fr * n
    i0 = np.floor(y).astype(int)
    f = y - i0
    s = tab[i0] + f * (tab[i0 + 1] - tab[i0])
    ci = i0 + n // 4
    cc = tab[ci] + f * (tab[ci + 1] - tab[ci])
    return cc, s


def axis_tables(dw, m):
    """Per-run axis geometry over k = j - d in [-(m-1), m-1] (idea A):
    dict of (2m-1,) float64 arrays h, ux, uz, ux2, uxuz with
    h_k = sqrt(1/16 + (k dw/4)^2) = |H|/(4 Omega), ux_k = Omega/|H| =
    1/(4 h_k), uz_k = delta/|H| = (k dw/4)/h_k, ux2 = ux^2, uxuz = ux uz."""
    m = int(m)
    k = np.arange(-(m - 1), m, dtype=np.float64)
    dq = k * float(dw) / 4.0
    h = np.sqrt(1.0 / 16.0 + dq * dq)
    ux = 0.25 / h
    uz = dq / h
    return dict(h=h, ux=ux, uz=uz, ux2=ux * ux, uxuz=ux * uz)


def level_matrix_tables(a_levels, dw, m):
    """B+E: the five rotation-matrix entries per (level l, k): dict of
    (n_levels, 2m-1) arrays Am = c + omc ux^2, B = s uz, Cc = omc ux uz,
    D = s ux, cth = c, with theta_{l,k} = -4 a_l h_k (turns) and
    omc = 1 - c. The sixth entry E = 1 - omc ux^2 = (1 + c) - Am."""
    ax = axis_tables(dw, m)
    a = np.asarray(a_levels, dtype=float).reshape(-1, 1)
    th = -4.0 * a * ax['h'][None, :]
    cth = np.cos(2.0 * np.pi * th)
    sth = np.sin(2.0 * np.pi * th)
    omc = 1.0 - cth
    return dict(Am=cth + omc * ax['ux2'][None, :], B=sth * ax['uz'][None, :],
                Cc=omc * ax['uxuz'][None, :], D=sth * ax['ux'][None, :], cth=cth,
                theta=th)


def level_seed_tables(b_levels, w_grid, phi_LS):
    """B+E: the drive-dependent parts of the phasor seeds per level: cos/sin
    of beta_{l,d} = 4 b_l (wq_d - wq_0) + phi_LS as (n_levels, m) tables
    indexed l*m + d, and cos/sin of dbeta_l = 4 b_l (wq_0 - wq_1) as
    (n_levels,) tables."""
    wq = np.asarray(w_grid, dtype=float) * 0.25
    b4 = 4.0 * np.asarray(b_levels, dtype=float).reshape(-1, 1)
    beta = b4 * (wq[None, :] - wq[0]) + float(phi_LS)
    dbeta = (b4 * (wq[0] - wq[1])).reshape(-1)
    return dict(cb=np.cos(2.0 * np.pi * beta), sb=np.sin(2.0 * np.pi * beta),
                cdb=np.cos(2.0 * np.pi * dbeta), sdb=np.sin(2.0 * np.pi * dbeta),
                beta=beta, dbeta=dbeta)


def corotating_phase_tables(f_grid_hz, t_start_ext_s):
    """The per-pulse azimuth-frame advances of the co-rotating frame (D),
    in turns in [0, 1): from the hypothesis phase seeds phi0_i, dphi_i
    (hypothesis_phase_tables) over the N+1-row schedule t_start_ext_s
    (row N: the would-be pulse N),

        dphi0_i = (phi0_i - phi0_{i+1}) mod 1,  ddphi_i = (dphi_i - dphi_{i+1}) mod 1

    for i = 0 .. N-1, so gamma_{j,i} = dphi0_i + j ddphi_i - alpha_{j,i}.
    Returns (dphi0, ddphi) shaped (..., N)."""
    phi0, dphi = hypothesis_phase_tables(f_grid_hz, t_start_ext_s)
    d0 = np.mod(phi0[..., :-1] - phi0[..., 1:], 1.0)
    dd = np.mod(dphi[..., :-1] - dphi[..., 1:], 1.0)
    d0 = np.where(d0 >= 1.0, d0 - 1.0, d0)
    dd = np.where(dd >= 1.0, dd - 1.0, dd)
    return d0, dd


def extend_schedule_cc(d_cc, c):
    """The N+1-row pulse-start schedule (cycles): the N scheduled starts plus
    a would-be pulse N one gap after pulse N-1 (with d_N := d_{N-1})."""
    d = np.asarray(d_cc).astype(np.int64)
    d_ext = np.concatenate([d, d[..., -1:]], axis=-1)
    return schedule_pulse_starts(d_ext, c.t_img_cc, c.budget_cc,
                                 c.overhead_cc + c.extra_gap_cc,
                                 block_edge_cc=c.edge_cc)


def _split_factor(inv_range_raw):
    """Smallest n in (1, 2, 4, 8) with |inv_range_raw|/n < 8, so the photon
    fraction is formed as ((raw - raw_down) * k1) * 2 * 2 ... with every
    factor in QUA fixed range."""
    for n in (1, 2, 4, 8):
        if abs(inv_range_raw) / n < QUA_FIXED_LIMIT:
            return n
    raise ValueError(
        f"[opx feedback] 1/(raw APD range) = {inv_range_raw:g} is too large "
        f"for the fixed-point photon-fraction conversion (needs < 64): the "
        f"up-down endpoint separation is below 1/64 raw integration units. "
        f"Increase the APD gain / integration window or fix the endpoint "
        f"calibration (v_apd_all_up_opx / v_apd_all_down_opx).")


# ---------------------------------------------------------------------------
# host-side per-shot tables and run constants
# ---------------------------------------------------------------------------

@dataclass
class FeedbackConstants:
    """Run-level constants of the fixed-point update (all host floats)."""
    N: int
    m: int
    t_pi: float
    Omega: float
    omega_res: float
    t_img_s: float
    phi_LS: float             # light-shift z rotation per measurement, turns
    C: float                  # back_action_coherence
    mid_m_half: float         # (midpoint - 0.5), 0 when the remap is off
    remap_enabled: bool
    sigma_p: float
    inv_sigma_p: float
    scale: int                # log-weight scale s: the OPX keeps L/s
    k_exp: int                # log2(scale): squarings of exp(L/s) (flat rule on)
    inv_sigma_p_s: float      # inv_sigma_p / sqrt(2 s): dL/s = -((pm - p1) * this)^2
    L_floor: float            # -8 - min dL/s (+ margin): the lazy-normalisation floor
    flat_rule: bool           # feedback_flat_rule_bool
    flat_threshold: float     # m / 1.15: sum(P) above it means "flat posterior"
    flat_threshold4: float    # flat_threshold / 4: the OPX sums P/4
    f_Omega_hz: float         # Omega / 2pi: Hz per unit of w
    t_offset_s: float         # switch-path turn-on latency
    v_up_raw: float
    v_down_raw: float
    inv_range_raw: float
    n_split: int              # photon-fraction split factor (1, 2, 4, 8)
    k1: float                 # inv_range_raw / n_split
    t_img_cc: int
    budget_cc: int
    overhead_cc: int
    extra_gap_cc: int
    edge_cc: int
    exp_lut_bits: int = EXP_LUT_BITS        # flat rule on: 0 = Math.exp
    sincos_lut_bits: int = SINCOS_LUT_BITS  # 0 = Math.cos2pi / sin2pi
    n_levels: int = 0                       # 0 = continuous durations


def _cc_multiple(get, key):
    v = float(get(key))
    cc = int(round(v * 1e9 / CLOCK_NS))
    if abs(cc * CLOCK_NS * 1e-9 - v) > 1e-12:
        raise ValueError(f"[opx feedback] {key} = {v} s is not a multiple of "
                         f"{CLOCK_NS} ns.")
    if cc < 0:
        raise ValueError(f"[opx feedback] {key} must be >= 0.")
    return cc


def _get_optional(get, key, default):
    try:
        return get(key)
    except (AttributeError, KeyError):
        return default


def feedback_constants(get, m=None, exp_lut_bits=None, sincos_lut_bits=None):
    """Build FeedbackConstants from a getter ``get(key) -> float`` of the
    run-level parameters (ctx.const in the sequence; plain attribute reads in
    the analysis). Raises on anything outside the fixed-point ranges."""
    N = int(get('N_pulses'))
    m = int(get('feedback_grid_size')) if m is None else int(m)
    if N < 1 or m < 2:
        raise ValueError(f"[opx feedback] need N_pulses >= 1 and "
                         f"feedback_grid_size >= 2, got {N}, {m}.")
    if m > 31:
        # the flat-rule path sums the weights as P/4 (max 1/4 each): sum < 8
        # needs m < 32
        raise ValueError(f"[opx feedback] feedback_grid_size = {m} > 31: the "
                         f"fixed-point weight sum (P/4 per point) would leave "
                         f"[-8, 8).")
    t_pi = float(get('t_raman_pi_pulse'))
    Omega = np.pi / t_pi
    omega_res = 2.0 * np.pi * float(get('frequency_raman_transition'))
    t_img_s = float(get('t_img_pulse'))
    f_LS = float(get('frequency_lightshift'))
    C = float(get('back_action_coherence'))
    remap = bool(get('feedback_measurement_midpoint_remap_enabled'))
    mid = float(get('feedback_measurement_midpoint_fraction'))
    if remap and not (0.25 < mid < 0.75):
        raise ValueError(
            f"[opx feedback] feedback_measurement_midpoint_fraction = {mid} "
            f"must be in (0.25, 0.75): only then is the expected photon "
            f"fraction p1(z) monotonic with p1(-1) = 0, p1(1) = 1, which the "
            f"OPX relies on (no p1 clamps).")
    sigma_p = float(get('std_photon_fraction_opx'))
    if not sigma_p > 0.0:
        raise ValueError("[opx feedback] std_photon_fraction_opx must be > 0.")
    inv_sigma_p = 1.0 / sigma_p
    if not inv_sigma_p < QUA_FIXED_LIMIT:
        raise ValueError(
            f"[opx feedback] 1/std_photon_fraction_opx = {inv_sigma_p:g} must "
            f"be < 8 for the fixed-point residual (sigma_p > 0.125).")
    scale = int(_get_optional(get, 'feedback_log_weight_scale', LOG_WEIGHT_SCALE))
    if scale < 2 or (scale & (scale - 1)) != 0:
        raise ValueError(f"[opx feedback] feedback_log_weight_scale must be a "
                         f"power of two >= 2, got {scale}.")
    k_exp = int(round(math.log2(scale)))
    inv_sigma_p_s = inv_sigma_p / math.sqrt(2.0 * scale)
    q_max = P_MEAS_SPAN_MAX * inv_sigma_p_s
    dL_max = q_max * q_max
    L_floor = -QUA_FIXED_LIMIT + dL_max + L_FLOOR_MARGIN
    if not L_floor < -1e-3:
        raise ValueError(
            f"[opx feedback] the largest log-weight decrement per pulse, "
            f"(3/sigma_p)^2/(2 s) = {dL_max:.3f} in L/s units, leaves no room "
            f"under the fixed-point range for s = feedback_log_weight_scale = "
            f"{scale}; increase the scale.")
    flat_rule = bool(int(_get_optional(get, 'feedback_flat_rule_bool', 0)))
    if float(get('feedback_remesh_threshold_Omega')) != 0.0:
        raise ValueError(
            "[opx feedback] feedback_remesh_threshold_Omega must be 0: remesh "
            "is not ported to the OPX (host/replay only, D7).")
    if int(get('feedback_phase_model_reset')) != 1:
        raise ValueError(
            "[opx feedback] feedback_phase_model_reset must be 1: the reset "
            "phase model is the only one implemented on the OPX.")
    t_int = float(get('t_opx_integration_len'))
    v_up = float(get('v_apd_all_up_opx'))
    v_down = float(get('v_apd_all_down_opx'))
    v_up_raw = float(volts2raw(v_up, t_int))
    v_down_raw = float(volts2raw(v_down, t_int))
    if abs(v_up_raw - v_down_raw) < 1e-12:
        raise ValueError("[opx feedback] OPX APD calibration range is zero.")
    if not (abs(v_up_raw) < QUA_FIXED_LIMIT and abs(v_down_raw) < QUA_FIXED_LIMIT):
        raise ValueError("[opx feedback] APD endpoints in raw units exceed the "
                         "fixed-point range.")
    inv_range_raw = 1.0 / (v_up_raw - v_down_raw)
    n_split = _split_factor(inv_range_raw)
    t_offset = float(get('t_raman_pulse_offset_opx'))
    edge_cc = BLOCK_EDGE_CC
    t_img_cc = int(s_to_cc(t_img_s, key='t_img_pulse'))
    budget_cc = int(s_to_cc(float(get('t_opx_feedback_compute_budget')),
                            key='t_opx_feedback_compute_budget'))
    n_levels = int(_get_optional(get, 't_raman_pulse_n_levels', 0))
    # the constant per-pulse sync overhead depends on the loop structure
    # (QOP simulator, 2026-09-25: 82 cc continuous draw, 86 cc discrete
    # levels); the discrete-level structure has its own parameter so the
    # scheduled pulse starts -- which the real-time posterior's phase tables
    # use -- stay exact in either mode
    overhead_key = 't_opx_feedback_align_overhead'
    if n_levels > 0 and _get_optional(
            get, 't_opx_feedback_align_overhead_levels', None) is not None:
        overhead_key = 't_opx_feedback_align_overhead_levels'
    overhead_cc = _cc_multiple(get, overhead_key)
    extra_gap_cc = _cc_multiple(get, 't_feedback_extra_gap')
    if budget_cc < MIN_PULSE_CC:
        raise ValueError("[opx feedback] t_opx_feedback_compute_budget must be "
                         ">= 16 ns.")
    if exp_lut_bits is None:
        bits = int(_get_optional(get, 'opx_exp_lut_bits', EXP_LUT_BITS))
    else:
        bits = int(exp_lut_bits)
    if not 0 <= bits <= 10:
        raise ValueError("[opx feedback] opx_exp_lut_bits must be 0 (Math.exp) or 1..10.")
    if sincos_lut_bits is None:
        sbits = int(_get_optional(get, 'opx_sincos_lut_bits', SINCOS_LUT_BITS))
    else:
        sbits = int(sincos_lut_bits)
    if not (sbits == 0 or 4 <= sbits <= SINCOS_LUT_MAX_BITS):
        raise ValueError(f"[opx feedback] opx_sincos_lut_bits must be 0 (Math "
                         f"trig) or 4..{SINCOS_LUT_MAX_BITS}.")
    if n_levels < 0 or 0 < n_levels < MIN_PULSE_LEVELS:
        raise ValueError(
            f"[opx feedback] t_raman_pulse_n_levels = {n_levels}: 0 "
            f"(continuous draw) or >= {MIN_PULSE_LEVELS} levels (fewer alias "
            f"measurably; >= 8 recommended).")
    return FeedbackConstants(
        N=N, m=m, t_pi=t_pi, Omega=Omega, omega_res=omega_res, t_img_s=t_img_s,
        phi_LS=f_LS * t_img_s, C=C,
        mid_m_half=(mid - 0.5) if remap else 0.0, remap_enabled=remap,
        sigma_p=sigma_p, inv_sigma_p=inv_sigma_p, scale=scale, k_exp=k_exp,
        inv_sigma_p_s=inv_sigma_p_s, L_floor=L_floor, flat_rule=flat_rule,
        flat_threshold=m / 1.15, flat_threshold4=m / (4.0 * 1.15),
        f_Omega_hz=1.0 / (2.0 * t_pi),
        t_offset_s=t_offset, v_up_raw=v_up_raw, v_down_raw=v_down_raw,
        inv_range_raw=inv_range_raw, n_split=n_split,
        k1=inv_range_raw / n_split,
        t_img_cc=t_img_cc, budget_cc=budget_cc, overhead_cc=overhead_cc,
        extra_gap_cc=extra_gap_cc, edge_cc=edge_cc, exp_lut_bits=bits,
        sincos_lut_bits=sbits, n_levels=n_levels)


@dataclass
class FeedbackShotTables:
    """Per-shot host tables (execution order, one row per shot)."""
    n_shots: int
    seed: np.ndarray            # (n_shots,) int
    d_cc: np.ndarray            # (n_shots, N) int64 pulse durations, cycles
    d_s: np.ndarray             # (n_shots, N) the same in seconds (4 ns grid)
    level_idx: Optional[np.ndarray]   # (n_shots, N) int, discrete durations only
    level_s: Optional[np.ndarray]     # (n_shots, n_levels) the level set (s)
    gap_cc: np.ndarray          # (n_shots, N) int64 per-step interval i -> i+1
    wait_cc: np.ndarray         # (n_shots, N) int64 hold on the switch after pulse i's block
    t_start_cc: np.ndarray      # (n_shots, N) int64 scheduled starts, pulse 0 = 0
    t_start_ext_cc: np.ndarray  # (n_shots, N+1) with the would-be pulse N
    t_start_s: np.ndarray       # (n_shots, N)
    a: np.ndarray               # (n_shots, N) (d - t_off)/(2 t_pi): theta scale, turns
    b: np.ndarray               # (n_shots, N) d/(2 t_pi): alpha_z scale, turns
    phi0: np.ndarray            # (n_shots, N+1) hypothesis phase seeds, turns in [0, 1)
    dphi: np.ndarray            # (n_shots, N+1)
    dphi0: np.ndarray           # (n_shots, N) co-rotating frame advance seeds
    ddphi: np.ndarray           # (n_shots, N)
    omega_grid: np.ndarray      # (n_shots, m) rad/s
    w_grid: np.ndarray          # (n_shots, m) Omega units
    dw: np.ndarray              # (n_shots,) grid step, Omega units (> 0)
    zidx: np.ndarray            # (n_shots,) int
    w_init: np.ndarray          # (n_shots,) the requested first drive, Omega units
    d_init: np.ndarray          # (n_shots,) int: the grid index nearest w_init
    d_sched: Optional[np.ndarray]   # (n_shots, N) int open-loop drive indices
    if_hz: Optional[np.ndarray]     # (n_shots, m, 2) int64 IF tables (needs terms)
    open_loop: bool
    c: FeedbackConstants

    @property
    def N(self):
        return int(self.c.N)

    @property
    def m(self):
        return int(self.c.m)

    @property
    def w_sched(self):
        """Open-loop drive schedule in Omega units (None when closed loop)."""
        if self.d_sched is None:
            return None
        return np.take_along_axis(self.w_grid, self.d_sched, axis=1)

    @property
    def w_init_snapped(self):
        return np.take_along_axis(self.w_grid, self.d_init.reshape(-1, 1), axis=1).reshape(-1)


def build_feedback_shot_tables(col: Callable[[str], np.ndarray], n_shots: int,
                               c: FeedbackConstants, open_loop=False,
                               seeds=None, terms=None) -> FeedbackShotTables:
    """Everything the OPX is handed for one run, computed per shot on the
    host in float64. ``col(key)`` returns the (n_shots,) execution-order
    column of an ExptParams key (ctx.p.<key>.column in the sequence).
    ``seeds`` overrides the per-shot seed column (replay of a recorded run).
    ``terms``: ctx.transition_offset_terms('raman') for the integer IF
    tables (None: no IF tables).
    """
    n_shots = int(n_shots)
    N, m = c.N, c.m

    def column(key):
        v = np.asarray(col(key), dtype=float).reshape(-1)
        if v.size == 1 and n_shots != 1:
            v = np.full(n_shots, v[0])
        if v.size != n_shots:
            raise ValueError(f"[opx feedback] column {key!r} has {v.size} "
                             f"entries for {n_shots} shots.")
        return v

    # --- pulse durations: the ARTIQ draw (or the level draw), rounded to 4 ns ---
    random_bool = column('t_raman_pulse_random_bool')
    t_pulse_col = column('t_raman_pulse')
    fmin = column('t_raman_pulse_min_frac_pi')
    fmax = column('t_raman_pulse_max_frac_pi')
    try:
        block_bool = column('t_raman_pulse_block_bool')
    except (AttributeError, KeyError):
        block_bool = np.zeros(n_shots)
    if np.any(block_bool != 0):
        raise ValueError("[opx feedback] t_raman_pulse_block_bool != 0 is not "
                         "ported (only the plain uniform draw is).")
    if seeds is None:
        seed_col = column('t_raman_pulse_seed')
        seeds = np.array([new_t_raman_pulse_seed(int(round(s))) for s in seed_col],
                         dtype=np.int64)
    else:
        seeds = np.asarray(seeds).reshape(-1).astype(np.int64)
        if seeds.size != n_shots:
            raise ValueError("[opx feedback] seeds must have one entry per shot.")
    n_levels = int(c.n_levels)
    level_idx = None
    level_s = None
    d_s_drawn = np.empty((n_shots, N))
    if n_levels > 0:
        if not (np.all(random_bool != 0)):
            raise ValueError("[opx feedback] t_raman_pulse_n_levels > 0 needs "
                             "t_raman_pulse_random_bool = 1 (the level draw).")
        level_idx = np.empty((n_shots, N), dtype=np.int64)
        level_s = np.empty((n_shots, n_levels))
        for s in range(n_shots):
            level_s[s] = t_raman_pulse_level_set(c.t_pi, float(fmin[s]), float(fmax[s]),
                                                 n_levels, CLOCK_NS * 1e-9)
            d_s_drawn[s], level_idx[s] = draw_t_raman_pulse_list_levels(
                int(seeds[s]), N, c.t_pi, float(fmin[s]), float(fmax[s]), n_levels,
                CLOCK_NS * 1e-9)
        if not np.all(level_s == level_s[0:1]):
            raise ValueError("[opx feedback] the pulse-duration level set must be "
                             "the same on every shot (t_raman_pulse_min/max_frac_pi "
                             "cannot be scanned with t_raman_pulse_n_levels > 0).")
    else:
        for s in range(n_shots):
            if random_bool[s]:
                d_s_drawn[s] = draw_t_raman_pulse_list(
                    int(seeds[s]), N, c.t_pi, float(fmin[s]), float(fmax[s]))
            else:
                d_s_drawn[s] = np.full(N, float(t_pulse_col[s]))
    d_cc = s_to_cc(d_s_drawn, key='t_raman_pulse (drawn)').astype(np.int64)
    if np.any(d_cc < MIN_PULSE_CC):
        raise ValueError(
            f"[opx feedback] a drawn Raman pulse rounds to under {MIN_PULSE_CC} "
            f"cycles ({d_cc.min()} cc); the reset-model schedule needs every "
            f"pulse played without a guard branch (min frac {fmin.min():g} * "
            f"t_pi = {fmin.min() * c.t_pi:g} s).")
    d_s = d_cc.astype(float) * (CLOCK_NS * 1e-9)
    if level_s is not None:
        assert np.allclose(np.take_along_axis(level_s, level_idx, axis=1), d_s)

    # --- per-step intervals from the drawn list; the schedule is their cumsum ---
    gap_cc = feedback_step_gaps_cc(d_cc, c.t_img_cc, c.budget_cc, c.overhead_cc,
                                   c.extra_gap_cc, c.edge_cc)
    # the hold on the switch element after the Raman block: everything of
    # the step that is not the pulse, its re-block edge or the sync
    # overhead -- the imaging exposure runs concurrently with its start
    # (see the module docstring)
    wait_cc = gap_cc - d_cc - c.edge_cc - c.overhead_cc
    if np.any(wait_cc < MIN_PULSE_CC):
        raise ValueError(
            f"[opx feedback] the per-step hold on the switch element "
            f"({wait_cc.min()} cc) is under the {MIN_PULSE_CC}-cycle minimum.")
    t_start_ext_cc = extend_schedule_cc(d_cc, c)
    t_start_cc = t_start_ext_cc[:, :N]
    assert np.array_equal(t_start_cc[:, 1:], np.cumsum(gap_cc, axis=1)[:, :-1])
    t_start_s = t_start_cc.astype(float) * (CLOCK_NS * 1e-9)
    t_start_ext_s = t_start_ext_cc.astype(float) * (CLOCK_NS * 1e-9)

    # --- hypothesis grid per shot (the offset may be scanned) ---
    offset = column('feedback_fractional_initial_offset')
    span = column('feedback_guess_span_Omega')
    omega_grid = np.empty((n_shots, m))
    zidx = np.empty(n_shots, dtype=np.int64)
    for s in range(n_shots):
        g, z = feedback_grid_omega(
            None, fractional_initial_offset=float(offset[s]),
            guess_span_Omega=float(span[s]),
            frequency_raman_transition=c.omega_res / (2.0 * np.pi),
            t_raman_pi_pulse=c.t_pi, feedback_grid_size=m)
        omega_grid[s], zidx[s] = g, z
    w_grid = (omega_grid - c.omega_res) / c.Omega
    dw = w_grid[:, 0] - w_grid[:, 1]
    if not np.all(dw > 0.0):
        raise ValueError("[opx feedback] the hypothesis grid must be descending "
                         "with a positive step (feedback_guess_span_Omega > 0).")
    # the requested first drive (the unrounded offset, as ARTIQ) and the grid
    # index nearest to it: the OPX drive is always a grid index
    w_init = offset.astype(float).copy()
    d_init = nearest_grid_index(w_grid, w_init)

    d_sched = None
    if open_loop:
        idx = open_loop_drive_indices(m, N)
        d_sched = np.tile(idx.astype(np.int64), (n_shots, 1))

    # --- range checks for the fixed-point representation ---
    max_abs_delta = float(np.max((m - 1) * dw))
    if max_abs_delta > MAX_ABS_DELTA:
        raise ValueError(
            f"[opx feedback] the drive-hypothesis detuning can reach "
            f"{max_abs_delta:.2f} Omega (the grid span), above the "
            f"{MAX_ABS_DELTA} the axis tables (h^2 < 8) allow. Reduce "
            f"feedback_guess_span_Omega.")
    w_abs = float(np.max(np.abs(w_grid)))
    if not w_abs < QUA_FIXED_LIMIT:
        raise ValueError(f"[opx feedback] grid values reach {w_abs:.2f} Omega; "
                         f"they must fit QUA fixed (< 8).")
    if not float(np.max(np.sum(np.abs(w_grid), axis=1))) / 16.0 < QUA_FIXED_LIMIT:
        raise ValueError("[opx feedback] sum_j |w_j| / 16 must be < 8 for the "
                         "flat-rule posterior mean dot(P/4, w/4).")

    # --- per-pulse rotation scales, phase tables ---
    a = (d_s - c.t_offset_s) / (2.0 * c.t_pi)
    b = d_s / (2.0 * c.t_pi)
    if not (np.all(np.abs(4.0 * a) < QUA_FIXED_LIMIT)
            and np.all(np.abs(4.0 * b) < QUA_FIXED_LIMIT)):
        raise ValueError("[opx feedback] a Raman pulse longer than 4 t_pi does "
                         "not fit the fixed-point rotation scale.")
    h_max = float(np.max(np.sqrt(1.0 / 16.0 + ((m - 1) * dw / 4.0) ** 2)))
    if not float(np.max(np.abs(4.0 * a))) * h_max < QUA_FIXED_LIMIT:
        raise ValueError("[opx feedback] the rotation angle 4 a h (turns) can "
                         "leave the fixed-point range: shorten the pulses or "
                         "the grid span.")
    beta_max = float(np.max(4.0 * np.abs(b))) * float(np.max((m - 1) * dw)) / 4.0 \
        + 1.0 + abs(c.phi_LS)
    if not beta_max < QUA_FIXED_LIMIT:
        raise ValueError("[opx feedback] the z-rotation phasor seed angle can "
                         "leave the fixed-point range: shorten the pulses or "
                         "the grid span.")
    phi0, dphi = hypothesis_phase_tables(omega_grid / (2.0 * np.pi), t_start_ext_s)
    dphi0, ddphi = corotating_phase_tables(omega_grid / (2.0 * np.pi), t_start_ext_s)

    if_hz = None
    if terms is not None:
        if_hz = np.empty((n_shots, m, 2), dtype=np.int64)
        for s in range(n_shots):
            if_hz[s] = if_tables_hz(w_grid[s], c.f_Omega_hz, terms)

    return FeedbackShotTables(
        n_shots=n_shots, seed=seeds, d_cc=d_cc, d_s=d_s, level_idx=level_idx,
        level_s=level_s, gap_cc=gap_cc, wait_cc=wait_cc, t_start_cc=t_start_cc,
        t_start_ext_cc=t_start_ext_cc, t_start_s=t_start_s, a=a, b=b,
        phi0=phi0, dphi=dphi, dphi0=dphi0, ddphi=ddphi, omega_grid=omega_grid,
        w_grid=w_grid, dw=dw, zidx=zidx, w_init=w_init, d_init=d_init,
        d_sched=d_sched, if_hz=if_hz, open_loop=bool(open_loop), c=c)


# ---------------------------------------------------------------------------
# the QUA body
# ---------------------------------------------------------------------------

class _RunTable:
    """A host table that is a run constant (one QUA array, declared with its
    values) or varies per shot (a ctx.shot_array, indexed on the current
    shot). ``tab[expr]`` is the QUA cell either way."""

    def __init__(self, ctx, key, rows, dtype=float):
        rows = np.asarray(rows)
        if rows.ndim == 1:
            rows = rows[None, :]
        self.constant = bool(np.all(rows == rows[0:1]))
        self.values = rows
        if self.constant:
            qua = ctx.qua
            if dtype is int:
                self._arr = qua.declare(int, value=[int(v) for v in rows[0]])
            else:
                self._arr = qua.declare(qua.fixed, value=[float(v) for v in rows[0]])
            self._sa = None
        else:
            self._arr = None
            self._sa = ctx.shot_array(key, rows, dtype=dtype)

    def __getitem__(self, idx):
        if self._sa is None:
            return self._arr[idx]
        return self._sa.at(idx)


def _feedback_body(ctx: KexpShotContext, open_loop: bool, exp_lut_bits=None,
                   sincos_lut_bits=None):
    qua = ctx.qua
    from qm.qua import Math, Cast, Util
    p = ctx.p
    assign, declare, fixed = qua.assign, qua.declare, qua.fixed

    # ---- run constants (trace-time; refuse per-shot values) ----
    c = feedback_constants(lambda k: ctx.const(getattr(p, k)),
                           exp_lut_bits=exp_lut_bits,
                           sincos_lut_bits=sincos_lut_bits)
    N, m = c.N, c.m
    KT = 2 * m - 1
    t_acq = ctx.const(p.t_imaging_pulse_apd_abs)
    if abs(t_acq - c.t_img_s) > 1e-12:
        raise RuntimeError(
            f"[opx feedback] t_img_pulse ({c.t_img_s:g} s) must equal the APD "
            f"acquire window t_imaging_pulse_apd_abs ({t_acq:g} s): the "
            f"imaging exposure and the ADC window are one and the same.")
    mode_flag = int(ctx.const(p.update_raman_frequency_bool))
    if mode_flag != (0 if open_loop else 1):
        raise RuntimeError(
            f"[opx feedback] update_raman_frequency_bool = {mode_flag} but the "
            f"sequence is {'open-loop' if open_loop else 'closed-loop'}; set "
            f"it to {0 if open_loop else 1} so the run file says what ran.")

    # ---- the drive split: integer IF0s and slopes of the run transition ----
    terms = ctx.transition_offset_terms('raman')
    if set(terms) != {RAMAN_EL_80, RAMAN_EL_150}:
        raise RuntimeError(f"[opx feedback] expected the Raman drives "
                           f"{RAMAN_EL_80!r}/{RAMAN_EL_150!r}, got {sorted(terms)}.")
    if0_80, s80 = terms[RAMAN_EL_80]
    if0_150, s150 = terms[RAMAN_EL_150]
    f_run = ctx.const(p.frequency_raman_transition)
    # two-photon inverse of the split: both AOs in +1 order, double pass, so
    # f_two_photon = 2 * (f_150 - f_80); the integer IF0s reproduce the run
    # transition to within their rounding (<= 2 Hz)
    f_res_applied = 2.0 * (if0_150 - if0_80)
    if abs(f_res_applied - f_run) > F_APPLIED_TOL_HZ:
        raise RuntimeError(
            f"[opx feedback] 2*(IF0_150 - IF0_80) = {f_res_applied:.1f} Hz does "
            f"not reproduce frequency_raman_transition = {f_run:.1f} Hz (within "
            f"{F_APPLIED_TOL_HZ} Hz): the drive split is not the +1/+1 double "
            f"pass this sequence inverts in the finish hook.")
    if abs(2.0 * (s150 - s80) - 1.0) > 1e-9:
        raise RuntimeError(
            f"[opx feedback] the split slopes ({s80:g}, {s150:g}) do not "
            f"satisfy 2*(s150 - s80) = 1: a df offset would not move the "
            f"two-photon frequency by df.")

    # ---- per-shot host tables (sized from ctx.n_shots) ----
    T = build_feedback_shot_tables(lambda k: getattr(p, k).column, ctx.n_shots,
                                   c, open_loop=open_loop, terms=terms)
    n_shots = ctx.n_shots
    ctx.host_data('t_raman_pulse', T.d_s)
    ctx.host_data('t_raman_pulse_seed', T.seed.astype(float).reshape(n_shots, 1))
    ctx.host_data('omega_raman_mesh',
                  np.repeat(T.omega_grid[:, None, :], N + 1, axis=1))
    ctx.host_data('if_table_hz', T.if_hz.astype(float))
    # the derived containers are declared as host_data so use() registers
    # them with their shapes; the body has nothing to hand the OPX for them,
    # so they are NaN at trace time and the finish hook overwrites them
    for key in ('omega_raman', 't_pulse_start', 't'):
        ctx.host_data(key, np.full((n_shots, N), np.nan))
    ctx.host_data('probabilities', np.full((n_shots, N + 1, m), np.nan))

    levels = c.n_levels > 0
    d_arr = ctx.shot_array('t_raman_pulse_cc', T.d_cc, dtype=int)
    wait_arr = ctx.shot_array('t_wait_cc', T.wait_cc, dtype=int)
    cd0_arr = ctx.shot_array('cos_dphi0', np.cos(2.0 * np.pi * T.dphi0))
    sd0_arr = ctx.shot_array('sin_dphi0', np.sin(2.0 * np.pi * T.dphi0))
    cdd_arr = ctx.shot_array('cos_ddphi', np.cos(2.0 * np.pi * T.ddphi))
    sdd_arr = ctx.shot_array('sin_ddphi', np.sin(2.0 * np.pi * T.ddphi))
    if levels:
        lvl_arr = ctx.shot_array('level_idx', T.level_idx, dtype=int)
        a4_arr = b4_arr = None
    else:
        lvl_arr = None
        a4_arr = ctx.shot_array('theta_scale_x4', -4.0 * T.a)   # th = a4 * h
        b4_arr = ctx.shot_array('alpha_scale_x4', 4.0 * T.b)    # beta = b4 * (wq_d - wq_0) + phi_LS
    if np.all(T.zidx == T.zidx[0]):
        zidx = int(T.zidx[0])
    else:
        zidx = ctx.shot_array('zidx', T.zidx, dtype=int).at(0)
    if open_loop:
        sched_arr = ctx.shot_array('drive_schedule_idx', T.d_sched, dtype=int)
        d_init = None
    else:
        sched_arr = None
        d_init = (int(T.d_init[0]) if np.all(T.d_init == T.d_init[0])
                  else ctx.shot_array('drive_index_init', T.d_init, dtype=int).at(0))
    # the integer IF tables of the grid (run constant unless the grid is scanned)
    if80T = _RunTable(ctx, 'if_table_80_hz', T.if_hz[:, :, 0], dtype=int)
    if150T = _RunTable(ctx, 'if_table_150_hz', T.if_hz[:, :, 1], dtype=int)
    # the grid step as -dw/4 = wq_1 - wq_0 (per shot only if the span is scanned)
    dwq_rows = -T.dw / 4.0
    dwq = (float(dwq_rows[0]) if np.all(dwq_rows == dwq_rows[0])
           else ctx.shot_array('grid_step_wq', dwq_rows).at(0))
    ndwq_rows = T.dw / 4.0
    ndwq = (float(ndwq_rows[0]) if np.all(ndwq_rows == ndwq_rows[0])
            else ctx.shot_array('grid_step_wq_neg', ndwq_rows).at(0))
    # axis / matrix tables over k = j - d
    if levels:
        n_lev = c.n_levels
        lev_a = (T.level_s - c.t_offset_s) / (2.0 * c.t_pi)     # (n_shots, n_levels)
        lev_b = T.level_s / (2.0 * c.t_pi)
        mt = [level_matrix_tables(lev_a[s], float(T.dw[s]), m) for s in range(n_shots)]
        st = [level_seed_tables(lev_b[s], T.w_grid[s], c.phi_LS) for s in range(n_shots)]
        AmT = _RunTable(ctx, 'rot_Am', np.stack([t['Am'].reshape(-1) for t in mt]))
        BT = _RunTable(ctx, 'rot_B', np.stack([t['B'].reshape(-1) for t in mt]))
        CcT = _RunTable(ctx, 'rot_Cc', np.stack([t['Cc'].reshape(-1) for t in mt]))
        DT = _RunTable(ctx, 'rot_D', np.stack([t['D'].reshape(-1) for t in mt]))
        cthT = _RunTable(ctx, 'rot_cth', np.stack([t['cth'].reshape(-1) for t in mt]))
        cbT = _RunTable(ctx, 'seed_cos_beta', np.stack([t['cb'].reshape(-1) for t in st]))
        sbT = _RunTable(ctx, 'seed_sin_beta', np.stack([t['sb'].reshape(-1) for t in st]))
        cdbT = _RunTable(ctx, 'seed_cos_dbeta', np.stack([t['cdb'] for t in st]))
        sdbT = _RunTable(ctx, 'seed_sin_dbeta', np.stack([t['sdb'] for t in st]))
        if not (AmT.constant and cbT.constant):
            raise RuntimeError("[opx feedback] the (level, k) rotation tables "
                               "must be run constants: with "
                               "t_raman_pulse_n_levels > 0 the grid span and "
                               "the pulse-duration limits cannot be scanned.")
    else:
        ax = [axis_tables(float(T.dw[s]), m) for s in range(n_shots)]
        hT = _RunTable(ctx, 'axis_h', np.stack([t['h'] for t in ax]))
        uxT = _RunTable(ctx, 'axis_ux', np.stack([t['ux'] for t in ax]))
        uzT = _RunTable(ctx, 'axis_uz', np.stack([t['uz'] for t in ax]))
        ux2T = _RunTable(ctx, 'axis_ux2', np.stack([t['ux2'] for t in ax]))
        uxuzT = _RunTable(ctx, 'axis_uxuz', np.stack([t['uxuz'] for t in ax]))
    flat_rule = bool(c.flat_rule)
    if flat_rule:
        wq = _RunTable(ctx, 'w_grid_q', T.w_grid / 4.0)

    # ---- QUA state ----
    x = declare(fixed, size=m)
    y = declare(fixed, size=m)
    z = declare(fixed, size=m)
    L = declare(fixed, size=m)       # log-weights / scale
    M = declare(fixed)               # the previous pulse's max (lazy normalisation)
    d = declare(int)                 # drive: grid index
    koff = declare(int)              # (m - 1) - d: k-table offset
    kk = declare(int)
    jmax = declare(int)
    if80 = declare(int)              # applied integer IFs, Hz
    if150 = declare(int)
    pm = declare(fixed)              # measured photon fraction (scaled, then full)
    dwd = declare(fixed)             # wq_d - wq_0
    cb = declare(fixed); sb = declare(fixed); cdb = declare(fixed); sdb = declare(fixed)
    cg = declare(fixed); sg = declare(fixed); cg_n = declare(fixed)
    cdg = declare(fixed); sdg = declare(fixed)
    h = declare(fixed); ux = declare(fixed); uz = declare(fixed)
    th = declare(fixed); cth = declare(fixed); sth = declare(fixed); omc = declare(fixed)
    A1 = declare(fixed); Am = declare(fixed); E = declare(fixed)
    B = declare(fixed); Cc = declare(fixed); D = declare(fixed)
    x2 = declare(fixed); y2 = declare(fixed); z2 = declare(fixed)
    p1 = declare(fixed); q = declare(fixed); tt = declare(fixed)
    if levels:
        lvl = declare(int); lm = declare(int); kbase = declare(int)
        a4 = None; b4 = None; beta = None; dbeta = None
    else:
        a4 = declare(fixed); b4 = declare(fixed); beta = declare(fixed); dbeta = declare(fixed)
    sbits = int(c.sincos_lut_bits) if not levels else 0
    if sbits:
        n_sc = 2 ** sbits
        sc_shift = 28 - sbits
        scT = declare(fixed, value=[float(v) for v in sincos_lut_table(sbits)])
        ub = declare(int); fr28 = declare(int); ni = declare(int); rem = declare(int)
        frac = declare(fixed)
    if flat_rule:
        P4 = declare(fixed, size=m)      # exp(L) / 4: the sum stays < 8 for m <= 31
        dist = declare(fixed, size=m)
        e = declare(fixed); S4 = declare(fixed); invS4 = declare(fixed)
        mean4 = declare(fixed); jmean = declare(int)
        flat = declare(bool)
        lut_bits = int(c.exp_lut_bits)
        if lut_bits:
            n_lut = 8 * (2 ** lut_bits)
            lut_shift = 28 - lut_bits
            lutR = declare(fixed, value=[float(v) for v in exp_lut_table(lut_bits)])
            u_bits = declare(int); n_idx = declare(int); rem_e = declare(int)
            frac_e = declare(fixed)

    # ---- per-shot init: uniform prior, spin up ----
    with ctx.for_range(m) as j:
        assign(x[j], 0.0)
        assign(y[j], 0.0)
        assign(z[j], 1.0)
        assign(L[j], 0.0)
    assign(M, 0.0)
    if not open_loop:
        assign(d, d_init)

    min_d_cc = int(T.d_cc.min())

    # ---- the pulse loop ----
    with ctx.for_range(N) as i:
        if open_loop:
            assign(d, sched_arr.at(i))
        # (1) drive frequency for this pulse: the two integer IFs of grid
        #     point d, both drives (ratio split)
        assign(if80, if80T[d])
        assign(if150, if150T[d])
        ctx.set_frequency('raman', if80, which=RAMAN_EL_80)
        ctx.set_frequency('raman', if150, which=RAMAN_EL_150)
        # (2) the pulse, phase reset at the align in front of it, timestamped;
        #     min_cc: no per-shot guard branch (see the module docstring)
        ctx.raman_pulse(d_arr.at(i), phase_reset=True,
                        timestamp_key='t_pulse_start_cc', min_cc=min_d_cc)
        # (3) imaging exposure + ADC window, after the pulse
        ctx.align('raman', 'imaging')
        v = ctx.measure('apd', role='imaging', expose=True, t_expose=c.t_img_s)
        # (4) the per-step hold on the switch element (from the pulse-time
        #     list): the next reset-align lands on the schedule
        ctx.wait_cc(wait_arr.at(i), 'raman')

        # (5) the update (the measure above blocks until the ADC result
        #     exists; everything from here runs inside the hold)
        # measured photon fraction: ((raw - raw_down) * k1) * 2 ..., clamped
        # ONCE (the only clamp of the likelihood)
        assign(pm, (v - c.v_down_raw) * c.k1)
        lo, hi = P_MEAS_CLAMP[0] / c.n_split, P_MEAS_CLAMP[1] / c.n_split
        assign(pm, Util.cond(pm < lo, lo, pm))
        assign(pm, Util.cond(pm > hi, hi, pm))
        n = c.n_split
        while n > 1:
            assign(pm, pm * 2.0)
            n //= 2
        # per-pulse seeds: the k-table offset, wq_d - wq_0, the drive-
        # dependent phasor parts (trig, or (level, d) tables), the host's
        # cos/sin of the frame advances; C folded into the seed phasor
        assign(koff, (m - 1) - d)
        assign(dwd, Cast.mul_fixed_by_int(dwq, d))
        if levels:
            assign(lvl, lvl_arr.at(i))
            assign(lm, lvl * m + d)
            assign(cb, cbT[lm])
            assign(sb, sbT[lm])
            assign(cdb, cdbT[lvl])
            assign(sdb, sdbT[lvl])
            assign(kbase, lvl * KT + koff)
        else:
            assign(b4, b4_arr.at(i))
            assign(beta, b4 * dwd + c.phi_LS)
            assign(dbeta, b4 * ndwq)
            assign(cb, Math.cos2pi(beta))
            assign(sb, Math.sin2pi(beta))
            assign(cdb, Math.cos2pi(dbeta))
            assign(sdb, Math.sin2pi(dbeta))
            assign(a4, a4_arr.at(i))
        assign(cg, c.C * (cd0_arr.at(i) * cb - sd0_arr.at(i) * sb))
        assign(sg, c.C * (sd0_arr.at(i) * cb + cd0_arr.at(i) * sb))
        assign(cdg, cdd_arr.at(i) * cdb - sdd_arr.at(i) * sdb)
        assign(sdg, sdd_arr.at(i) * cdb + cdd_arr.at(i) * sdb)
        with ctx.for_range(m) as j:
            # rotation of hypothesis j about its axis (x-z plane of its
            # co-rotating frame), then the merged z rotation with C
            if levels:
                assign(kk, j + kbase)
                assign(Am, AmT[kk])
                assign(B, BT[kk])
                assign(Cc, CcT[kk])
                assign(D, DT[kk])
                assign(cth, cthT[kk])
                assign(E, (1.0 + cth) - Am)
            else:
                assign(kk, j + koff)
                assign(h, hT[kk])
                assign(ux, uxT[kk])
                assign(uz, uzT[kk])
                assign(th, a4 * h)                      # -4 a h = theta in turns
                if sbits:
                    assign(ub, Cast.unsafe_cast_int(th))
                    assign(fr28, ub - ((ub >> 28) << 28))       # the fraction of a turn, 28 bits
                    assign(ni, fr28 >> sc_shift)
                    assign(rem, fr28 - (ni << sc_shift))
                    assign(frac, Cast.unsafe_cast_fixed(rem << sbits))
                    assign(cth, scT[ni + n_sc // 4]
                           + frac * (scT[ni + n_sc // 4 + 1] - scT[ni + n_sc // 4]))
                    assign(sth, scT[ni] + frac * (scT[ni + 1] - scT[ni]))
                else:
                    assign(cth, Math.cos2pi(th))
                    assign(sth, Math.sin2pi(th))
                assign(omc, 1.0 - cth)
                assign(A1, omc * ux2T[kk])
                assign(Cc, omc * uxuzT[kk])
                assign(Am, cth + A1)
                assign(E, 1.0 - A1)
                assign(B, sth * uz)
                assign(D, sth * ux)
            assign(x2, (Am * x[j] - B * y[j]) + Cc * z[j])
            assign(y2, (B * x[j] + cth * y[j]) - D * z[j])
            assign(z2, (Cc * x[j] + D * y[j]) + E * z[j])
            assign(x[j], cg * x2 - sg * y2)
            assign(y[j], sg * x2 + cg * y2)
            assign(z[j], z2)
            # likelihood: expected photon fraction (midpoint remap when on),
            # sigma-scaled residual over sqrt(2 s), lazy max-normalisation
            # with the floor, one multiply for the decrement
            if c.mid_m_half != 0.0:
                assign(p1, 0.5 * (1.0 + z2) + c.mid_m_half * (1.0 - z2 * z2))
            else:
                assign(p1, 0.5 * (1.0 + z2))
            assign(q, (pm - p1) * c.inv_sigma_p_s)
            assign(tt, L[j] - M)
            assign(L[j], Util.cond(tt < c.L_floor, c.L_floor, tt) - q * q)
            # phasor recurrence (rotate to hypothesis j+1)
            assign(cg_n, cg * cdg - sg * sdg)
            assign(sg, sg * cdg + cg * sdg)
            assign(cg, cg_n)
        assign(jmax, Math.argmax(L))
        assign(M, L[jmax])
        if flat_rule:
            # ARTIQ's flat rule: normalise, weights e^L = (e^{L/s})^s kept
            # as P/4 (sum in [1/4, m/4]: inside fixed range and Math.inv's
            # domain); the mean = 4 * dot(P/4, w/4) / sum(P/4), snapped to
            # the nearest grid index
            with ctx.for_range(m) as j:
                assign(L[j], L[j] - M)
                if lut_bits:
                    assign(u_bits, Cast.unsafe_cast_int(L[j]))
                    assign(n_idx, (u_bits >> lut_shift) + n_lut)
                    assign(rem_e, u_bits - ((u_bits >> lut_shift) << lut_shift))
                    assign(frac_e, Cast.unsafe_cast_fixed(rem_e << lut_bits))
                    assign(e, lutR[n_idx] + frac_e * (lutR[n_idx + 1] - lutR[n_idx]))
                else:
                    assign(e, Math.exp(L[j]))
                for _ in range(c.k_exp):
                    assign(e, e * e)
                assign(P4[j], e * 0.25)
            assign(M, 0.0)
            assign(S4, Math.sum(P4))
            assign(invS4, Math.inv(S4))
            assign(flat, S4 > c.flat_threshold4)
            assign(mean4, Math.dot(P4, _wq_array(wq)) * invS4)
            with ctx.for_range(m) as j:
                assign(dist[j], Math.abs(wq[j] - mean4))
            assign(jmean, Math.argmin(dist))
        # (6) saves: the drive index, the model S_z, the normalised log-weights
        ctx.save('drive_index', d)
        ctx.save('s_z', z[zidx])
        with ctx.for_range(m) as j:
            assign(tt, L[j] - M)
            ctx.save('log_weights', tt)
        # (7) next drive (closed loop only)
        if not open_loop:
            if flat_rule:
                assign(d, Util.cond(flat, jmean, jmax))
            else:
                assign(d, jmax)


def _wq_array(wq: _RunTable):
    """The QUA array of a run-constant w/4 table (Math.dot needs a whole
    array; a per-shot grid cannot use the flat-rule mean)."""
    if not wq.constant:
        raise RuntimeError("[opx feedback] feedback_flat_rule_bool = 1 needs a "
                           "run-constant grid (the posterior mean is a Math.dot "
                           "over the whole w/4 array); do not scan the grid "
                           "with the flat rule on.")
    return wq._arr


# ---------------------------------------------------------------------------
# finish hook: derived containers on the host
# ---------------------------------------------------------------------------

def _rows(data, key, shape):
    """A container's execution-order array as (n_shots, *shape), or None."""
    dc = getattr(data, key, None)
    if dc is None:
        return None
    arr = np.asarray(dc._run_data)
    return arr.reshape(-1, *shape)


def _write(data, key, values):
    dc = getattr(data, key, None)
    if dc is None:
        print(f"[opx feedback] NOTE: no container {key!r} to fill.")
        return
    dc._run_data = np.asarray(values).reshape(dc._run_data.shape).astype(
        dc._run_data.dtype, copy=False)
    dc._data_gotten = True


def _scalar_param(p, key, default=None):
    try:
        return float(np.asarray(getattr(p, key), dtype=float).reshape(-1)[0])
    except AttributeError:
        if default is None:
            raise
        return float(default)


def scheduled_pulse_starts_s(p, d_s):
    """The pulse-start schedule (s from pulse 0) the OPX was held to,
    recomputed from the saved durations d_s (n_shots, N) and the params --
    the same function of both that the sequence shipped (step gaps from
    the pulse-time list, cumulative). Used by the finish hook's slip check
    and by the replay when no actual timestamps are wanted."""
    c = feedback_constants(lambda k: float(np.asarray(getattr(p, k), dtype=float)
                                           .reshape(-1)[0]))
    d_cc = np.rint(np.asarray(d_s, dtype=float) / (CLOCK_NS * 1e-9)).astype(np.int64)
    t_cc = schedule_pulse_starts(d_cc, c.t_img_cc, c.budget_cc,
                                 c.overhead_cc + c.extra_gap_cc,
                                 block_edge_cc=c.edge_cc)
    return t_cc.astype(float) * (CLOCK_NS * 1e-9)


def feedback_finish(expt, data):
    """Derive omega_raman (from drive_index + if_table_hz), probabilities
    (from log_weights and the saved scale), t_pulse_start (from the
    timestamps) and t from the raw containers (all in execution order; the
    normal end-of-run unshuffle follows). Shots the OPX did not run are NaN
    (opx_data_valid == 0) and stay NaN. Recomputes the schedule from the
    saved durations and prints the slip summary (a *** line if any pulse
    started off it)."""
    p = expt.params
    N = int(p.N_pulses)
    m = int(p.feedback_grid_size)
    t_img = float(p.t_img_pulse)

    mask_rows = _rows(data, 'opx_data_valid', (1,))
    apd = _rows(data, 'apd', (N,))
    n_shots = apd.shape[0] if apd is not None else mask_rows.shape[0]
    valid = (mask_rows.reshape(-1)[:n_shots] > 0) if mask_rows is not None \
        else np.ones(n_shots, dtype=bool)
    nan_rows = ~valid

    # the applied two-photon frequency of the driven grid index: both AOs
    # in +1 order, double pass -> f = 2 * (if_150[d] - if_80[d])
    didx = _rows(data, 'drive_index', (N,))
    if_tab = _rows(data, 'if_table_hz', (m, 2))
    if didx is not None and if_tab is not None:
        f_app = applied_frequency_hz(if_tab, didx)          # INT_MISSING -> NaN
        f_app[nan_rows] = np.nan
        _write(data, 'omega_raman', 2.0 * np.pi * f_app)
    else:
        dif = _rows(data, 'dif_hz', (N,))                   # pass-2 files
        if dif is not None:
            f_app = 2.0 * dif.astype(float)
            f_app[nan_rows] = np.nan
            f_app[dif < 0] = np.nan
            _write(data, 'omega_raman', 2.0 * np.pi * f_app)

    key, scale = 'log_weights', _scalar_param(p, 'feedback_log_weight_scale', LOG_WEIGHT_SCALE)
    if getattr(data, key, None) is None and getattr(data, 'log_weights4', None) is not None:
        key, scale = 'log_weights4', 4.0
    L_dc = getattr(data, key, None)
    if L_dc is not None:
        n_rows = int(L_dc._per_shot_data_shape[0])
        Lw = _rows(data, key, (n_rows, m)).astype(float)
        prob = np.full((n_shots, N + 1, m), np.nan)
        prob[:, 0, :] = 1.0 / m
        if n_rows == N + 1:
            prob[:, 1:, :] = log_weights_to_probabilities(Lw[:, 1:, :], scale)
        else:
            prob[:, 1:, :] = log_weights_to_probabilities(Lw, scale)
        prob[nan_rows] = np.nan
        _write(data, 'probabilities', prob)

    t_cc = _rows(data, 't_pulse_start_cc', (N,))
    d_s = _rows(data, 't_raman_pulse', (N,))
    if t_cc is not None:
        t_start = timestamps_cc_to_seconds(t_cc, valid=valid)
        _write(data, 't_pulse_start', t_start)
        if d_s is not None:
            _write(data, 't', t_start + d_s.astype(float) + t_img)
            # the slip check: the schedule the OPX was held to, from the
            # same durations and params, against the actual starts
            t_sched = scheduled_pulse_starts_s(p, d_s)
            slip = t_start - t_sched
            fin = np.isfinite(slip)
            n_ok = int(np.sum(valid))
            if fin.any():
                worst_cc = float(np.max(np.abs(slip[fin]))) / (CLOCK_NS * 1e-9)
                print(f"[opx feedback] slip: {worst_cc:.1f} cycles max |slip| "
                      f"over {n_ok} shots")
                if worst_cc > 0.5:
                    n_bad = int(np.sum(np.abs(slip[fin]) > 0.5 * CLOCK_NS * 1e-9))
                    print(f"[opx feedback] *** {n_bad} pulse(s) started off "
                          f"the schedule (max {worst_cc:.1f} cycles): the "
                          f"OPX overran the compute budget or the align "
                          f"overhead is not the assumed "
                          f"{float(p.t_opx_feedback_align_overhead) * 1e9:g} "
                          f"ns. The replay uses the actual timestamps; the "
                          f"real-time loop used the schedule. ***")
            else:
                print(f"[opx feedback] slip: no valid timestamps over "
                      f"{n_ok} shots")


# ---------------------------------------------------------------------------
# the sequence objects
# ---------------------------------------------------------------------------

def _measurements():
    return {
        'apd': lambda p: int(p.N_pulses),
        'drive_index': lambda p: Stream((int(p.N_pulses),), int),
        's_z': lambda p: int(p.N_pulses),
        'log_weights': lambda p: Stream((int(p.N_pulses),
                                         int(p.feedback_grid_size))),
        't_pulse_start_cc': lambda p: Stream((int(p.N_pulses),), int),
    }


def _host_data():
    return {
        't_raman_pulse': lambda p: int(p.N_pulses),
        't_raman_pulse_seed': 1,
        'omega_raman_mesh': lambda p: (int(p.N_pulses) + 1,
                                       int(p.feedback_grid_size)),
        'if_table_hz': lambda p: (int(p.feedback_grid_size), 2),
        # derived by the finish hook
        'omega_raman': lambda p: int(p.N_pulses),
        'probabilities': lambda p: (int(p.N_pulses) + 1,
                                    int(p.feedback_grid_size)),
        't_pulse_start': lambda p: int(p.N_pulses),
        't': lambda p: int(p.N_pulses),
    }


def make_feedback_sequence(open_loop=False, exp_lut_bits=None, sincos_lut_bits=None,
                           name=None) -> OPXSequence:
    """The per-shot OPX feedback sequence. open_loop=False: closed loop, the
    posterior picks every drive (feedback_fast.py). open_loop=True: the
    drive walks the grid on a fixed schedule (deterministic_bayesian.py)
    while the posterior still runs and is saved. exp_lut_bits /
    sincos_lut_bits: None = the run's params (opx_exp_lut_bits,
    opx_sincos_lut_bits; module defaults EXP_LUT_BITS / SINCOS_LUT_BITS);
    an int overrides it (0 = the Math call, exact)."""
    if name is None:
        name = SEQUENCE_NAME_OPEN_LOOP if open_loop else SEQUENCE_NAME
    bits = None if exp_lut_bits is None else int(exp_lut_bits)
    sbits = None if sincos_lut_bits is None else int(sincos_lut_bits)

    def body(ctx):
        _feedback_body(ctx, open_loop, exp_lut_bits=bits, sincos_lut_bits=sbits)
    body.__name__ = name
    body.__qualname__ = name

    seq = OPXSequence(body, name=name, claims=('raman', 'imaging'),
                      measurements=_measurements(), host_data=_host_data(),
                      finish=feedback_finish)
    seq.exp_lut_bits = bits
    seq.sincos_lut_bits = sbits
    return seq


bayesian_feedback = make_feedback_sequence(False)
bayesian_feedback_open_loop = make_feedback_sequence(True)

__all__ = [
    'bayesian_feedback', 'bayesian_feedback_open_loop', 'make_feedback_sequence',
    'EXP_LUT_BITS', 'SINCOS_LUT_BITS', 'LOG_WEIGHT_SCALE', 'MIN_PULSE_LEVELS',
    'exp_lut_table', 'exp_lut_emulation', 'sincos_lut_table', 'sincos_lut_emulation',
    'axis_tables', 'level_matrix_tables', 'level_seed_tables',
    'corotating_phase_tables', 'extend_schedule_cc', 'nearest_grid_index',
    'if_tables_hz', 'applied_frequency_hz', 'IF_TABLE_COLUMNS',
    'feedback_finish', 'feedback_constants', 'build_feedback_shot_tables',
    'FeedbackConstants', 'FeedbackShotTables', 'log_weights_to_probabilities',
    'log_weights4_to_probabilities', 'timestamps_cc_to_seconds',
    'scheduled_pulse_starts_s', 'volts2raw', 'open_loop_drive_indices',
    'feedback_step_gaps_cc',
    'BLOCK_EDGE_CC', 'P_MEAS_CLAMP', 'P_MEAS_SPAN_MAX', 'MAX_ABS_DELTA',
    'F_APPLIED_TOL_HZ', 'STREAM_KEYS', 'HOST_KEYS', 'HOST_KEYS_OPEN_LOOP',
    'DERIVED_KEYS', 'RAMAN_EL_80', 'RAMAN_EL_150',
]
