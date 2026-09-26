# Bayesian frequency feedback on the OPX+ — port report

Date: 2026-09-25 (pass 3b). Status: **offline-tested and compiled/timed on the
QOP simulator; never run with atoms.** Hardware prerequisites in §7.

## 1. What was ported

The per-shot loop of `kexp/base/feedback.py` + `HF_experiments/feedback/base_expt_feedback.py`
(N_pulses cycles of Raman pulse → 5 µs imaging pulse → posterior update over a
grid of two-photon resonance hypotheses → next drive frequency) now runs as a
QUA sequence on the OPX between the ARTIQ handoff and hand-back. ARTIQ keeps
tweezer preparation, `prep_raman()` (switch-AOM warm-up with the shutter
closed), imaging detuning/power, the handshake, hold, release and the
absorption image.

| piece | file |
|---|---|
| QUA sequence (`bayesian_feedback`, `bayesian_feedback_open_loop`), host tables, finish hook | `kexp/experiments/opx_sequences/feedback.py` |
| params (inherits `expt_params_feedback.py`) | `kexp/experiments/HF_experiments/feedback/expt_params_feedback_opx.py` |
| ARTIQ experiments (closed loop; open-loop grid sweep, the analog of `deterministic_bayesian`) | `.../feedback/feedback_opx.py`, `feedback_opx_deterministic.py` |
| replay / re-simulation | `kexp/analysis/feedback_opx.py` (`FeedbackOPXReplay`, `FeedbackOPXReplayResult`, `posterior_update_fixed_point_emulation`, `run_shot_fixed_point_emulation`, `true_bloch_step`) |
| host helpers shared with the kernel model | `kexp/base/feedback.py` (additive: `feedback_grid_omega`, `hypothesis_phase_tables`, `schedule_pulse_starts`) |
| tests (28 items) | `k-exp/tests/test_feedback_opx.py` |
| framework features the port needed | `kexp/control/opx/context.py` (`for_range`, `shot_array`, `save`, timestamps, `phase_reset`, `min_cc`, `set_frequency` with QUA ints, `transition_offset_terms`, `wait_cc`), `sequence.py` (`Stream`, `host_data`, `finish`), `manager.py` (2-D/int/host containers, shot-index echo, provenance) |

## 2. The phase model, and why it forces exact timing

Per user directive the port does **not** reproduce ARTIQ's FTW phase tracker.
Immediately before every pulse both Raman drives get `reset_if_phase`, applied
by `align(raman_80, raman_150, raman_switch)`; the `play('pass', ...)` on the
switch is the next statement on that element. The two-photon drive phase at
every pulse start is therefore 0 (plus a hardware constant common to all
pulses), and the posterior is ARTIQ's `generate_posterior` with
`phase_raman_pulse_start = 0` and the hypothesis term `−omega_j t_i`.

Consequence: between pulses the atom–drive phase advances by `omega_0 dt`, i.e.
119.4639 MHz × 4 ns = **0.478 turns per OPX clock cycle**, so pulse-start
times must be exact in cycles. In the hypothesis rotating frame the state is
static between pulses (only pulse starts enter the model, through the axis
azimuth; z-rotations commute), so imaging, hand-back and gap timings do not
enter. The port therefore:

- makes every per-step interval come from the drawn pulse-time list, as
  ARTIQ's `compute_t_between_pulses_mu` does per step: on `raman_switch` each
  pulse is `align(reset)` → `pass d_i` → `block` (4 cc) → `align(raman, imaging)`
  → `wait(wait_i)` with `wait_i = t_img + 4 cc + budget + t_feedback_extra_gap`,
  shipped per shot and pulse as an int array; the imaging exposure and
  `measure` run on `imaging_switch`/`apd` concurrently with the start of that
  wait. Scheduled starts: `t_{i+1} = t_i + d_i + 4 cc + wait_i + overhead`;
- timestamps the Raman `pass` play of every pulse (`t_pulse_start_cc`, the only
  timestamp saved) and uses the actual times in the replay; the finish hook
  recomputes the schedule from the saved durations and prints a `***` line
  with the maximum slip if any pulse deviates;
- the host precomputes the hypothesis phase tables from the schedule.

Simulator (QOP simulator through `OPXBench`, 2026-09-25, N = 6, m = 21, budget
10 µs, a DC level on the APD input so the weights are nontrivial): every
interval equals the schedule plus a **constant 82 cycles (328 ns)** on all
five intervals (86 cycles with discrete durations; separate parameters), and
the slip against the schedule is zero on every pulse.
A jitter-tolerant "continuous" model (`keep_phase=True` + host-tracked
detuning phase) was designed but not built.

## 3. Exact applied frequency

The drive is always a grid point: the control law picks the posterior argmax
(§4), and the initial drive snaps to the grid point nearest the initial offset
(the grid is built around the rounded offset and shifted by up to half a step
so one point lands on resonance, e.g. an offset of 2.0 starts the drive at
2.1 in the simulator config). For every grid point the host computes the two
integer drive IFs once per run from the Raman split
(`ctx.transition_offset_terms`), and the OPX applies `if_table[d]` with
`ctx.set_frequency(..., which=)`. The sequence streams the driven index
`drive_index` per pulse and saves the integer table as `if_table_hz (m, 2)`, so
the applied two-photon frequency is known exactly: `2 (if150 − if80)` for the
+1/+1 double-pass pair. The finish hook derives `omega_raman` from it. QM
documents no finite NCO quantum beyond "sub-Hz resolution"; the integer Hz
commanded is taken as applied. The config IF rounding puts the `w = 0` drive
within 2 Hz of `frequency_raman_transition`.

## 4. Numerics on the OPX (QUA fixed point, [-8, 8))

Units `w = (omega − omega_res)/Omega`; the drive is grid index `d`, so
`delta_j = (d − j)·dw` and every axis quantity (`|H|/Ω`, `Ω/|H|`, `u_z`) comes
from host tables indexed by `k = j − d` (length 2m − 1), with no `inv_sqrt`.
The Bloch vectors are kept in a co-rotating azimuth frame: the pre-rotation of
the Rodrigues step vanishes and the light-shift and frame z-rotations merge
into one phasor that is linear in `j` (the back-action damping folded in),
seeded by two table-driven trig pairs per pulse and stepped by angle
addition. The rotation angle's cos/sin comes from a 12-bit sine table with
interpolation (`opx_sincos_lut_bits`; 0 = `Math.cos2pi/sin2pi`). The likelihood
uses `p1` with the midpoint remap (monotonic for a midpoint in (0.25, 0.75),
so no clamps) and `p_meas` clamped once per pulse to [-2, 3]. Log-weights are
stored as `L/32` (`feedback_log_weight_scale`), which leaves room for the
largest possible per-pulse decrement without any per-point clamp, and are
max-normalised lazily with a derived floor of −78.5 nats. The control law is
the posterior argmax (`feedback_flat_rule_bool = 0`): ARTIQ's flat rule never
fired in 6000 model-consistent synthetic pulses, and dropping it removes the
exp/sum/inv/dot pass; flag 1 restores it with the mean snapped to the grid.
Optionally (`t_raman_pulse_n_levels ≥ 4`) the pulse durations are drawn from a
discrete level set, and the whole rotation matrix per (level, k) comes from
tables, with no trig at all.

Agreement with the double-precision ARTIQ posterior (`generate_posterior`,
phase 0), 6 seeds × 20 pulses: with exact trig P0 and `s_z` agree to ~1e-10
and every decision is identical; with the sine table P0 agrees to ≤ 5e-7 and
`s_z` to ≤ 3e-7, decisions identical. The previous L/4 representation with a
7.9σ clamp was not benign under model mismatch (it changed 32 % of argmax
decisions at 4× noise); L/32 matches the unclamped posterior to 2e-8 there.
Fixed-point truncation flips about 1 % of argmax decisions at near-ties, so the
replay expects ≥ 99 % agreement with the OPX, not 100 %.

### Compute speed (QOP simulator, m = 21, per pulse after the imaging exposure)

| structure | compute per pulse |
|---|---|
| pass 2: fused loop, `inv_sqrt`, exp table, flat rule | 4875 cc = 19.5 µs |
| pass 3b, exact trig | 2043 cc = 8.2 µs |
| **pass 3b, 12-bit sine table (default)** | **1938 cc = 7.75 µs** |
| pass 3b, 16 discrete durations | 1074 cc = 4.3 µs |

Statement costs behind the design (cycles per grid point): `Math.inv_sqrt` 64,
`Math.exp` 60, `cos2pi` + `sin2pi` 28, sine-table lookup 24, the full new
per-point update 75–82 with trig and 33 with discrete-duration tables;
`Math.argmax` ≈ 3.5 per entry (225 over 64 entries, so ≈ 74 for our 21), once
per pulse.

`t_opx_feedback_compute_budget = 10 µs` (≈ 35 % margin for the default). With
it every simulated interval equals the schedule plus a constant sync overhead
of 82 cycles (continuous durations) or 86 cycles (discrete levels); both are
parameters (`t_opx_feedback_align_overhead[_levels]`) and with them the
simulated slip is zero on every pulse. The overhead matters for the real-time
estimate: the OPX's posterior uses the *scheduled* starts, and one cycle of
error is 0.478 turns of hypothesis phase. The flat-rule structure has not been
timed. Per cycle now ≈ `d_i + 5 µs + 10 µs + 0.33 µs` ≈ 19–23 µs against
ARTIQ's 57–61 µs.

What did not help, measured: issuing the Bloch prediction before or after the
pulse statements (classical statements run serially with the element's pulse
stream; `measure` blocks it), deferring the log-weight saves, unrolling the
grid loop (did not compile within 120 s), and **multi-core parallelism**. The
OPX+ has one core per element with a hardware sync path, but on QOP 2.6 the
compiler emits all classical statements as one sequential stream: splitting
the hypotheses into K = 2, 3, 4 blocks bound to spare elements ran 2–8 %
slower, a same-core control was indistinguishable, and per-iteration ticks
were queued to the pulsers up front. Offloading to stream processing is
impossible (one-way, millisecond latency).

## 5. Data saved per shot (minimal; ARTIQ names kept)

Streams: `apd (N)` (volts), `drive_index (N)` (int), `s_z (N)`,
`log_weights (N, m)` (L/32), `t_pulse_start_cc (N)` (int cycles, the only
timestamp: in the hypothesis frame the state is static between pulses, so only
pulse starts enter the model); framework: `opx_data_valid`, `opx_shot_index`.
Host: `t_raman_pulse (N)` (4 ns-rounded), `t_raman_pulse_seed (1)`,
`omega_raman_mesh (N+1, m)`, `if_table_hz (m, 2)`. Derived at finish:
`omega_raman (N)` (rad/s, exact applied), `probabilities (N+1, m)` (row 0
uniform), `t_pulse_start (N)` (s from pulse 0), `t (N)` (= start + d + t_img,
ARTIQ's convention). Run-file attributes: `opx_qua_program`, `opx_machine`,
`opx_shot_tables`. The finish hook recomputes the schedule from the saved
durations and prints a `***` line if any pulse slipped.

Replay: `ad = atomdata(run_id, roi_id='auto'); fr = FeedbackOPXReplay(ad);
res = fr.replay_measured(); fr.compare_with_opx()` — double-precision replay on
the actual timestamps and the exact applied frequencies
(`control_omega_source='measured'|'recomputed'|'override'`),
`emulate_fixed_point=True` for the OPX arithmetic incl. its tables,
`simulate_counterfactual(...)`, `simulate_feedback_run_apd(...)`, and
`scheduled_starts_rr` to recompute the schedule. `compare_with_opx` reports the
argmax agreement fraction against the expected ≥ 99 %.

## 6. Planned: remesh with pole-return

`remesh_plan.md` designs the remesh for the reset model: when the posterior is
single-peaked, narrow, and the posterior-mean physical Bloch vector `s̄` is
long enough, a corrective pulse rotates `s̄` to the pole (axis `atan2(−X̄, Ȳ)`,
angle `atan2(T̄, Z̄)`; reduces to the MAP rotation for a sharp posterior and to
a flip-if-inverted when the azimuth is unknown, which at 1 ms it is unless the
width is below ~160 Hz), every hypothesis is reset to `(0, 0, ±|s̄|)`, the
phase origin moves to that pulse, and the grid is re-centred and shrunk. It
occupies a probe slot with `Util.cond`-selected duration and a frame rotation
so the schedule stays branch-free, and needs one new hardware measurement
(a Ramsey phase scan to pin the frame-rotation sign).

## 7. Placeholders and hardware prerequisites

| parameter | value now | run needed |
|---|---|---|
| `v_apd_all_up_opx`, `v_apd_all_down_opx` | copied from ARTIQ run 78309 (wrong scale on the OPX) | M3: `apd_voltage_vs_state_2.py` with the OPX playing the pulses, then `apd_pulse_analysis_measured_pi.ipynb`, in OPX `demod2volts` units (settle the factor-2 convention, `time_of_flight` and the APD sign first — the simulator integrated +0.16 V DC to −0.195 raw, inverted relative to the `demod2volts` convention) |
| `std_photon_fraction_opx` | 0.1592 | same run |
| `t_raman_pulse_offset_opx` | 127 ns (ARTIQ DDS path) | M2: OPX-driven flop; `t_raman_pi_pulse` re-measured at the OPX drive amplitude (dds defaults vs ARTIQ's √0.3) |
| `t_opx_feedback_align_overhead` / `_levels` | 328 / 344 ns (simulator) | any hardware run (`***` slip line); re-measure whenever the loop structure changes, and before using the flat-rule structure |
| `t_opx_feedback_compute_budget` | 10 µs (simulator: 7.75 µs default, 8.2 µs exact trig) | confirm, then tighten |
| `t_raman_pulse_n_levels` | 0 (continuous) | a 10k-seed synthetic comparison before switching on (4–16 levels were within ≤ 2σ of continuous at 1000 seeds) |

Also M1 (trigger → block latency vs 350 ns, hand-back slack, halt-mid-block
line state, port-less sticky acceptance — the port compiled with them) and
`reset_if_phase` vs the intensity servo.

## 8. Known limitations

- Remesh not ported yet (plan above); `feedback_remesh_threshold_Omega` must
  be 0. The alternating random/constant schedule is refused.
- `frequency_raman_transition` and `t_raman_pi_pulse` must be run constants.
- Without remesh the grid is coarse: a truth less than half a grid step off
  a grid point can end several Ω wrong after a shot (the hypothesis phase
  drifts many turns), which is what the remesh plan targets.
- The APD sign on the simulator input is inverted (+0.16 V DC integrated to
  raw −0.195); M3 must settle sign and scale.
- ARTIQ quirk surfaced by the oracle: `generate_posterior` truncates
  `n = int(N_photons)` while `k` stays float (~1e-3 in P0 at N = 1336.2); the
  OPX carries only σ/N.
