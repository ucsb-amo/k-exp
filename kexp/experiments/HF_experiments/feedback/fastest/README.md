# Fastest feedback kernel: structure, timing, lowest reliable spacing

**Status, 2026-11-04: FeedbackExpt's default loop** (`fastest_loop.py`, `p.fast_path = 2`; user: "build it,
make it default"). `self.p.fast_path = 0` runs the standard loop. Not yet run on the machine (offline: compiled
against the device db, and run on the host against the standard loop event by event; see "As the default" below).
The bench kernels below passed the bench rule at a 26.16 us median spacing (m = 21), against 66.7 us when this
work began. Since 2026-11-05 the default loop picks its spacing from the measured required slack, and runs the
bench's posterior numerics and first-gap stretch, so at m = 21 it runs at the bench's rule-pass spacing plus the
deadline guard: T ~ 26.6 us ("The bench's configuration" and "Spacing" below). Since the 2026-11-05 slack
ladders (on atoms, timing only) it uses the measured entries: m 21 T ~ 26.1, m 31 ~ 31.1, m 51 ~ 44.1 us, lean
posterior. No feedback data has been taken at these spacings.

Files:

| File | What it is |
| --- | --- |
| `fastest_loop.py` | FeedbackExpt's default loop: the guarded kernel's step on FeedbackExpt's own loop, with the library posterior. |
| `bench_fastest_t26.py` | The kernel that passed the rule: run 90958 (class `bench_cg12_t26`, kept as run). Margin records on, no guards. |
| `bench_fastest_t23_guarded.py` | The same with all three guards, at 23.15 us: run 90988, 63 shots clean (class `bench_cg13_g23`). |
| `fastest_timing.py` | Spacing, slack and push padding as functions of grid size: the formula below; `required_slack_mu`, the slack the default loop picks; `MEASURED_SLACK_FLOOR_US`, slack-test results. |
| `slack_ladder_rung.py` | One rung of the slack test ("Slack test" below): copy per rung, set grid size and slack. |
| `../../../../../tests/test_fastest_timing.py` | Checks the formula against the values the runs used. |

Both benches are the H0 bench of the S2 kernel (`feedback_reinit` subclass): no MOT, no field, Raman shutter
closed, imaging light on, real ADC reads. Odd rows replace the read with a synthetic count after the ADC is
read, so the posterior leaves the flat branch; those rows time the non-flat path and mean nothing physically.
They were generated, not hand-written: `make_cf.py` then `make_cg*.py` in the 2026-10-30 night folder
(`C:\lab\skynet_log\outputs\2026-10-30_17-54_night_summary\expts`, local to kong), every replacement asserted.
The wax side, `RamanBeamPair.set_ao_mode` and `prepare_direct_fast_path`, is in wax a3bfd88.

## Lowest reliable spacing

T is the median gap between pulse starts. The kernel sets dT = (slack + 24.216 us + t_pulse) & ~7, so T moves
with the drawn pulse time (1.9 to 3.8 us) and the time after each pulse stays fixed. Median T = slack + 27.06 us
(27.00 to 27.10 across runs).

| Grid m | Lowest clean T, 63 shots (us) | First underflow | Passed the rule (us) |
| --- | --- | --- | --- |
| 21 | 23.15 (90945) | 22 (90946, shot 3) | **26.16** (90958) |
| 11 | 19.2 (90950) | 18 (90951) | not run |
| 5 | 18.1 (90953) | 17 (90954, shot 6) | not run |

The rule (fpab H0, fixed before data): no underflow, no new warning or error in either core log (master and
`artiq_coremgmt -s 1 log`), minimum margin >= 5 us by step type, >= 10,000 counted steps. 90958: 10,710 steps,
0 underflows, minimum margin 5.1 us, no-atom APD level flat at -155.3 +/- 0.24 mV across reads. A second soak at
23.15 us with no margin records (90959) also ran clean for 10,710 steps but measures no margin, and its APD
level sat 1.2 +/- 0.34 mV lower (two runs; cause open).

## Structure of one step

The CPU waits on the read, so the floor is the read return plus the work after it, until the CPU total catches
up near 22 us at m = 21. Order, as built (`bench_fastest_t26.py`, `feedback_loop`):

1. **Frequency word**: one RTIO write of the moving AO's FTW (`hot_write`), single-AO mode, no flag checks.
2. **IO_UPDATE and phase**: the IO_UPDATE event (unless the previous step's trace carried it), then the phase
   accumulator (`hot_update`, the same integers as `io_update_and_phase_update`).
3. **Pulse**: pulse-on (unless carried) and pulse-off.
4. **Records** of this step and the previous one's posterior row, while the read is still in flight.
5. **One DMA playback** at the pulse end: integrator gate, imaging pulse, sample, ADC transfer, the DDS staging
   for the next word, and, when the next step is certainly a plain stage-1 pulse, its IO_UPDATE and pulse-on
   (trace `cf_chain`; otherwise `cf_read`).
6. **propagate_hypotheses**, then the blocking ADC read (16-bit transfer, channel 7 only), then the weigh step.

What was cut to get there, steady margin gained at fixed T (no atoms):

| Change | Gain (us) | Run |
| --- | --- | --- |
| Single-AO frequency moves (larger-centre AO, 1.53x) | about 8 of CPU | 90842 |
| One DMA playback for the read | about 3 of CPU | 90843 |
| Write, IO_UPDATE and staging with no flag bookkeeping | 2.4 | 90898 |
| IO_UPDATE and pulse-on carried in the read trace | 1.6 | 90918 |
| Integrator settle 4 -> 2 us | 2.1 | 90907 |
| ADC transfer 32 -> 16 bits | 1.3 | 90917 |
| Records moved into the read wait | 0.8 | 90933 |
| Std on demand, one ADC channel decoded | 0.3 | 90899 |

Nulls: compiler invariants, inline sin/cos, no pre-issue alone, two records off. Rejected: settle 1 us (no-atom
level -33 mV), gate extra 0.2 us (+5 mV). Not available: RTIO batching (needs ACPKI gateware). Subkernels are
15-18x slower on the satellite with a 204 ms message round trip. One RTIO write costs about 0.5 us to either
crate; the old 5.8 us "phase update" was the IO_UPDATE call, the arithmetic is 0.11 us.

## Guards

| Guard | Cost per step | Run |
| --- | --- | --- |
| Row screen in `prepare()`: refuse rows that can reach the unstaged read branch | none | |
| Stage/write counters: a write needs exactly one stage since the last | not measurable | 90989 |
| Deadline check: RTIO counter vs the word's timestamp, under 1 us lead ends the shot as an underflow | about 0.5 us | 90987 |

`bench_fastest_t26.py` has none of them; `bench_fastest_t23_guarded.py` has all three.

## Larger (or smaller) grids

`fastest_timing.py`:

```
T_floor(m)    = max(18.1, 23.15 - 0.40 (21 - m))   for m <= 21   (measured at m = 5, 11, 21)
              = 23.15 + 0.68 (m - 21)               for m > 21    (UNTESTED; slope from the stamped CPU benches)
T_reliable(m) = T_floor(m) + 3.0 + 0.5 if the deadline guard is on
slack (ns)    = T - 27.06 us, rounded so slack + 24216 is a multiple of 8 (the chained trace asserts it)
push doubles  = 2 m (N + 1) + 7 N + 41  (+ 2 N with margin records), N = N_pulses
```

| m | T_floor (us) | T_reliable with guard (us) | slack (ns) | Push padding |
| --- | --- | --- | --- | --- |
| 5 | 18.1 | 21.6 | -5464 | pad 649 -> 7368 B |
| 11 | 19.15 | 22.65 | -4416 | pad 481 -> 7368 B |
| 21 | 23.15 | 26.65 | -416 | pad 201 -> 7368 B |
| 31 | 29.95 | 33.45 | 6384 | above every tested size |
| 41 | 36.75 | 40.25 | 13184 | above every tested size |

Only m = 21 has a rule pass; m < 21 are measured floors plus the m = 21 gap to the rule; m > 21 is an
extrapolation. Above 7896 B the push needs its own stall test: pick a size with size % 1460 under about 700 B
(the 11-01 stall lead, mechanism unknown) and run it before trusting it.

## As the default (2026-11-04)

`FeedbackExpt.feedback_loop` runs `feedback_loop_fastest` unless `p.fast_path` is set to 0 or the class would
not run as written on it: a class that overrides the read (`measurement`, `readout_*`) or the posterior
(`generate_posterior`, the two halves), scans a param the traces are built from (imaging, integrator, slack,
pretrigger, FIFO and IO_UPDATE timings, `N_pulses`), uses an APD channel other than 7, or scans the
transition frequency over more than 50 kHz gets the standard loop and a printed reason. A class with its own
`feedback_loop` (feedback_reinit, the S2 copies, adaptive Ramsey, FeedbackExptFast) is untouched. `p.fast_path`
records the loop that ran: 2 fastest, 1 overlap (FeedbackExptFast), 0 standard or own loop. The choice is a
host-side function list, so only the loop that runs is compiled.

What differs from the bench kernel: its own records and hooks, and since 2026-11-05 nothing else by default (below).

### The bench's configuration on the default loop (2026-11-05)

User, 2026-11-05: "lengthen only the first gap if it gets rid of the 5us ... can't we run the faster posterior?
port the S2 numerics and fix it to be default if it works fine. +3 for the margin is fine." Two settings, both
recorded in the run file, put the default loop where the bench kernel was when the floors were measured:

- **`p.fastest_posterior = 1` (default): the lean posterior** (`fastest_loop.LeanPosterior`), the bench's numerics: the
  rotation angle's sine table inline, the read fraction inline, the Gaussian without its prefactor
  sigma / sqrt(sigma^2) = 1, one multiply to normalise, the std only when the remesh or the Rabi update uses it.
  The same model as the library's; it differs in rounding only. Kept from the library, which the bench lacked:
  the binomial read, the std and Rabi-rate output, the flat and all-zero branches, `map_frequency`.
  `tests/test_fastest_lean_posterior.py` holds it against the library posterior: one step from 300 random states
  per read model and noise model to ~1e-12; 480 whole trains (reads drawn from a true hypothesis) with no drive
  parting; the remesh decisions identical. Writing those tests found a bug in the bench numerics: a subnormal
  posterior total made the normalisation inf / NaN (1 / total overflows); the lean weigh divides there, as the
  library does. `p.fastest_posterior = 0` runs the library's posterior on the fastest loop. A class that overrides
  `expected_photon_fraction` or `sincos_lut_interp` (inlined by the lean numerics) gets the library's, with a
  printed reason.
- **`p.fastest_first_gap_extra_mu = -1` (auto): the first gap 5 us longer whenever the loop takes the measured
  required slack**; an experiment that keeps its own slack (a calibration, a run pinned to T 66.7 us, a ladder rung
  that does not set it) keeps its timeline, no stretch; a value >= 0 is used as set. The run records the value that
  ran. Replay (`kexp.analysis.feedback`) rebuilds the stretched gap from it (`tests/test_fastest_first_gap.py`:
  the rebuilt `data.t` is the kernel's to the ns). Stretched: step 0 not chained, as every rung ran
  (a non-zero schedule entry was never pre-issued). Step 0's read still starts right after its pulse; step 1's
  IO_UPDATE and pulse-on are the CPU's; every later step chains. Why: the first post-read step of a shot has
  ~4.4 us less margin than every later one, at any spacing (90871, T 66.7: 33.7 vs 38.2 us; 90873, T 42, uniform
  gaps, the same code path every step: 9.3 vs 13.7 us). It is a fixed one-time cost, not a timing effect. The
  cause is not shown; the likely one is a cold first pass through the post-read code and data (caches) after the
  shot's long sequence. A warm-up pass before `t_start` might remove it; untested.
  `tests/test_fastest_first_gap.py`: step 0 the same event for event, every later event exactly 5 us later, the
  phase handed to the posterior moved by the drive's phase over 5 us, no sequence error.

A run that keeps its own slack (`fastest_slack_auto = 0` or its own `t_calculation_slack_compensation_mu`) keeps its RTIO schedule (no stretch, the same chain and gaps) but NOT its posterior arithmetic: the lean posterior is the default for it too, equal to the library's to rounding. A copy that must match earlier library-posterior runs bit for bit sets `p.fastest_posterior = 0`. (Reviewer, organizer 11-05, 2026-11-05.)

The 11-01 posterior-time numbers (propagate 10.7, weigh 6.1 us at m 21, 90809) were the library halves on the
overlap loop; the bench floors below were measured with the lean numerics.

### Spacing: the measured required slack (default since 2026-11-05)

User, 2026-11-05: "the fastest loop feedback should pick the wait time from the measured required slack. make
this the default behavior." When the fastest loop runs, `fastest_pick_slack` sets
`p.t_calculation_slack_compensation_mu = fastest_timing.required_slack_mu(p)`:

```
slack = slack_for(T_reliable(m), deadline guard on)   the rule pass at m 21 (90958: floor 23.15 + 3.0 us), + .5 us
                                                       guard; elsewhere the floor + 3.5 us
      + max(0, 5 us - p.fastest_first_gap_extra_mu)    a shorter first-gap stretch than the bench's, on every gap
      + 6.1 us x max(1, m / 21)  if p.fastest_posterior = 0   the library posterior's whole stamped weigh (90809):
                                                       an upper bound on its post-read time over the bench's
      + any longer read than the bench's               settle > 2 us, gate delay > .7, gate extra > 1, FIFO < 18.416
      rounded up so slack + pretrigger + imaging + FIFO is on the 8 ns grid
```

At the defaults (lean, +5 us):

| m | slack (us) | median T (us) |
| --- | --- | --- |
| 5 | -5.464 | ~21.6 |
| 11 | -4.416 | ~22.6 |
| 21 | -1.000 | ~26.1 (slack ladder 2026-11-05, L -4 us + 3.0; was -0.416, ~26.6, bench-derived; 11-05 first version: 10.69 slack, ~37.8 T; the standard loop: 39.70, ~66.7) |
| 31 | 4.000 | ~31.1 (slack ladder 2026-11-05, L 1 us + 3.0) |
| 51 | 17.000 | ~44.1 (slack ladder 2026-11-05, L 14 us + 3.0; 13 us failed at shot 12 of 100) |
| other m > 21 | refused until the slack test below has an entry for that m and posterior | |

With the library posterior, m 21: 5.688 us, T ~ 32.7 us (bench-derived; no library entry). m 31/51 with the library
posterior: refused (the lean entries do not stand for it; its 2026-11-05 ladders, 20 shots only, were clean only down
to -2 us at m 21 and 17 us at m 51). With no first-gap stretch, m 21: 4.000 us, T ~ 31.1 us.

Slack test record, 2026-11-05 (organizer night; runs, rungs and caveats: night folder
`2026-11-05_17-46_night_summary`, AMENDMENTS A18-A29, and `2026-11-05_20-25_slack_ladder/MANIFEST.md`):
L (lowest rung clean in 100 shots) lean m 21 -4, m 31 1, m 51 14 us; library m 21 -2 and m 51 17 us (20 shots only).
Lean = library numerics (replay check R4) at m 21/31/51, N 11, adaptive drive, tonight's contrast only; on the
hardware they differ by ~1e-5 (1e-12 on the host), cause untested (guess: FTW / phase quantisation). The +3.0 us
margin was measured only at m 21; untested at m 31 and 51. Both core logs clean in the ladder windows (satellite ring
from 21:37 only). Cost per grid point 0.50 us (m 21 -> 31), 0.65 us (31 -> 51); one line fits poorly.

An experiment that sets `t_calculation_slack_compensation_mu` itself (any value other than the params default it
was built with) or `p.fastest_slack_auto = 0` keeps its slack. `p.fastest_slack_auto` records whether the measured
slack was applied (1) or not (0); `p.t_calculation_slack_compensation_mu` and `p.t_between_pulses_mu` the spacing
that ran (the first gap is `p.t_between_pulses_mu` + `p.fastest_first_gap_extra_mu` for the median pulse). The
standard loop's slack is unchanged; it records `fastest_posterior = 0` and `fastest_first_gap_extra_mu = 0`. The
run's terminal prints the slack and where it comes from.

What is not measured: the default loop at this spacing (no bench of it, no atoms). It now runs the bench's
numerics and gap schedule, but not the bench's whole step (its own records and hooks, `maybe_remesh`'s call), so
the slack test at m 21 is the check. The deadline guard ends a shot with a late word as an RTIOUnderflow, and an
underflow is followed by AUX_DAC failures on the next run (memory: underflow aftereffects). The read model, the
APD levels and the contrast were all calibrated at T ~ 66.7 us; at ~26.6 us the integrator clear and the read
history differ. A remesh (off by default) costs three passes over the grid on the step it fires; it was never
timed at these spacings.

### How the slack is determined (look-up order in `required_slack_mu`)

1. The experiment set `t_calculation_slack_compensation_mu` itself, or `p.fastest_slack_auto = 0`: that slack.
2. The grid size m and the run's posterior have an entry in `fastest_timing.MEASURED_SLACK_FLOOR_US` (a slack test
   on the default loop, below; keyed `(m, "lean")` or `(m, "library")`, with the stretch the ladder ran): the
   measured floor + 3.0 us + any first-gap shortfall against the ladder's + any longer read.
3. m <= 21 without one: the bench-derived value above.
4. m > 21 without one: **refused** before a run id (`SlackUntested`, user 2026-11-05: a larger grid "needs to
   test it for slack first"). The bench measured m 5, 11 and 21 only; above 21 its slope is a guess.

### Slack test (any grid size; required before the default loop runs m > 21)

What it measures: the lowest slack at which the default loop (the fastest loop as built: single-AO moves, one
DMA read playback, the posterior split around the ADC read, the deadline guard) runs every step on time, at one
grid size, on atoms, with the feedback read settings. One rung = one run at one fixed slack. It is a timing
test: no rung's data is feedback data.

Method (fixed 2026-11-05, before any ladder ran):

1. **Rung file**: copy `slack_ladder_rung.py` into the night's run folder once per rung and set `GRID_SIZE`,
   `SLACK_US`, `N_SHOTS` (20 per rung, 3 warm-ups). It runs the default loop on atoms with adaptive drive and
   keeps its slack as set. Read settings stay the `ExptParamsFeedback` defaults (settle 2 us, gate .7 / 1.0 us,
   FIFO 18.416 us); a ladder at other read settings is a different measurement.
2. **Start** at `fastest_timing.ladder_start_us(p, m)` (the bench estimate for the run's posterior and first-gap
   stretch, rounded up to a whole us; at the defaults m 31 gives 7 us, m 21 gives 0 us). Step **down 1 us** per rung until the first rung that underflows. If the first rung underflows,
   step **up 2 us** until one is clean, then down 1 us again.
3. **Clean rung** = the log shows `feedback: fastest loop` and `slack ... us as set`, no `RTIOUnderflow` line,
   and every planned shot stored, counted from `data/t` (> 0 at every step), never from `data/apd`, whose fill
   value 0 is finite. The "complete, N shots" line is the planned count, not proof (90946). Neither is
   "shot n/N done": an underflowed shot is cleaned up like any other (its partial record is stored, then the
   shot-complete notice prints that line; 92625). A deadline-guard trip is an underflow.
4. **Underflows are expected and fine; continue.** The run after an underflow usually fails at init with
   `ValueError: Urukul AD9910 AUX_DAC mismatch` (3 of 3 on 11-01; the run after that worked every time). User,
   2026-11-05: fine to underflow and continue through it. A rung that failed that way took no shots:
   submit it again and go on. Any other error stops the ladder and goes to the organizer.
5. **Floor** = the lowest clean rung whose next rung down underflowed. **Confirm** it with one run of 100
   shots at the floor. Clean: the floor stands. Underflow: floor + 1 us, confirm again.
6. **Core logs** after the ladder, read-only: master and `artiq_coremgmt -s 1 log` (a late word at the
   satellite is silent). A sequence error or new warning during a rung makes that rung not clean.
7. **Afterwards**: check that the TOF loop is not latched (an AUX_DAC failure latches it, 11-01) and restart it.
8. **Record**: add `(m, "lean"): (floor_us, "ladder runs A-B, confirm C, YYYY-MM-DD", 5000)` (the posterior
   and the `fastest_first_gap_extra_mu` the ladder ran with) to `MEASURED_SLACK_FLOOR_US` in `fastest_timing.py`,
   add a test, and put every rung (run id, slack, clean or not) in the night's run table. The default loop then
   uses floor + 3.0 us at that m and posterior (`RELIABLE_OVER_FLOOR_US`: the bench's gap from the m 21
   floor, 23.15 us, to its rule pass, 26.16 us).

Cost: about 23 shots a rung on atoms (~2 min at ~5 s a shot), 5-10 rungs plus the confirmation run.

Offline (tests/test_fastest_default.py, test_fastest_rtio_stream.py, test_fastest_first_gap.py,
test_fastest_lean_posterior.py): compiles with either posterior; against the standard loop at the same slack
(39.7, 20, 3.9 us) and no first-gap stretch, with either posterior and the same reads, every Raman switch at the same timestamp; every read
event shifted by one constant 0-15 ns (the read starts on the 8 ns grid after the pulse end); the moving AO's
IO_UPDATE where the standard loop pulses it; the same decoded reads; the phase each loop hands the posterior
within the frequency word's LSB and the tracker's quantisation, and identical on the anchor; the posterior to
2e-4. In 1 of 24 adaptive trains a posterior near-tie (top two points within 0.07 %) broke the other way at
step 8: the 1-LSB single-AO word is enough to do that. No sequence error predicted by the lane model.

## Before trusting it on atoms

Done for the default loop:

- `imaging.off()` and `raman.off()` in `FeedbackExpt.cleanup_abort_kernel` (after Base's safe state).
- The deadline guard (always on in the default loop; < 1 us of lead ends the shot as an RTIOUnderflow).
- The 32-bit ADC transfer restored at the end of the loop and in both cleanups.
- The posterior numerics: the lean ones since 2026-11-05, held against the library's on the host
  (test_fastest_lean_posterior.py, and through the RTIO stream). Owed on hardware: a replay of a real fastest-loop
  run through the library posterior (the compiled kernel rounds under fast-math). `s_z` kept.
- The 10,000-step soak: dropped (user, 2026-11-04: "do not do the crazy soak thing").

Not done:

- The first run on the machine (CPU time, the compiled kernel's rounding and the satellite are out of reach
  offline), and the destination-1 core log read after it (`artiq_coremgmt -s 1 log`): a late word at the
  satellite is silent.
- Single-AO t_pi at the reference and +/- 50 kHz (the drive moves within the grid, about +/- 10 kHz).
- The first run at the measured required slack (T ~ 37.8 us at m 21): watch for the deadline guard's
  RTIOUnderflow and read both core logs after it.
- Settle 2 us with atoms; the read model, contrast, APD levels and grid recalibrated at the new T (all were
  measured at T = 66 us). The default T moved on 2026-11-05, so this is owed before trusting default feedback data.

Record: `TIMING_LOG.md` in the night folder, page https://claude.ai/artifact/Sv8ja2XNmgYNQWpT8UMJvi.
