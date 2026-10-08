# Design: grid step from the pulse period, 17 points, remesh on the same rule, one-period grid

Written 2026-10-07 ~23:15 before building (session 2026-10-07_13-38_1). User instruction: "set the grid to
initialize by a fraction of T — start with 0.4 and the grid discretized to 17 points (remeasure minimum
timing). Generalize the remesh rule to also use the good spacing rule to avoid comb. Also test out a run for
a very narrow grid span (only covering one comb spacing around the true resonance)."

## 1. The rule

The quantity that decides whether a grid neighbour sits on an alias tooth is

    q = Δf_grid · T_ref        (grid step in Hz × pulse-start period; k·q for the k-th neighbour)

so the grid is now defined by **q = n + φ**, with φ = `feedback_grid_alias_frac` (0.4 to start) and n =
`feedback_grid_alias_order` (an integer; −1 = choose automatically). Everything else follows:

    Δf_grid = (n + φ) / T_ref,   step_Ω = Δf_grid / f_Rabi,   span_Ω = step_Ω · (m − 1) / 2,   m = 17.

`feedback_guess_span_Omega` becomes a **derived** quantity written at prepare time (it is still what the
kernel's `_initialize_frequency_grid` reads, so the kernel, the saved params and the replay stay as they are).

**Why φ = 0.4 is a good choice.** With four neighbours on each side considered (k = 1..4), the distance of
k·q from the nearest integer is at least 0.2 for φ ∈ {0.2, 0.4, 0.6, 0.8} and nothing does better; the
measured plateau of the hit rate is frac(q) ∈ ~[0.1, 0.4] ∪ [0.6, 0.85] with dips at 0 and 0.5. For φ = 0.4
the k = 1..5 neighbours sit at 0.4, 0.2, 0.2, 0.4, 0 orders from a tooth: the 5th neighbour is on one (harmless
at 5 steps from resonance, where the posterior is already low; it is what today's standard path has at q = 2.2).

**Which T when the gaps alternate.** ALT2 has two gap classes (46.9 / 66.6 µs now). `T_ref` = the **longest**
gap class (param `feedback_grid_alias_T_ref = "long"`; "short" and "mean" accepted). Reason: the long gap makes
the finest comb (smallest 1/T) and is the one the alternation removes least cleanly at the production-grid
level (its own comb is gone, 1.05, but the short-gap comb survives at 1.26); defining q on the long gap and
then *reporting* q for the short gap is the transparent choice. With n = 2, φ = 0.4 and today's timing:
q_long = 2.4 → Δf = 36.0 kHz = 0.273 Ω; q_short = 1.69, whose k = 3 neighbour is 0.07 orders from a short-gap
tooth — acceptable only because the short-gap comb is weak under alternation; the prepare-time printout
flags any neighbour within 0.1 order of a tooth for the reference gap and 0.05 for the other. For a
single-gap schedule (FBF/FB) there is one T and one q.

**Automatic n.** n = round(0.25·f_Rabi·T_ref − φ), the integer that keeps the step nearest the legacy 0.25 Ω
(today: 2.2 − 0.4 = 1.8 → n = 2). It is printed and recorded; the user can pin it.

## 2. Implications of the rule

- **The span is no longer ±2.5 Ω.** With m = 17 and n = 2: ±8 × 0.273 = ±2.18 Ω (±288 kHz). The current
  offset scan, linspace(−2.5, 2.5, 21), would put the resonance *outside* the grid for |offset| > 2.18 (4 of 21
  points), shots that can never hit by construction. The run files therefore take their offsets from the
  grid: **offsets = step_Ω × k, k = −7..7** (15 values, up to ±1.91 Ω), so the initial drive and the resonance
  are both grid points and the snap is zero. With 13 repeats that is 195 shots (~22 min).
- **The step is set in Hz, so it moves with f_Rabi and with T.** A Rabi-frequency change of 10 % changes the
  step in Ω by 10 % (q stays 2.4); a slack change changes T and hence the step in Hz. q is the invariant now,
  the step in Ω is not: hit rates before and after today are not bin-for-bin comparable (bin 0.25 → 0.273 Ω,
  chance 1/21 → 1/17). The pre-registered fine-grid metrics (MAP within ±0.04 Ω, mass, folded comb) are
  unaffected and remain the comparison across designs.
- **Everything downstream still works.** `feedback_guess_span_Omega` and `feedback_grid_size` are saved per
  run, `FeedbackReplay` rebuilds the grid from them (`_grid_for_offset`), and `alias_replay.py` uses
  20·(m − 1) + 1 fine points (321 at m = 17). Only the scorer's q column, which assumed a 0.25 Ω step, needs
  to read the real step (patched).

## 3. 17 points and the timing

The posterior cost is linear in m: production 16.1 µs → ~13.0 µs; the fast path's post-read half 6.1 → ~4.9 µs.
The slack floor on the fast path was measured at 21 points (16 µs runs, 14 µs underflows; 20 µs chosen for a
4 µs margin against DRTIO stalls). **Re-measurement**: the 09-29 timing bench (`timing_bench.py`, mode 2 =
the fast path, 200 pulses × shots, no atoms) with `feedback_grid_size = 17` at slack 20 / 16 / 14 / 12 µs
(3 shots each, ~1 min per run) → floor; the production slack for 17 points is then floor + 4 µs, as today.
A shorter slack shortens T, i.e. widens the comb; the grid rule absorbs that because it is evaluated at
prepare time from the actual slack. Bench runs produce no feedback data (bench containers only) and leave
cooling beams and tweezers off; the pre-run audit is in §6.

## 4. Remesh on the same rule

`maybe_remesh` (kernel, in `Feedback`) halves `feedback_remesh_span_Omega` and re-grids. The generalization:
before re-gridding, the requested span is converted to q_req = step_req · T_ref and **snapped to the nearest
n + φ** (n ≥ 0), span = that step × (m − 1)/2. Consequences with m = 17, φ = 0.4: the remesh ladder from
q = 2.4 is 2.4 → 1.4 (±1.27 Ω) → 0.4 (±0.36 Ω, step 6 kHz, 6.4 periods wide) → 0.4 (floor: the grid never
gets finer than φ/T per step, i.e. it never samples *inside* one comb period with several points unless n = 0
and φ is set small on purpose, see §5). The snap only moves the span, never the centre; the clamp to the
original bounds is unchanged. Remesh stays **off** in the cycle (`feedback_remesh_threshold_Omega = 0`); the
generalized rule is exercised in the run-only test with a deliberately loose threshold so the code path
compiles and runs. Replay does not remesh (known limitation), so a remeshing run cannot be replay-validated;
this is why remesh stays off in the data cycle.

## 5. The one-period ("very narrow") grid

The same rule with **n = 0, φ = 1/16**: Δf = 1/(16 T_ref) → 16 steps = exactly one comb period, grid span
±1/(2 T_ref) around the initial drive, every tooth outside the span. On the single-gap fast schedule (T = 46.9 µs
today; chosen because "one comb spacing" is well defined only for a single period) that is ±10.7 kHz = ±0.081 Ω,
step 1.33 kHz ≈ the measured tooth width. Offsets = step × k, k = −6..6 (±8.0 kHz), 5 repeats = 65 shots + 20
warm-ups (~8 min). What it tests: whether a single shot localizes within one period when the prior excludes
the other periods — the fine-grid replays say the mass inside ±5 kHz is only ~5 % of a ±2.5 Ω grid, but the
folded posterior shows the tooth at 1.6–1.8× the mean, so the expected per-shot hit is modest; the useful
outputs are the posterior width in kHz and the hit within one 1.33 kHz bin, not a yes/no. It is a test run,
not part of the cycle.

## 6. Files, order of operations, audit

Session copies only (my folder `expts/`): `base_expt_feedback_grid.py` = `FeedbackExptGrid(FeedbackExptAlt)`
with the rule in `finish_prepare`, `grid_step_Omega()` for the run files, and the remesh override;
`feedback_grid_test.py` (run-only, ALT2 gaps, 17 pts, φ 0.4, remesh enabled loosely, 5 offsets × 1);
`feedback_narrow_test.py` (fast single gap, n 0, φ 1/16, 13 offsets × 5); `feedback_alt2_g17.py` for the
cycle; the 09:37 session's `random_bayesian` copy needs only the base import and `feedback_grid_size = 17`.
`timing_bench_g17.py` = the 09-29 bench with the grid size from the environment.

Order at the handover: (1) bench 20 / 16 / 14 / 12 µs → floor; (2) set the slack in the run files = floor + 4;
(3) run-only grid test → gap pattern, replay agreement (gap-aware), printed q table; (4) narrow test;
(5) hand the files to the 09:37 session; cycle resumes ALT2 > NAALT2 on the 17-point rule grid.

Hardware/end-state audit: the feedback files touch exactly what `feedback_alt2.py` touched (audited in
PLAN §3). The bench (from its docstring and `run()`): imaging light and Raman pulses only, no MOT load,
no tweezers, cooling beams powered down; same cleanup path on completion; it is the file run 10 times on
09-29 (83757–83812). Each `ar` launch goes through the run lock and the hook's hardware-run prompt.

## 7. What is deliberately not done

- No change to the repository; no calibration constants touched; the alternating gap list stays [0, 20] µs.
- No attempt to make the grid adaptive to measured comb phase; q is set from the planned timing, which is
  exact to the ±1 µs pulse-duration jitter (±0.03 in q).
- The 21 → 17 change halves nothing else: N_pulses 17, repeats and warm-ups as the user set them.

---

## Update 23:2x — user changes while building: 15 points, 9 pulses, alternation spacing

- **m = 15** (not 17). Rule unchanged; with n = 2, φ = 0.4 and today's timing: step 36.3 kHz = 0.275 Ω, span
  ±7 × 0.275 = **±1.93 Ω**, q_long 2.40, q_short 1.67 (neighbours of the short-gap comb at 0.33, 0.35, 0.02 (!),
  0.30 orders from a tooth for k = 1..4: the k = 3 neighbour sits on a short-gap tooth; tolerated because the
  short-gap comb is the weak one under alternation, flagged by the prepare-time printout). Offsets k = −7..7
  (15 values) still fit inside the span. One-period grid: n = 0, φ = 1/14 → 14 steps = one period, step
  1/(14 T) = 1.52 kHz at T = 46.9 µs, span ±10.7 kHz = ±0.081 Ω.
- **N_pulses = 9** per preparation for every arm (was 17). Consequences: a single shot carries roughly half the
  information (the Bloch length after 9 measurements is ~0.72^4 ≈ 0.3 instead of ~0.05, so the last pulses are
  no longer wasted, but the total is still less); the comb teeth are broader (~1/(8T) ≈ 2.7 kHz at 46.9 µs
  instead of ~1.5 kHz); the shot is ~0.5 ms shorter. The timing bench is per step and unaffected.
- **Alternation spacing X and q are coupled.** The grid rule fixes q on the long gap T_f + X, so the short
  gap's comb sees q_short = q · T_f/(T_f + X). Both fractional parts should sit on the plateau: for n = 2,
  φ = 0.4 that means X ≈ 18–23 µs (q_short 1.60–1.73); X = 10 µs would put q_short at 1.98 (the ±1
  neighbours on the short-gap tooth), X = 30 µs at 1.46 (the half-integer dip). The comb-*breaking* strength
  grows with X/T_f (it is the phase scatter 2π·X/(2 T_mean) between the two pulse classes), while the time
  cost is X/2 per pulse. `alias_altspacing_sim.py` sweeps X = 0..40 µs with the rule grid, m 15, 9 pulses;
  result in Addendum 5 of REPORT.md. X stays at 20 µs unless the sweep says otherwise.
