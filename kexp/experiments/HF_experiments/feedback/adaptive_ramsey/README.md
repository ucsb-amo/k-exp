# Adaptive Ramsey — design note (2026-10-30, not yet run on hardware)

Built from the 2026-10-29/30 night's discussion of longer gaps and the saturating posterior width
(session log `outputs\2026-10-29_19-40_night_summary\log.md`, 00:21 and 00:26). Everything below
is a design plus a model-only simulation; nothing has been run on the machine.

## What the feedback loop is, physically

Every step of `FeedbackExpt.feedback_loop` is a Ramsey step: the gap between two Raman pulses is a
free evolution in the drive's frame, the next pulse maps the accumulated phase onto S_z, the weak
APD read samples it (noise σ_sz ≈ 2·std_n/N ≈ 0.73 per read at the 10-29 evening calibration, and
each read scales the transverse Bloch vector by C ≈ 0.84). The posterior
(`Feedback.generate_posterior`) already propagates every hypothesis' Bloch vector exactly through
arbitrary gaps, phases and pulse areas. The production protocol fixes the gap at the hardware
floor (~66 µs), draws random pulse areas (0.5–1 π) and hops the drive to the MAP.

Two measured facts frame the design:

* **Aliasing at 1/T.** With every gap equal, the posterior is periodic in detuning with period
  1/T (15–21 kHz). Alternating gaps removed the first alias tooth (10-07/08).
* **Width saturation.** The final width saturates near 1.5 kHz and stretching all later gaps by
  2–8× (`longgap_sim.py`, 10-30) did not narrow it: ~5–6 reads carry information (C^k), and a long
  gap aliases unless the posterior is already narrower than 1/T.

## The protocol

Within one shot (no re-pumping, no posterior across shots — user rule 10-07):

1. the drive frequency stays fixed at the initial offset; every pulse is π/2;
2. after each read the kernel **chooses the next gap and the next pulse's two-photon phase** from
   the posterior (`kexp.base.adaptive_ramsey.ramsey_plan_next`, the same `@portable` code the
   simulator runs);
3. the estimate is the posterior after the last read (MAP on the grid, or the mean).

Default rule (`PHASE_MAXVAR` + `GAP_MAXVAR`): maximize the **posterior variance of the predicted
S_z** over the phase (closed form: the largest eigenvector of the 2×2 posterior covariance of the
transverse vectors rotated into the drive frame) and over a few candidate gaps (multiples of the
hardware floor). For a weak read with fixed Gaussian noise the expected information gain is
½ ln(1 + Var/σ_sz²), monotone in Var, so this is one-step Bayesian experimental design. It handles
both regimes with one rule: a broad, multimodal posterior (unavoidable here — the floor already
makes the first fringe 7–15 kHz, under the 12 kHz prior span) is split by the read that spreads its
lobes most; a unimodal posterior of width σ gives Var ∝ (2πσT)² until the fan wraps, so the chosen
gap grows as 1/σ — the textbook adaptive schedule, with no tuned gap factor. Aliased hypotheses
predict the same S_z and add nothing to Var, so an aliasing gap is never picked for its own sake.

Alternatives kept for comparison (`kexp.analysis.adaptive_ramsey.DEFAULT_POLICIES`): the
posterior-mean-parallel phase rule (zero expected S_z, steepest slope), the MAP-parallel rule
(policy_sim's "maxslope", which lost to production on a fixed gap), a σ-driven gap
(T = g/σ), a doubling schedule, random phases (the non-adaptive control), production's random
durations with and without drive hops.

### Why the mean-parallel rule alone is not enough

The posterior-mean transverse vector R = |E[e^{iδt}]| is the posterior's characteristic function
at the gap time. At the hardware floor (90 µs at grid 41) R collapses to ~0.1 for a 12 kHz prior:
no phase gives a steep slope, the σ-based gap stays at the floor, and the loop never leaves the
aliased regime (first smoke test, this folder's simulator). The variance rule does not need R.

## The information budget (why gains are bounded)

With σ_sz = 0.73 per read and C = 0.84, even a perfect protocol collects at most
Σ_k ½ ln(1 + C^{2k}·f/σ_sz²) nats over 12 reads: 2.25 nats (f = 1, an ideal two-lobe split every
read) or 1.30 nats (f = ½, a uniformly fanned posterior). From a 12 kHz uniform prior that is a
Gaussian-equivalent σ of **~300 Hz (ideal) to ~800 Hz (fanned)**. Production ends near 1 kHz
median error. So the protocol can buy at most ~1.5–3×; the larger levers are the read SNR (the
10-29 morning readout, N 614 / std 132, gives ~150 Hz on the same budget) and the per-read
coherence. State this with every result.

## Hardware considerations (the test experiment)

`adaptive_ramsey.py` (class `AdaptiveRamseyExpt(FeedbackExpt, AdaptiveRamsey)`):

* **Phase control.** Synchronized DDS phase mode with the phase origin at the start of the train
  (as `check_twist` / `raman_ls_ramsey`); `RamanBeamPair.set(relative_phase=θ)`
  `t_ramsey_phase_set_pretrigger_mu` before each pulse. No fast-frequency-update staging (the drive
  never hops). **The sign of θ in the model is unverified** (`ramsey_phase_sign`); the first data
  run must be `PHASE_RANDOM` and scored with `kexp.analysis.adaptive_ramsey.phase_sign_check`
  (log evidence under ±θ). An adaptive run under the wrong sign picks the worst phase every pulse.
* **Timing.** The gap floor is production's formula with the phase-set pretrigger and a slack that
  is a guess: posterior (0.7 µs/point) + plan (~0.35 µs/point/candidate) + 35 µs. Grid 41 with
  4 candidates → ~135 µs floor (first fringe 7.4 kHz). `initialize_feedback` times one posterior
  update and one plan step and records `data.ramsey_timing = [t_posterior, t_plan, slack]` every
  shot, and warns loudly if less than 15 µs of slack remains. Raise
  `t_calculation_slack_compensation_mu` before trusting anything; `save_on_underflow` keeps what
  was taken.
* **End state.** As `FeedbackExpt`: Raman shutter and tweezer off in the shot; the scanner's
  cleanup resets the coils on normal completion and in the RTIO handlers, and runs
  `cleanup_abort_kernel` (the safe state) before any other exception goes on. The only new
  hardware action is the DDS phase register write.
* **Gap cap 300 µs (user, 10-30 morning: "our coherence time is a limitation there").**
  `t_ramsey_gap_max` = 300 µs in the kernel defaults, the experiment params and the simulator's
  policy default. With the ~150 µs floor the max-variance candidates ×1…8 collapse to two distinct
  gaps (floor and 300 µs); the simulation numbers above were taken with a 1 ms cap and are not
  re-run.
* **v2 (`adaptive_ramsey_v2.py`, reviewer change 10-30 02:4x).** Records per pulse the timeline
  margin of the phase write, `data.ramsey_set_margin` = cursor after `set()` minus the pulse time
  (negative = in time), and warns above −2 µs. Smoke pass = negative with room on every pulse. v1 is
  kept unchanged for provenance; run v2.
* **Recorded per pulse** (`data.ramsey_*`): gap taken, phase (model convention), the maximized
  quality, posterior std and mean; plus the base containers (apd, probabilities per pulse, …).
  `run_arrays_from_atomdata(ad)` → `replay_posterior(...)` re-scores a run on any grid or sign.

## First-run checklist

1. `/test-experiment` run-only, 3 offsets × 1, `N_pulses` 4: compile, no underflow,
   `data.ramsey_timing` against the slack, gaps and phases recorded, `probabilities` finite.
2. A `PHASE_RANDOM` run (set `p.ramsey_phase_policy = 3`), ≥ 60 shots: `phase_sign_check`.
   Decide the sign from the evidence difference; record both numbers.
3. Only then adaptive runs, interleaved with the production feedback file on the same calibration,
   scored against a Ramsey truth as the night did (`fb_score.py`), fine-grid replay for both.

## Simulation results (model physics, optimistic)

`C:\lab\skynet_log\outputs\2026-10-30_01-10_adaptive_ramsey\` (`*/results.json`, `*/comparison.png`).
Grid 41 over 12 kHz, 12 pulses, truths at 0 / +777 / −2345 Hz from the nominal resonance, fine-grid
(241-point) replay, errors vs the injected truth. Caveats on every number: the posterior's own model
is the truth (no free-evolution dephasing, no field jitter unless the run says so), the read model
fails the hardware simulation checks (10-29), the slack is a guess (floor ~135 µs here).

| policy (720 shots each, `followup_fixed_gap_phase`) | MAP median \|err\| (Hz) | P(\|mean err\| < 1 kHz) | posterior std (Hz) | train (ms) |
|---|---|---|---|---|
| production (random areas, drive hops, fixed gap) | 850 ± 56 | 0.62 ± 0.02 | 3113 | 1.29 |
| fixed gap, π/2, no phase control | 845 ± 135 | 0.66 ± 0.02 | 3302 | 1.28 |
| **fixed gap, π/2, max-variance phase** | **553 ± 35** | 0.61 ± 0.02 | **2386** | 1.28 |
| fixed gap, max-variance phase, random areas | 897 ± 61 | 0.62 ± 0.02 | 2770 | 1.29 |
| mild gap adaptation (×1, 1.5, 2 floor) + max-var phase | 864 ± 84 | 0.60 ± 0.02 | 2363 | 2.17 |
| gap candidates ×1, 2, 4, margin 0.3 | 1012 ± 179 | 0.40 ± 0.02 | 3303 | 2.49 |

From `main_grid41` (360 shots each): full adaptive gaps (×1…8 floor) 1902 ± 415 Hz, with drive hops
3436 ± 535, doubling schedule 1077 ± 125, random phases + adaptive gaps 2548 ± 418 — all worse than
the fixed floor gap; the σ-driven gap rule never leaves the floor; the mean-parallel phase rule
gives nothing (812 ± 214). The phase-control gain holds in the variants: grid 21 (723 vs 900 Hz),
500 Hz per-shot jitter (506 vs 662), truth coherence 0.72 vs the model's 0.84 (1225 vs 1425).

**Reading:** on this machine the protocol is floor-limited. Any gap longer than the floor aliases
over the 12 kHz prior, and the greedy variance rule, which does not see beyond one read, prefers the
longest candidate. "Adaptive Ramsey" here therefore reduces to **adaptive phase at the fixed gap**:
~35 % lower MAP error and a ~25 % narrower posterior, but **no change in the fraction of posterior
means within 1 kHz** (the posterior stays multimodal; the MAP lands in the right lobe more often).
Coverage is 1.00 everywhere: the posterior is over-wide under its own model. The information bound
above says the remaining room is ≤ 2–3× and sits in the read SNR, not in the protocol.

Tests: `k-exp/tests/test_adaptive_ramsey.py` (policies, simulator, replay, sign check) and
`test_adaptive_ramsey_compiles.py` (the kernel compiles, default and random-phase policies).
