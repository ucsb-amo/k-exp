# Fastest feedback kernel: structure, timing, lowest reliable spacing

**Status, 2026-11-04: FeedbackExpt's default loop** (`fastest_loop.py`, `p.fast_path = 2`; user: "build it,
make it default"). `self.p.fast_path = 0` runs the standard loop. Not yet run on the machine (offline: compiled
against the device db, and run on the host against the standard loop event by event; see "As the default" below).
The bench kernels below passed the bench rule at a 26.16 us median spacing (m = 21), against 66.7 us when this
work began; the default keeps the spacing (slack) and the integrator settle as they were.

Files:

| File | What it is |
| --- | --- |
| `fastest_loop.py` | FeedbackExpt's default loop: the guarded kernel's step on FeedbackExpt's own loop, with the library posterior. |
| `bench_fastest_t26.py` | The kernel that passed the rule: run 90958 (class `bench_cg12_t26`, kept as run). Margin records on, no guards. |
| `bench_fastest_t23_guarded.py` | The same with all three guards, at 23.15 us: run 90988, 63 shots clean (class `bench_cg13_g23`). |
| `fastest_timing.py` | Spacing, slack and push padding as functions of grid size: the formula below. |
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

What differs from the bench kernel, on purpose: the posterior is the library's (`OverlapPosterior`, bit for bit
`Feedback.generate_posterior` on the host), not the S2 kernel's faster numerics, so the replay and the
analysis see the posterior they always did; the slack default (T ~ 66.7 us at m = 21) and the integrator settle
default are unchanged. The bench floors were measured with the S2 numerics: re-measure before lowering T.

Offline (tests/test_fastest_default.py, test_fastest_rtio_stream.py): compiles; against the standard loop at
the same slack (39.7, 20, 3.9 us), with the same reads, every Raman switch at the same timestamp; every read
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
- The posterior numerics: unchanged (library posterior), so no replay of new numerics is owed; `s_z` kept.
- The 10,000-step soak: dropped (user, 2026-11-04: "do not do the crazy soak thing").

Not done:

- The first run on the machine (CPU time, the compiled kernel's rounding and the satellite are out of reach
  offline), and the destination-1 core log read after it (`artiq_coremgmt -s 1 log`): a late word at the
  satellite is silent.
- Single-AO t_pi at the reference and +/- 50 kHz (the drive moves within the grid, about +/- 10 kHz).
- Only when lowering T: settle 2 us with atoms; the read model, contrast and grid recalibrated at the new T
  (all were measured at T = 66 us).

Record: `TIMING_LOG.md` in the night folder, page https://claude.ai/artifact/Sv8ja2XNmgYNQWpT8UMJvi.
