# Plan: test a non-commensurate inter-pulse schedule on the machine

Written 2026-10-07 16:1x, session 2026-10-07_13-38_1. Background: `REPORT.md` in this folder
(measured comb at n/T in every feedback run; synthetic schedule, order-sweep and cycle tests).
Nothing in this plan has been run. No repository file changes; everything is a session copy.

## 0. Decision from the synthetic tests

- **Three gaps do not break the comb more.** The 1/T_mean tooth is killed when the pulse-start
  deviations from i·T_mean are maximally scattered; a two-gap alternation does that (every other
  pulse off by the same amount). An equal-increment three-gap cycle puts two of every three pulses
  at the same deviation and the first alias comes back (0.63 of resonance vs 0.11 for two gaps).
  Unequal three-gap cycles remove the first alias but move the mass to other secondary peaks
  (0.66–0.75) and score no better on localization. Table: `REPORT.md`, Addendum 2 / fig 12.
- **Candidate: ALT2 = fast gap / standard gap alternation**, 46.9 / 66.6 µs at today's pulse times
  (extra delay list [0, 20 µs] repeated over the fast-path gap). Mean 56.9 µs, so it costs no time
  against the standard path. Model predictions at the stored noise: first alias 0.98 → 0.11,
  fine-grid MAP within ±0.04 Ω 0.07 → 0.16, mass within ±0.04 Ω 0.043 → 0.066, production 21-pt hit
  unchanged (0.415 vs 0.404), a residual weaker comb at 1/(T_f + T_s) = 8.8 kHz.
- **Arms:** ALT2 (new), FBF (fast path, as 85351) and FB (standard, as 85352) as controls, run by run.
  The adaptive loop only; the non-adaptive form can follow if ALT2 works. An ALT3-φ arm is not
  worth machine time on these numbers.

## 1. What gets built (session copies in `outputs\2026-10-07_11-35_feedback_procedure\expts\`, repo untouched)

1. `base_expt_feedback_alt.py`: `FeedbackExptAlt(FeedbackExptFast)` — the 10-06 fast-path session
   copy (verified 85204, 85213–85243) with two changes in `feedback_loop`:
   - after the per-pulse gap is computed: `dT_i += self.p.t_gap_extra_list_mu[i]` (int64 array of
     length N_pulses, 8 ns aligned; default all zeros = today's behaviour). `t_step`, the pre-issued
     next read, and `io_update_and_phase_update` already take the actual `dT`, and the time handed to
     the posterior is `t_step - t_start_mu`, so the kernel model stays exact. `generate_posterior` and
     `OverlapPosterior` are not touched.
   - record the gap: `self.data.dT_mu.put_data(float(dT_i), i)`, container `dT_mu` of length
     N_pulses added next to `t_raman_pulse` in `finish_prepare`.
   - params: `t_gap_extra_list_mu` (array) built in `finish_prepare` from `t_gap_cycle_extra_us`
     (list, default [0]); recorded in the run file like every other param.
2. Run files: `feedback_alt2.py` = `feedback_fast_fast.py` with `t_gap_cycle_extra_us = [0, 20]`;
   same xvar (`feedback_fractional_initial_offset` linspace(−2.5, 2.5, 21)), N_repeats 5, 3 warm-ups,
   slack 20 µs, `end(..., restart_monitor=False)`. The parked `# self.xvar(... linspace(0,4.,5))`
   line stays as it is.
3. Analysis: `FeedbackReplayGaps(FeedbackReplay)` in `alias_replay_gaps.py`, overriding
   `_compute_dT_rr_mu` to return `ad.data.dT_mu` when the container exists (reconstruction as now
   otherwise). Without this the stock replay passes its validation (which only checks the nominal
   pulse) and replays ALT2 runs on the wrong timeline. `replay_check.py`, `alias_replay.py`,
   `alias_folded.py` get a one-line switch to the subclass.
4. `alt2_analyse.py`: the pre-registered metrics of §5, written and dry-run on 85351/85352 before any
   ALT2 data exist.

## 2. Offline checks before hardware

- `py_compile` of the new files; `artiq_compile --device-db %db% feedback_alt2.py` (kernel only).
- Host check: the gap list `finish_prepare` builds is [0, 20000, 0, 20000, …] ns and 8-aligned;
  `t_between_pulses_mu` (the pre-loop gap) unchanged.
- The fast-path equivalence test (`test_overlap_equivalence.py`) is unaffected: the posterior code
  is unchanged. The timing is checked on hardware (§4).

## 3. Pre-run audit (run-experiment §2), to be re-read against the built file

- **Hardware:** identical to `feedback_fast_fast.py`: Raman DDS pair with fast frequency update and
  the Raman shutter; imaging DDS/AOM at `amp_imaging`; SLM phase mask written every shot; PDXC APD
  stage **in** via `camera_select=cameras.apd` (the sanctioned route, lab-rules §2 exception);
  HF tweezers via `prepare_hf_tweezers(squeeze=False)`; integrator/sampler reads; Siglent scope
  armed; `pd_scope_trig3` TTL; absorption image after TOF. No Precilaser/ALS setpoint, no stage or
  picomotor, no coil current beyond the standard sequence. Nothing new is touched.
- **xvar:** `feedback_fractional_initial_offset`, −2.5 … 2.5 Ω, 21 points × 5 repeats = 105 shots
  + 3 warm-ups; ≈ 637 s per run (as 85351/85352).
- **Overrides in file:** `update_raman_frequency_bool 1`, `include_photon_noise 1`, slack 20 000 mu,
  `N_warmup_shots 3`, `t_gap_cycle_extra_us [0, 20]`.
- **Tier:** no-camera APD run with liveOD (`save_data=True`); the scalar feed is not available, the
  watcher runs liveness-only; `ar` stdout carries the aprints.
- **End state:** normal completion — `cleanup_scan_kernel` (Raman shutter off, `reset_coils`,
  lightsheet off) plus the file's own `tweezer.off`, `clean_up_fast_frequency_update`, Raman shutter
  off; caught `RTIOUnderflow` — the same path; any other exception — **no cleanup**, same as every
  feedback run since 2026-09-28. The change adds only dead time inside the loop (≤ 16 × 20 µs =
  0.32 ms more tweezer hold); it removes no cleanup and adds no new hazard.

## 4. Run-only test first (`/test-experiment`, parameter files fenced)

`feedback_alt2.py` with N_repeats 1 and 5 offsets (5 shots + 3 warm-ups, ≈ 1 min), through the run
lock. Pass criteria, all required:
- `ar` exit 0, no underflow, `run_log.py` outcome `saved`, 8/8 shots.
- `data.dT_mu` alternates within 46.1–48.0 µs and 66.1–68.0 µs (recorded pulse-time jitter kept);
  `data.t` equals the cumulative sum of the recorded gaps plus pulse and imaging times.
- Gap-aware replay vs `data.probabilities`: max |ΔP| < 1e-3 and MAP agreement 8/8 (85204's fast
  test gave 6e-5; today's runs 3e-4). A failure here means the kernel timeline and the recorded gaps
  disagree: stop, no data runs.

## 5. Data protocol

- Cycle **ALT2 → FBF → FB**, 105 shots each, same constants for all arms. The hourly APD recal
  (procedure step 8: 3-point × 10, `--sz-source params --degree 1`) applies to all arms alike and is
  logged with its values; no other parameter changes during the sequence. Minimum **4 cycles**
  (≈ 36 min per cycle incl. recal, ≈ 2.5 h), through `fb_driver.py` with a new ALT2 stage, run lock,
  `restart_monitor=False`, TOF loop at the end.
- Preconditions: a calibration not older than the procedure allows (t_π #85342 = 3.787 µs stands
  only if the Raman lock is unchanged; session 13-34 ran a joint calibration 85383 at imaging amp
  0.12 — the active constants and `amp_imaging` must be checked and must be the same for all three
  arms); pre-shot contrast gate 25 mV as in the procedure; the start-of-run contrast dip found on
  85376 (first ~20 shots low) hits every arm equally under run-by-run alternation and is noted, not
  corrected.
- Stop rules: run-experiment §5 (zero signal, 2-min stall, any traceback); contrast fallback per the
  procedure when a recal fails sanity.

## 6. Pre-registered analysis (scripts in this folder, gap-aware replay; every shot counted)

- **P1 — is the comb gone? (per run)** Fold the 801-point final posterior modulo 1/T at the fast
  period (46.9 µs) and at the standard period (66.6 µs), resonance tooth excluded. Measured so far:
  peak/mean 1.58–1.80 in all four baseline runs, 0.88–0.92 for a wrong period. Prediction: FBF and
  FB ≥ 1.4 at their own period; **ALT2 < 1.2 at both**, and a new peak at 1/(T_f + T_s) = 8.8 kHz
  (report its height; the model gives the largest secondary peak 0.76 of resonance there).
- **P2 — does it localize better?** Fine MAP within ±0.04 Ω (±5.3 kHz) and mass within ±0.04 Ω,
  per run; paired per-cycle differences ALT2 − FB and ALT2 − FBF with their SEM. Prediction
  +0.09 ± 0.045 per pair on the MAP fraction; **useful if > 3σ over ≥ 4 cycles** in the predicted
  direction.
- **P3 — production hit**, with each run's q = 0.25·f_Rabi·T (ALT2 has two). Prediction: no change
  beyond ±0.05. Reported either way.
- **P4** — wrong-bin pattern (±1, ±2 bins) and the per-run alias-order table, as in `results_folded.json`.
- Report the result as it comes out: P1 false means the comb is not set by the pulse-start times as
  modelled, which would itself be the finding.

## 7. Timeline and occupancy

- Build + offline checks: ≈ 1 h, can start now, touches no hardware.
- Machine: held by session 2026-10-07_13-34 until ≈ 16:35; session 2026-10-07_09-37 has the
  interleaved contrast test (≈ 1.5 h) queued behind it, as the user requested. Earliest ALT2 run-only
  test ≈ 18:00 unless the user reorders; 4 data cycles ≈ 2.5 h after that.
- Every launch through `run_lock.py run`, `--after-run` from the handing-over session; occupancy
  re-checked at each launch.

## 8. Deliverables and what is not done

- `REPORT.md` Addendum 3 with the P1–P4 tables and figures; session log entries per run.
- No calibration write-backs. If P1 and P2 hold, a proposal (not an edit) for the repository port:
  `t_gap_extra_list_mu` + `dT_mu` container in `base_expt_feedback.py` / `data_vault_feedback.py`,
  the `_compute_dT_rr_mu` change in `kexp/analysis/feedback.py`, and the AGENTS/wiki notes.

---

## Status 2026-10-07 18:18 — §1–§4 done

- §1 built in `expts/` of this folder (`base_expt_feedback_alt.py`, `feedback_alt2_test.py`; `alias_replay_gaps.py`,
  `alt2_test_check.py`). One build fix: array params must be **float** arrays — `waxx.Scanner.generate_assignment_kernels`
  emits a kernel setter `self.params.<key> = value` with a float-array value for every ndarray param, so an int64 array
  does not compile (run 85396 consumed by that compile failure, no data). The extra-gap list is a float array of ns, cast
  with `np.int64()` in the kernel.
- §4 run-only test **PASS** on run 85397 (5 shots + 3 warm-ups, no underflow): even gaps 46.14–47.63 µs, odd gaps
  66.27–67.80 µs; `data.t` consistent with the recorded gaps to 1e-10 ns; gap-aware replay vs the kernel posterior
  max |ΔP| 8.4e-5 with 5/5 MAPs agreeing. The stock replay on the same run: max |ΔP| 0.29, 3/5 — it must not be used on
  alternating-gap runs.
- §5 data runs: not started; awaiting the user's go. Preconditions to check first: active t_π / LS / APD constants and
  `amp_imaging` identical for all arms (session 13:34 ran a joint calibration at amp 0.12 — verify what is active).
