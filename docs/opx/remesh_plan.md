# Remesh with pole-return for the OPX feedback loop — design plan

Date: 2026-09-25. Status: **plan only, nothing implemented.** Builds on the
reset-phase-model port (`feedback_port_report.md`) and on the ARTIQ remesh code
in `kexp/base/feedback.py` (`maybe_remesh`, `remesh_to_centered`, and the
never-used `re_initalize_spin_vector`).

## 1. What is being asked

Once the posterior over resonance hypotheses is (a) single-peaked and (b)
narrower than a threshold, run a corrective Raman pulse that drives the atoms
back to the nearest pole of the Bloch sphere, computed from the most likely
Bloch-sphere position given the posterior; then reset the prior to a known
state (a shorter Bloch vector along the pole) and continue on a finer grid
centred on the best estimate.

## 2. Why the ARTIQ remesh cannot be ported as is

`remesh_to_centered` re-grids in place and carries the hypotheses' Bloch
vectors onto the new grid by nearest-neighbour or linear interpolation. That is
only meaningful for the *z* components. The transverse components of
neighbouring hypotheses differ in azimuth by `(omega_j − omega_j') · t`, where
`t` is the time since the phase origin: for a 21 kHz grid step and `t = 1 ms`
that is 132 rad. Interpolating `x, y` between hypotheses whose azimuths differ
by many turns produces a vector with no physical meaning, and the finer the
new grid, the worse it gets (the new step is smaller, but the azimuth spread
across the *old* neighbours that the interpolation reads from is unchanged).

The pole-return pulse is precisely the cure: at a pole the state is
azimuth-free, so the whole grid can be reset to one common state and the
phase origin can be moved to the corrective pulse. This is what makes a
remesh well-defined in the reset model, and it is why the corrective pulse and
the grid reset must be one operation.

## 3. The corrective rotation

### 3.1 Physical Bloch vector of each hypothesis

Hypothesis `j` carries `s_j = (x_j, y_j, z_j)` in its own rotating frame.
With the reset phase model, the physical azimuth of its transverse part
relative to the drive phase (0 at every pulse start) at a pulse starting at
`t` is rotated by the hypothesis-frame phase `phi_j(t) = −omega_j t` (mod 2π),
the same quantity the posterior already computes per pulse through the
phasor recurrence. So the physical vector is

    x_j^phys =  x_j cos(phi_j) + y_j sin(phi_j)
    y_j^phys = −x_j sin(phi_j) + y_j cos(phi_j)          (sign to be verified, §7)
    z_j^phys =  z_j

### 3.2 The best single rotation given the posterior

A resonant pulse rotates about an equatorial axis `n = (cos ψ, sin ψ, 0)` by
`θ`. The z component after the pulse is

    z' = z cos θ + sin θ · (cos ψ · y^phys − sin ψ · x^phys).

The expected outcome over the posterior is linear in the *posterior-mean
physical Bloch vector* `s̄ = Σ_j P_j s_j^phys = (X̄, Ȳ, Z̄)`:

    E[z'] = Z̄ cos θ + sin θ · (cos ψ · Ȳ − sin ψ · X̄).

Maximising it:

    T̄ = sqrt(X̄² + Ȳ²),   ψ* = atan2(−X̄, Ȳ),   θ* = atan2(T̄, Z̄),   E[z']_max = |s̄|.

Three limits show this is the right rule:

- **sharp posterior** (`P_j = δ_{jj*}`): `s̄ = s_{j*}^phys`, and `ψ*, θ*` are
  exactly `re_initalize_spin_vector`'s `arctan2(−x, y)` and
  `arctan2(sqrt(x²+y²), z)` — the rotation the user described;
- **azimuth unknown** (the posterior's frequency width `σ_ω` satisfies
  `σ_ω t ≫ 1`, so the `phi_j` of the supported hypotheses spread over the full
  circle): `T̄ → 0`, `θ* → 0` if `Z̄ > 0` and `θ* → π` if `Z̄ < 0` — a flip when
  the state is in the lower hemisphere, no pulse otherwise. Any equatorial axis
  works for a π pulse, which is why no azimuth knowledge is needed;
- **in between**: a partial rotation whose gain is `|s̄| − |Z̄|`.

The `atan2` rule maximises `z'`, so it always ends on **+z**: the reset state is
`s_reset = (0, 0, |s̄|)`, a Bloch vector along +z whose length is *reduced* by
the measurement back-action already in `s_j` and by the azimuth uncertainty.
That is the "known state with reduced Bloch vector length" the prior is reset
to. The *nearest* pole differs when `θ* > π/2` (for an unknown azimuth, when
`Z̄ < 0`): rotating by `θ* − π` about the same axis gives
`z' = −(Z̄ cos θ* + T̄ sin θ*) = −|s̄|` with the smaller rotation `π − θ*`, and
`z_reset = −|s̄|`. A negative angle is played as the angle `π − θ*` about the
reversed axis `ψ* + π`. The `remesh_pole` parameter selects: 1 = nearest
(`min(θ*, π − θ*)`, target ±z accordingly), 2 = always up (`θ*`, up to a π
pulse, reset to the prepared +z state). *(Corrected 2026-09-25: the first
version of this plan had the two options reversed.)*

### 3.3 Realising the rotation on the OPX

- Frequency: the pulse is played at the posterior mean (or MAP) frequency, as
  any other pulse, through `set_transition_offset`.
- Axis azimuth `ψ*`: `frame_rotation_2pi` on the Raman drives before the
  pulse. The two-photon phase is `2(φ_150 − φ_80)` for the +1/+1 double-pass
  pair, so a frame rotation of `ψ*/2` turns on `raman_150` (or `±ψ*/4` split
  over both drives) sets the two-photon phase to `ψ*`. The reset that lands at
  the align before the pulse zeroes the IF phase, and the frame phase survives
  it (`reset_if_phase` does not touch the frame; `reset_frame` does) — so the
  order is: `reset_if_phase` (both), `frame_rotation_2pi(ψ*/2)`, align, play,
  then `reset_frame` after the pulse so the next probe starts at frame 0.
- Angle (`θ*`, or `π − θ*` about `ψ* + π` for the nearest pole below the
  equator): duration `θ/Ω = 2 θ_turns · t_π`, in cycles
  `Cast.mul_int_by_fixed(t_pi_x2_cc, θ*_turns)`, plus the switch-path turn-on
  offset; the model's `dt_ideal` for this pulse is the coherent area.
- Both `ψ*` and `θ*` come from `Math.atan2_2pi` (QOP ≥ 2.4; the lab runs 2.6).
- **No `if_` branch.** To keep the schedule deterministic the corrective pulse
  should occupy the *next pulse slot* with the same statements as a probe:
  duration `Util.cond(flag, d_corr, d_i)`, frame rotation `flag · ψ*/2` (0 for
  a probe), frequency from the usual control law. The imaging measurement that
  follows then measures `z ≈ |s̄|` and validates the pole return in-loop. The
  pulse train length stays `N_pulses`; the phase tables stay indexed by pulse
  index; the one thing that changes per pulse is the origin (below).

## 4. Trigger: single-peaked and narrow enough

All quantities come from one pass over the `m` hypotheses. **Cost note (pass
3b):** the shipped argmax-only loop no longer forms the weights `P_j` (only
log-weights), so enabling the remesh brings back a weights pass (exp from the
table ≈ 16 cycles per point, plus the sums), evaluated every pulse to stay
branch-free — roughly +1.5 µs per pulse by the statement-cost table; time it
on the simulator before enabling.

| quantity | how | used for |
|---|---|---|
| not flat | `S4 ≤ m/4.6` (needs the weights pass above) | (a) |
| unimodal mass | `Σ_{|j − jmax| ≤ k} P_j ≥ remesh_unimodal_mass` (k = `remesh_unimodal_window` grid steps) | (a) |
| width | posterior std in Ω from `Σ P w²/4` tables (w/4 keeps squares < 8) | (b), ARTIQ's `feedback_remesh_threshold_Omega` |
| expected reset length | `|s̄|` from §3.2 (`X̄, Ȳ, Z̄` accumulated in the same loop that rotates the phasors) | (c): only remesh if `|s̄| ≥ remesh_min_bloch_length`, else the reset state carries no information and more probes are better |
| counters | ARTIQ's `remesh_after_n_good_shots` / `remesh_reset_counter_threshold_fraction` semantics, `remesh_max_levels`, `n_initial_shots_before_remesh` | hysteresis |

The width criterion is stated in Ω like ARTIQ's, but its physical meaning is
now explicit through `|s̄|`: at `t ~ 1 ms` a posterior width of 0.05 Ω (3.5 kHz)
makes `T̄ ≈ 0` — the remesh will practically always be a dephase-and-flip, not a
tilted rotation. That is fine (the reset works either way); `|s̄|` is the
quantity that tells the estimator how much it keeps. Expect `|s̄|` to be set
mostly by `|Z̄|`, which after the last measurement's damping (`C = 0.62` on
`x, y` only) is typically 0.3–0.8.

## 5. The remesh itself (on the OPX, in the same pulse slot)

1. New grid: centre = posterior mean snapped to the nearest **old** grid
   point (keeps every hypothesis-phase increment host-precomputable, §6),
   span = old span × `remesh_scale_factor`, clamped inside the original bounds
   exactly as `remesh_to_centered` does; `omega_raman_mesh` row `i+1` records it.
2. Log-weights: linear interpolation of the old posterior onto the new grid
   (fractional index arithmetic, `Cast.to_int` for the floor, `Util.cond` at the
   edges), or uniform, per `remesh_interpolate_posterior`; then the usual
   max-renormalisation.
3. States: every hypothesis set to `(0, 0, z_reset)` with `z_reset = ±|s̄|`
   (sign per `remesh_pole`). No interpolation of states, by construction.
4. Phase origin: the per-hypothesis phase accumulators are zeroed at the
   corrective pulse (its start time is the new `t = 0`); its own timestamp is
   in `t_pulse_start_cc` like any pulse.
5. Drive for the next probe: the control law on the new grid (flat rule as
   now, but from the new `P`).

## 6. Phase bookkeeping with a movable origin

Today the host precomputes `phi0_i, dphi_i = frac(−f_grid[0] t_i), frac(−Δf t_i)`
from the schedule with the origin at pulse 0. A remesh at a data-dependent
pulse moves the origin and changes the grid, so the per-pulse phase must be
built on the OPX from **increments**: keep one phase phasor per hypothesis and
advance it every cycle by the host-precomputed per-cycle increment
`frac(f_j Δt_i)` (Δt_i = the per-step gap from the pulse-time list, known on the
host), which is `frac(f_c Δt_i) + (j − c) · frac(dw_ℓ Δt_i)` — a base term for
the centre point (in the old grid's table because the centre is snapped to it)
and a step term per remesh level ℓ. Tables per shot: `N_pulses × (m + n_levels)`
values, host-precomputed, shipped as shot arrays. Zeroing the accumulators is
the origin reset. Fixed-point drift of an accumulator is `2^-28` per addition,
negligible over 20 pulses.

Cost: per hypothesis per pulse, one phasor rotation (4 mul + 2 add) replaces
today's phasor recurrence — the same order of work — plus the `s̄` accumulation
(6 mul + 3 add). The remesh branch (interpolation, `atan2_2pi` ×2, the
duration) runs once per level; it should be measured in the simulator like the
rest (B's timing table) and folded into the compute budget.

## 7. Sign conventions that must be pinned before use

1. The physical-azimuth rotation in §3.1 (which way `phi_j` rotates `x, y`)
   must match `generate_posterior`'s axis construction — verify offline by
   applying the model's own rotation to `s_{j*}` and checking it lands on
   the pole (unit test on the numpy oracle).
2. Which drive's frame to rotate and the sign of `ψ*` on hardware: a Ramsey
   phase scan (π/2 – wait – frame-rotated π/2) fixes the mapping between
   `frame_rotation_2pi` and the model's azimuth. This is a prerequisite
   measurement (M4 in the milestone list).
3. The rotation-angle sign (`θ = −|H| dt` in the model) fixes whether the
   corrective duration goes with `+θ*` or `−θ*`.

## 8. Data to save (minimal, in the spirit of the port)

Per pulse, in addition to the existing containers: `pulse_kind (N)` (0 probe,
1 pole-return), `t_raman_pulse` becomes the *applied* duration (the corrective
slot's duration is OPX-computed: stream it as an int of cycles and let the
finish hook merge it into `t_raman_pulse`), `pole_return_psi_turns (N)` and
`pole_return_z_reset (N)` (0 / NaN on probe slots). `omega_raman_mesh` and
`probabilities` already have a row per pulse. That is enough for the replay to
reproduce the decision and re-simulate.

## 9. Replay and tests

- `FeedbackOPXReplay`: reproduce the trigger and the rotation from the saved
  posterior (`compare_with_opx` extends to the remesh decision), re-simulate
  with the recorded `pulse_kind`, or counterfactually with a different
  threshold; `simulate_feedback_run_apd` gains the remesh so RMSE with and
  without it can be compared on synthetic truth (as the pulse-schedule study
  in `draw_t_raman_pulse_list_blocks` did).
- Tests: numpy oracle of §3–§6 vs `generate_posterior` + `remesh_to_centered`
  for the parts that overlap; pole-return unit test (sharp posterior lands on
  the pole; azimuth-unknown posterior reduces to the flip); fixed-point range
  checks on the new intermediates; trace test asserting no `if_` in the body;
  simulator compile and timing.

## 10. Parameters (new, in `expt_params_feedback_opx.py`)

`remesh_enable_bool` (0), `remesh_pole` (1 = nearest, 2 = always up),
`remesh_unimodal_window` (grid steps), `remesh_unimodal_mass` (0.9),
`remesh_min_bloch_length` (0.3), `remesh_max_levels` (2), plus the inherited
`feedback_remesh_threshold_Omega`, `remesh_scale_factor`,
`remesh_after_n_good_shots`, `remesh_reset_counter_threshold_fraction`,
`remesh_interpolate_posterior`, `n_initial_shots_before_remesh`
(`remesh_interpolate_states` becomes meaningless: states are always reset).

## 11. Risks and open questions

- The azimuth-uncertainty budget (§4) means the tilted rotation is rarely
  reachable; the design still delivers the reset. Whether a dephasing step
  (extra imaging pulses with no Raman pulse, each multiplying `x, y` by `C`)
  before the flip improves `|s̄|` enough to be worth its time is a simulation
  question for the replay.
- The corrective slot's data-dependent duration keeps the interval to the next
  pulse deterministic only because the gap list is per step (`wait_cc[i]` is
  recomputed from `d_corr` in QUA: `wait = gap_i − d_corr − …`, integer
  arithmetic).
- `Math.atan2_2pi` cost and precision are undocumented; measure.
- Hardware prerequisites: M1–M3 as before, plus the Ramsey phase-scan (M4)
  for the frame-rotation sign.

Estimated effort: 2–3 days for sequence + oracle + replay + tests, plus the
hardware sign check.
