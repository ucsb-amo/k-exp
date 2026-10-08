# alias_grid — inter-pulse-time aliasing of the feedback hypothesis grid (2026-10-07/08)

Copies of the session files used on 2026-10-07/08 (session log `C:\lab\skynet_log\2026-10-07_13-38_1.md`,
working folder `C:\lab\skynet_log\outputs\2026-10-07_13-38_aliasing_analysis\` with REPORT.md, figures and data).
Placed here, uncommitted, so the structure can be reviewed; the production procedure still runs from the
session copies in the skynet outputs folders. Nothing in the repository base (`base_expt_feedback.py`,
`kexp/base/feedback.py`, `kexp/analysis/feedback.py`) was changed.

## What the problem is

The posterior update rotates the drive axis by `phase − ω_j·t` at each pulse start; with pulse starts at
multiples of a period T, hypotheses `ω_res + n/T` predict the same axes at every pulse. Measured on 85351,
85352, 85213, 85214: the posterior is a comb with teeth exactly at n/T (21.3 kHz fast path, 15.0 kHz standard),
the first aliases carry 70–98 % of the resonance mass, and the production grid's hit rate depends on where its
0.25 Ω points fall on the comb (`q = step_Hz × T`; dips at integer and half-integer q). Details: REPORT.md
findings 1–5 and Addenda 1–6 in the outputs folder.

## Experiment files (the inheritance chain)

| file | class | adds |
|---|---|---|
| `base_expt_feedback_fast.py` | `FeedbackExptFast(FeedbackExpt)` | 2026-10-06 fast step: ADC read overlapped with the posterior's propagation, next read pre-issued; slack 20 µs at 21 points |
| `base_expt_feedback_alt.py` | `FeedbackExptAlt(FeedbackExptFast)` | per-pulse extra inter-pulse delay `p.t_gap_extra_list_mu[i]` built from `p.t_gap_cycle_extra_us` (e.g. `[0, 15]` µs = alternating gaps); records the gap used after every pulse in `data.dT_mu` |
| `base_expt_feedback_grid.py` | `FeedbackExptGrid(FeedbackExptAlt)` | grid step from the pulse period: `q = step_Hz × T_long = n + frac` (frac 0.4, n auto), span derived and written to `feedback_guess_span_Omega`; `grid_step_Omega()` for placing offsets on grid points; `maybe_remesh` snapped to the same rule |

Run files (each imports its base from its own directory):

| file | arm / purpose | grid | gaps | shots |
|---|---|---|---|---|
| `feedback_alt2_test.py` | run-only test of the alternating gap (85397 PASS) | 21 × 0.25 Ω | [0, 20] µs | 5 + 3 |
| `feedback_alt2.py` | ALT2 data arm, cycles 1–2 (85419, 85429) | 21 × 0.25 Ω | [0, 20] µs | 420 + 20 |
| `feedback_grid_test.py` | run-only test of the rule grid with remesh ON (85435; replay cannot follow a remesh) | 15, q 2.4 | [0, 15] µs | 5 + 3 |
| `feedback_grid_test_noremesh.py` | same with remesh off (85436 PASS, replay max ΔP 8.5e-5) | 15, q 2.4 | [0, 15] µs | 5 + 3 |
| `feedback_narrow_test.py` | one comb period only: n 0, frac 1/14 (85437) | 15 over ±1/(2T) | single fast gap | 65 + 20 |
| `feedback_alt2_g15.py` | ALT2 arm on the rule grid, 9 pulses, slack 18 µs (cycle from 2026-10-08 00:14) | 15, q 2.4 | [0, 15] µs | 195 + 20 |
| `random_bayesian_alt2_g15.py` | NAALT2 arm (non-adaptive drive list on the same grid/base) | 15, q 2.4 | [0, 15] µs | 195 + 20 |

`bench/timing_bench_g15.py` is the 2026-09-29 timing bench with a `BENCH_GRID` environment knob
(`bench_batch_g15.sh "16 14 12 10"` ran 85431–85434: floor 14 µs at 15 points; `bench_analyze.py` summarizes).

## Analysis (`analysis/`)

All read-only on run data; they write their outputs next to themselves, so run them from a copy in an outputs
folder, not from here.

- `alias_replay_gaps.py` — `FeedbackReplayGaps`: the replay engine reading `data.dT_mu`. **Mandatory for any
  run with alternating gaps** (the stock `FeedbackReplay` replays them on the wrong timeline: max |ΔP| 0.3–1.0).
- `alt2_test_check.py`, `grid_test_check.py`, `narrow_check.py` — per-run pass/fail checks (gap pattern, time
  base, replay agreement; grid rule vs the kernel's mesh; one-period localization).
- `alias_replay.py` → `alias_analysis.py`, `alias_folded.py` — fine-grid replays (321/641 points), comb figures,
  folded-comb and Rayleigh tests, production-grid alias-proximity test.
- `alt2_analyse.py` — pre-registered P1–P4 scorer for the ALT2 / FBF / FB / NAALT2 cycles.
- Synthetic design checks on the as-written model: `alias_schedule_sim.py` (schedules), `alias_order_sweep.py`
  (hit vs q), `alias_cycle_sim.py` (2/3/4-gap cycles), `alias_gap_sim.py` (random extra delay),
  `alias_altspacing_sim.py` (extra delay vs the rule grid), `policy_sim.py` (pulse-steering policies: none beat production).

## Design notes

`DESIGN_grid_rule.md` (choices and implications of the q-rule grid, 15 points, 9 pulses, remesh rule, one-period
grid, alternation spacing) and `PLAN_gap_cycles.md` (the alternating-gap test plan and its status).

## Candidate repository port (not done)

`t_gap_extra_list_mu` + the `dT_mu` container into `base_expt_feedback.py` / `data_vault_feedback.py`, the
`dT_mu`-aware `_compute_dT_rr_mu` into `kexp/analysis/feedback.py`, and the grid rule into `Feedback` or
`ExptParams`; `AGENTS.md` / wiki notes on the comb and on q.

Added 2026-10-08 morning: `drift_check.py` (did the resonance drift? no), `ls_asymmetry_check.py` (replay with the stored
light shift varied), `asym_check.py` (final MAP bin and drive path by offset sign: the mirror-image mechanism),
`mirror_sim.py` (model is symmetric; hold-the-drive remedies). See REPORT.md Addendum 8 in the outputs folder.
