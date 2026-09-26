# OPX+ integration — assessment, handoff timing, and waste findings

Date: 2026-09-24. Scope: `k-exp/kexp/control/opx/` (our framework), the
ARTIQ handshake in `k-exp/kexp/base/control.py`, the scripts Quantum Machines
wrote in `customer-weld-ucsb/`, and QUAM (https://qua-platform.github.io/quam/).
Evidence lives in the phase-1 reports (ours_audit, artiq_handshake,
customer_handoff, feedback_spec, qua_capabilities, quam_docs, data_plumbing).
Nothing in this document was validated on hardware; every timing number is
either read off the code (marked *code*) or inferred (marked *inferred*).
Confidence labels: **confirmed** = read in code or an official document by at
least two independent readers; **inferred** = a reading of the code/docs
without a measurement; **unverified** = the automated cross-check was cut
short (session limit) and only one reader supports it.

## 1. Headline findings

1. **The framework could not start a run (confirmed, fixed in the rebuild).**
   `kexp_channel_map` read `ExptParams.t_opx_handoff_settle`, which commits
   `b77c728c`/`9f7daec1` (2026-09-24) replaced with `t_opx_handoff_artiq_side =
   350 ns` and `t_opx_handoff_opx_side = 1 µs`. `self.opx.use()` therefore
   raised `AttributeError` inside `prepare()`; the 39 offline tests passed only
   because every fixture fabricated the old attribute on a stand-in. The rebuild
   makes the OPX settle wait the sum of the two ARTIQ-side parameters and adds a
   test that builds the map from the real `ExptParams()`.
2. **The block-before-RF ordering is an unmeasured assumption (confirmed as
   unmeasured).** ARTIQ now turns its steady-state RF on 350 ns after the
   trigger. The OPX must have raised both RF blocks (trigger latency + 16 ns
   play + switch turn-off) before that. QM publishes no trigger latency; the
   repo's own comments put the OPX at "~1 µs" and the switch turn-off at
   "~1 µs". If either number is right, ARTIQ raman **and** imaging RF reach the
   switch AOMs for up to ~0.7 µs at the start of every OPX window. Milestone M1
   (scope trigger → block) decides this; until then the previous design (RF at
   5 µs) was safe by construction and this one is not.
3. **Two documentation errors about the handshake (confirmed).** (a) "RF goes off
   before the handoff TTL drops": the three take-back events carry the same
   timestamp. (b) "A crash mid-window leaves the OPX blocks HIGH": the emitted
   program fires the hand-back, holds the blocks for the overlap and releases
   them whatever ARTIQ does; the real crash end state is ARTIQ RF ON on both
   switch AOMs and the handoff TTL HIGH until the next run's `init_kernel`.
   Both are rewritten in the rebuild, and `cleanup_scan_kernel` now switches
   the RF off.
4. **Hand-back CPU slot is tighter than the code's own guidance (inferred).**
   `TTL_IN.wait_for_edge` says "keep t_delay >= 10 µs"; it is called with
   `overlap/2 = 7.5 µs`. The two in-repo estimates of the kernel's per-event
   cost differ by 4×. The VERBOSE slack print in
   `wait_for_quantum_machines_handback` is the measurement and has never been
   run.
5. **QUAM: borrow the shapes, not the package (decision).** See §2.

## 2. QUAM assessment

QUAM (v0.6.0 on `main`) is a tree of `@quam_dataclass` components rooted in a
`QuamRoot`; every component writes its slice of the QUA config in
`apply_to_config`, channels wrap `play/measure/wait/align/update_frequency/
frame_rotation_2pi/reset_if_phase` with the element name filled in, a
`StickyChannelAddon` emits exactly our sticky dict, `Pulse` objects derive
config names as `<element>.<label>.pulse|wf|dm|iw`, references (`#/...`,
`#./...`) share one number between components, `to_dict()/load()` round-trip
the whole tree through JSON with `__class__` and package versions, and macros
live on components (`QuantumComponent.macros`, `@register_macro`).

What it does better than our string-keyed `ChannelSpec` + hand-written config
dict, and what the rebuild borrows:

| borrowed | why |
|---|---|
| elements as objects that generate their own config (`components.py`: `DigitalLine`, `AnalogDrive`, `IntegratedInput`, `Machine.generate_config`) | the element name and the op names no longer have to agree in three places; a typo surfaces at build time |
| QUAM's `<element>.<label>.pulse/.wf/.dm/.iw` naming for pulses/waveforms/weights | no collisions when a second acquire length or Raman tone is added |
| a declared `Sticky` field instead of a comment | the QOP's "analog: True even on digital-only sticky" rule becomes a checked value |
| `Machine.to_dict()` saved into the run file (`opx_machine`) next to the QUA text, with the qm-qua version | the run's OPX wiring (ports, polarities, IFs, amplitudes, windows) is reproducible from the file alone |
| composite components carrying their own macros (RamanPair / ImagingBeam / handshake) | new beams are new components, not new role strings plus new ctx methods |

What we keep that QUAM has no notion of: per-shot parameter binding to the
ARTIQ scan (`build_shot_tables` sweeping the real `compute_derived` per shot;
`ParamRef` columns that refuse to collapse to one number), builder-owned
handshake framing, SI units at the API with grid/range checks, trace-time
validation (claims, save counts, nothing after hand-back, live-Adjust
refusal), the op-log provenance behind the pulse viewer, and qm-free imports.

Why not the package: QUAM imports `qm` at module import (we deliberately do
not), its `InSingleChannel.measure` always emits `demod.full` (our APD path is
`integration.full`), its references resolve once at trace time and cannot
express a per-shot value, `Channel.wait/align` mis-handle channel objects, it
needs `typeguard` + `qualibrate-config`, and v0.5/v0.6 are mid-refactor
(channel ports and all shaped pulses deprecated). Python (3.13) and qm-qua
(1.4.1) would be compatible, so the door stays open: our components keep
QUAM's shapes so a later switch is mechanical.

## 3. How the handoff works, as coded

Wires: ARTIQ ttl32 → OPX trigger in; OPX digital 3 → ARTIQ ttl41 (hand-back,
rising-edge gate armed before the trigger); ARTIQ ttl33 routes the raman 80/150
AOs to the OPX analog outputs while high. OPX digital 1/2 drive RF switches in
ARTIQ's RF path to the raman/imaging **switch** AOMs: HIGH = blocked, LOW =
passes; the lines idle LOW with no job.

### 3.1 The customer 00-series (what was run with atoms on 2026-09-23/24)

`00d` (single shot) and `00e` (30-shot `for_each_`) do, per shot:
`wait_for_trigger("raman_gate")` → `align()` → latch the sticky drives
(`play("cw")` 16 ns, held) → `BEAM_OFF` on both gates (digital HIGH, held) →
`wait(t_artiq_handoff − 4 cc)` (10 µs in 00d, 1 µs in 00e) → exposure by
`ramp_to_zero("raman_gate")` (line LOW at ramp start) + `wait(t)` + `BEAM_OFF`
→ `align(gates, handoff)` → `play("trigger", duration=10 or 15 µs)` → (00e
only) `ramp_to_zero` on the drives and both gates. Timeline table with every
statement: customer_handoff.md §1.2–1.4. Points established there:

- The exposure is `t + 4 ns` (the sticky ramp precedes the wait; *inferred* from
  the docs' "digital marker stops at the beginning of the ramp"), and `t` was
  floored to the 4 ns grid.
- The 15 µs hand-back "trigger" play is used as a timer for the block hold; the
  OPX does nothing during it. ARTIQ takes its RF back at overlap/2, so 7.5 µs
  (now) / 10 µs (then) of it is idle margin.
- **00e-era mismatch (inferred).** Against the ARTIQ code live at the time
  (`063c3b07`/`612698b9`: RF on at settle/2 = 5 µs), 00e opened the raman gate at
  ~1 µs, i.e. the first ~4 µs of every 00e exposure had no ARTIQ RF, and the four
  shortest non-zero settings had no light at all. Which `control.py` was loaded
  for the 00e data is not recorded; treat 00e's Rabi data accordingly.
- **00g accumulates the sticky latch (inferred from the sticky docs).** It
  re-plays `cw` every shot without the trailing `ramp_to_zero` of 00e, so the
  held drive amplitude doubles on shot 2 (raman_B 0.65 V > 0.5 V full scale)
  and the blocks are never released between shots.
- The 01–05 templates play `BEAM_OFF` **as** the Raman pulse: inverted against
  the truth table (the atoms are exposed the whole window except during the
  intended pulse), never block imaging, never hand back. They were written
  before the switch-box polarity was known and were never reworked.

### 3.2 The framework (builder) program, after the rebuild

```
                 ARTIQ (1 ns mu)                                   OPX+ (4 ns cc)
 t0              arm ttl41 gate; ttl32 HIGH (1 us pulse) ------->  wait_for_trigger('raman_switch') returns after L_trig (unpublished)
 t0 + L + a                                                         align; play 'block' on raman_switch, imaging_switch (16 ns, sticky HIGH)
 t0 + 350 ns     ttl33 HIGH; imaging sw ON; raman sw ON            |  (ASSUMPTION: blocks complete before this)
 t0 + 1.35 us    kernel returns; CPU blocks in wait_for_edge        wait(settle = 1.35 us) on both switches; align; <body>
 Te              <-------- 200 ns hand-back on digital 3 --------  align; play 'trigger'; wait(overlap = 15 us) on the switches
 Te + 7.5 us     imaging sw OFF, raman sw OFF, ttl33 LOW (3 events; ~4-7 us of CPU reaction needed, unmeasured)
 Te + 15 us      off() bookkeeping                                  play 'pass' on both switches (LOW); loop
```

Dead time per OPX window on the ARTIQ timeline: 1.35 µs + 15 µs. The 15 µs
overlap could shrink to ~8–10 µs once the VERBOSE slack print has been read;
a self-timed release (ARTIQ pulses ttl32 again after its RF-off events and the
OPX waits for it before `pass`) would remove the guessed margin entirely
(artiq_handshake.md §3.2, design B; not implemented — hardware change).

### 3.3 Waste and risk table (per OPX window unless stated)

| # | item | time | status |
|---|---|---|---|
| W1 | hand-back overlap 15 µs vs ~8.5–10 µs need | ~5 µs | inferred |
| W2 | 00d/00e: 10 µs settle vs 1.35 µs needed now; builder: crash (fixed) | 8.6 µs | confirmed |
| W3 | redundant `imaging.off()`/`raman.off()` re-writes at overlap end | ~1–2 µs CPU | confirmed (no DAC on these DDSs) |
| W4 | `T_OPX_HANDBACK_TIMEOUT = 2 s`: with a dead job every shot burns 2 s **with both switch-AOM RFs on and the OPX lines idle low** | 2 s per failing shot | confirmed |
| W5 | redundant global aligns in the framing (one removed in the rebuild) | ns | confirmed |
| W6 | ARTIQ turns RF on for both beams every window regardless of `claims` | risk | confirmed |
| W7 | intensity servo during the block: depends on where its photodiode sits | unknown | open |
| W8 | `prep_raman` 10.7–28 ms per shot: necessary (switch-AOM warm-up, shutter, line trigger) | ms | confirmed |
| R1 | handoff leak risk (trigger→block vs 350 ns) | ≤ 1 µs light on both beams | unverified |
| R2 | take-back CPU margin 0.5–3.5 µs | — | inferred |
| R3 | underflow in the take-back left RF on (fixed: cleanup switches RF off) | — | confirmed |
| R4 | crash mid-run left ttl33 HIGH into the next run (fixed: init drops it) | one shot | confirmed |
| R6 | 00d: sticky release at program end vs the 10 µs trigger play — ambiguous | possibly 7.5 µs of light | inferred |

### 3.4 Pulse-logic triple check (summary)

Polarity of every op vs the truth table: consistent in the builder and in the
00-series; inverted in 01–05. Hand-back edge cannot be missed (gate armed at
the cursor before the trigger; verified in code). Zero-length exposures are
guarded. Sticky replays of `block`/`pass` add no hidden duration (they carry no
analog waveform). `measure` in 00f/00g integrates the whole 10 µs gate-open
window shifted by the (uncalibrated) 28 ns `time_of_flight`; the builder's
`time_of_flight = 200 ns` is equally uncalibrated (M3). `acquire_background`
in 02b/02c is **not** a dark shot on this machine (the imaging gate is never
touched); `ctx.measure(expose=False)` is.

## 4. What the rebuild changed  (filled in after the agents report)

## 5. Bayesian feedback port  (separate report: feedback_port_report.md)

### 4.1 Framework (k-exp/kexp/control/opx, k-exp/kexp/base, wiki) — offline-tested, 96 tests

| change | where | why |
|---|---|---|
| OPX settle wait = `t_opx_handoff_artiq_side + t_opx_handoff_opx_side` (1.35 µs); docstrings/wiki/params comments rewritten with the real numbers; the block-before-RF ordering marked "never measured (M1)" | `opx_config.kexp_channel_map`, `channels.ChannelMap`, `control.py`, `expt_params.py` comments, `TTL.py` docstring, wiki | the framework crashed on the missing `t_opx_handoff_settle`; the two sides now read one source |
| config-time parameters (`t_imaging_pulse_apd_abs`, `t_opx_integration_start/len`, `t_opx_handoff_*`, `t_opx_handback_overlap`) refused as xvars and as Adjust keys, added to `tables.accessed`; a config-time key that varies through a derived parameter is refused too | `opx_config.CONFIG_TIME_PARAMS`, `manager.check_config_time_xvars` (at `use()` and at `finish_prepare`) | a scanned acquire window would have been baked at its first declared value while ARTIQ scanned it |
| QUAM-shaped component layer: `Sticky`, `Element`, `DigitalLine`, `AnalogDrive`, `IntegratedInput`, `Machine.generate_config()/to_dict()`; `build_machine(expt, tables)`; pulse/waveform/weight names follow `<element>.<label>.pulse|wf|dm|iw`; the map is checked against the machine (every op/weight it names exists) | `components.py`, `opx_config.py`, `channels.ChannelMap.machine` | one place per element; a typo fails at `use()`; the wiring serialises |
| provenance: `opx_machine` (JSON of the machine incl. qm-qua version) and `opx_shot_tables` (accessed columns in SI, execution order, xvardims, shot-array shapes, host/cluster, job id) saved next to `opx_qua_program`; the map/machine is built from the same shot tables as the config | `manager._write_provenance`, `_call_map_builder` | a run file now reconstructs what the OPX ran without parsing QUA text |
| QMM connection moved into `use()` (prepare) | `manager._connect` | an unreachable OPX no longer claims a run id |
| shot-index echo: the OPX saves its loop counter every shot; `fill_containers` verifies `arange` and cuts the valid mask at the first mismatch with a `***` line | `builder`, `manager.fill_containers`, container `opx_shot_index` | the only ARTIQ↔OPX shot link was "one trigger per scan_kernel"; desync is now visible in the data |
| `finish()` re-entrant (marked finished only after a successful fetch); sequence `finish(expt, data)` hook; 2-D per-shot shapes, int streams (int64, `-1` for missing), host-filled containers | `manager`, `sequence.Stream` | needed by the feedback port; NaN/-1 + mask keep missing shots honest |
| one redundant global align removed from the handshake framing; settle waited on every guarded switch; `wait_s` = one align + guard for zero; IF restore align only when a drive was re-pointed | `builder.trace` | fewer non-deterministic syncs per shot |
| context API for real-time sequences: `ctx.qua`, `ctx.shot`, `ctx.n_shots`, QUA-expression durations, `raman_pulse(phase_reset=, timestamp_key=, min_cc=)`, `measure(...)` returning the variable (+ optional timestamps), `transition_offset_terms`, `stream/save`, `for_range` (saves counted × n), `shot_array` (flat per-shot QUA arrays), `host_data`, `set_transition_offset` (numeric slope with a linearity check, `Cast.mul_int_by_fixed`), `align(*names)`, `wait_cc`, `elements` | `context.py`, `sequence.py` | the feedback loop is a sequence, not a fork of the builder |
| ARTIQ safety: `cleanup_scan_kernel` switches imaging/raman RF off; `init_kernel` drops the handoff TTL | `base.py` | an underflow in the take-back or a crashed run no longer leaves RF on / AOs routed to a halted OPX |

Not done (deliberately): composite components (RamanPair/ImagingBeam/ArtiqHandshake) — `ChannelMap`/`ChannelSpec` remain the adapter; the self-timed hand-back release (design B) — a hardware change; input-stream delivery; remesh on the OPX.

### 4.2 Bayesian feedback port

Ported as a QUA sequence with the per-pulse phase-reset model, its own params
file, two ARTIQ experiments, a replay class and 24 offline tests; compiled on
the QOP simulator (constant 95-cycle per-pulse overhead; 25.7 µs posterior for
m = 21). Details, placeholders and prerequisites: `feedback_port_report.md`.

## 5. What must happen on hardware before any of this takes data

1. **M1 (scope, no atoms):** trigger → both block lines HIGH (vs the 350 ns
   assumption); hand-back edge → ARTIQ RF off (read the VERBOSE slack print);
   digital line state after `job.halt` mid-block; a run with no OPX job must
   end every shot in `TriggerTimeout` with no false edge.
2. **M2:** `qm_rabi_frequency_opx.py` / `check_rabi_frequency_apd_opx.py`
   against the ARTIQ flop — the OPX drives the AOs at the dds default
   amplitudes while ARTIQ scales by √0.3, so `t_raman_pi_pulse` must be
   re-measured for the OPX drive; then the OPX switch-path turn-on latency.
3. **M3:** APD conversion (`demod2volts` factor-2 convention, `time_of_flight`)
   and the endpoint calibration in OPX units.
4. **Feedback-specific:** confirm the per-pulse overhead is constant
   (`data.opx_schedule_slip`), tighten the compute budget, check the intensity
   servo across `reset_if_phase`.

## 6. Where things are

- Code (uncommitted, k-exp branch `jep/opx-integration`; wax `main` has only the
  `TTL.py` docstring from this work): `kexp/control/opx/` (framework),
  `kexp/experiments/opx_sequences/feedback.py`, `HF_experiments/feedback/*_opx*.py`,
  `kexp/analysis/feedback_opx.py`, `tests/test_opx*.py`, `tests/test_feedback_opx.py`.
- Docs: `k-exp/docs/opx/opx_architecture.tex` (+ `sections/`, never compiled —
  no TeX toolchain on this machine), this file, `feedback_port_report.md`; the
  wiki page `OPX-integration---Quantum-Machines-OPX+.md` rewritten.
- Phase-1 audit reports (evidence for §1–3) are in the session scratchpad and
  are summarised, not copied, here.

## 7. Recommended fixes not made here (need a decision or a measurement)

1. **Handoff margin until M1.** `t_opx_handoff_artiq_side = 350 ns` assumes the
   OPX has blocked both switch lines by then. Until the trigger-to-block latency is
   on a scope, a value that is safe by construction (several µs, as the previous
   design's 5 µs was) costs nothing but a few µs per shot. Value change = your call.
2. **`T_OPX_HANDBACK_TIMEOUT = 2 s`.** With a dead or untriggered job every shot
   spends 2 s with both switch-AOM RFs on and the OPX lines idle low (light on the
   atoms). The longest legitimate OPX body is the feedback loop (~1 ms); 0.2 s
   would do. Suggested as an `ExptParams` entry.
3. **Customer templates 01–05** play `BEAM_OFF` as the Raman pulse (inverted for
   this machine), never block imaging and never hand back; 00g accumulates the
   sticky latch and never releases the blocks between shots. Retire them or fix
   the polarity before anyone runs them again.
4. **APD path constants** are placeholders on both sides: `time_of_flight`
   (200 ns here, 28 ns in QM's config), `demod2volts` factor-2 convention,
   `gain_db` (0 here, 20 in QM's config). M3.
5. **`check_live_adjust_conflicts` runs after INIT_RUN**, so a refused run leaves
   a stub file with a claimed run id. Move it before the liveOD registration (the
   config-time xvar refusal already runs at `use()`).
6. **Adjust-panel values are not recorded per shot** anywhere (pre-existing,
   ARTIQ side): the saved params only hold the value at `end()`.
7. **Array parameters whose length equals a shuffled xvar's are unshuffled at
   save** (`waxa/data/data_saver.py`), which silently permutes e.g. a pulse list
   of `N_pulses` entries when `N_pulses` equals a scan length (pre-existing).
8. **`generate_posterior` truncates `n = int(N_photons)` while `k` stays float**
   (1.5e-4 scale mismatch at N = 1336.2, ~1e-3 in P0). The OPX port carries only
   σ/N and has no such term; align the ARTIQ code or document it.
9. **Uncaught exceptions in `run()` skip `end()`**, so OPX stream data of such a
   run is never fetched (the run file keeps zero placeholders). A `try/finally`
   around `scan()` in `Base.run` patterns, or a fetch in the atexit hook, would
   preserve it.
10. **Wiki/memory describe the random-scan-order (`shot_order`) scheme, which is
    not in this checkout** (it is a stash on `jep/random-scan-order-new`); the
    per-axis shuffle is what runs. The OPX order-equivalence argument must be
    redone if that branch lands.
