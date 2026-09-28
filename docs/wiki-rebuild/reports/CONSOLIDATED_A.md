# Consolidated research report A — areas 04 (scanning/params), 05 (device layer), 07 (monitor/device state)

Final-sweep report (2026-09-28) written after the 15-agent fan-out was stopped. k-exp HEAD c8faf77, wax HEAD acc4621 (both 2026-09-27).

**Labels.** **[C]** confirmed (code/test/commit shows it) · **[I]** inferred (reason given) · **[H]** needs a human.
**Path prefixes.** `waxx/` = `wax/waxx-src/waxx/`, `waxa/` = `wax/waxa-src/waxa/`, `kexp/` = `k-exp/kexp/`, `wtests/` = `wax/waxx-src/tests/`, `ktests/` = `k-exp/tests/`, `wiki:` = the wiki clone. Commit SHAs: 7-char wax/k-exp (history beyond the shallow clones read from full clones in `SP/a05/{wax,kexp}_full.git`).

## Coverage

| Area | Source | Depth |
|---|---|---|
| 04 Scanning and parameters | salvaged transcript (agent stopped before writing; 131 tool calls, no draft) + fresh code reads of scanner.py, dealer.py, xvar.py, expt.py, scribe.py, data_saver.py (END_RUN path), 3× expt_params.py, adjust.py, base.py | reduced: all scan/param code read; wiki Scan-loop, Numerology, Unit-conventions audited at key claims; Standard-terminology/_Commonly-used/Saving-and-loading skimmed |
| 05 Device layer | salvaged transcript (stopped before writing; no draft) + fresh reads of dds_id (waxx+kexp), DDS.py, DAC_CH.py, dac_id (both), TTL.py, ttl_id (both), devices.py, ad9910_fast_init.py, camera_id.py, device_db.py (parsed), hardware_id.py | reduced: Sampler_CH, Shuttler_CH, Grabber, mirny, ramp_math, raman_beams FFU internals, siglent/wavemeter ids NOT read |
| 07 Monitor / device state | salvaged transcript (stopped before writing; no draft) + fresh reads of monitor_server_gui.py (status, trust, fence, replace/abort_state, update), monitor_manager.py, monitor.py (announce/withdraw/sync/seed/loop), device_summary.py, device_control_gui.py (pill, dialogs), run_loop/op_queue/connections/state_reset constants, tools/monitor.py, mot_observe.py, ip.py, server_dashboard_app.py | reduced: composite.py/op_runner/telemetry/connection_agent internals, composite_panel.py, sequences_panel.py read only by constants/docstrings; Monitor wiki page audited at claim level only where doubtful |

No `NN_<area>.md` report existed for 04, 05 or 07 in `SP/reports/` (checked 2026-09-28).

**Top items for the editor (details in each area).**
1. 04: `shuffle='axis'` and `run_info/shot_order` (Scan-loop and DataVault pages) do not exist on main or any wax branch; the only scheme is per-axis shuffle, and `'axis'` == `True`. Saved params/images are unshuffled (sorted) at END_RUN.
2. 04: xvar/adjust on a derived key is overwritten every shot; bool/list params never reach the kernel; array params whose length equals an xvar length are permuted in the saved file.
3. 05: `force_dds_init` defaults to **True** since 2026-09-22 (68d8dcb8) while all docs say skipping is the default; `DAC_CH` over `max_v` writes **0 V** (wiki calls it a clamp); `ttl_frame.populate_ttl_list` footgun is already fixed (444a27e).
4. 07: plain Device Control edits are accepted while the monitor is down or a run holds the core, and are never applied afterwards (monitor baselines the file on start) — contradicting the GUI's own notice text. Needs a hardware check.
5. 07: symptom table for the Device Control GUI is in Area 07 → symptoms; status_json states/sub_states and every trust transition with its reason text are in Area 07 → reference_facts.

---

## Area 04 — Scanning and parameters

### operator_summary
- Every tunable number lives on `self.p` (an `ExptParams`), in SI units (s, Hz, V, A); detunings named `detune_*` are in linewidths Γ. Defaults are in `kexp/config/expt_params.py`; override them in your experiment's `prepare()` after `Base.__init__` with `self.p.x = ...` [C kexp/base/base.py:50-56].
- `self.xvar('t_tof', values)` makes a scan; several xvars are nested loops, the **last xvar innermost**; one pass of `scan_kernel` per combination is a **shot** [C waxx/base/scanner.py:301-312, 637-657].
- By default each xvar's value list is **shuffled per axis** (not over the full grid); the saved file is put back in sorted order at the end of the run [C waxa/base/dealer.py:77-126; waxa/data/data_saver.py:734-742].
- `N_repeats=3` repeats the **first** xvar's values 3×; the terminal prints `Scan: 30 x t_tof -> 30 shots (90 images)` [C dealer.py:55-58; scanner.py:754,776].
- `self.adjust('t_tof', ...)` adds a live knob to liveOD's Adjust panel; a change takes effect at the start of the next shot and only the last value reaches the data file [C scanner.py:521; waxx/base/expt.py:194-199,256].

### mental_model
An odometer: each xvar is a wheel, the last one spins fastest. "Shuffle" relabels the digits on each wheel at random before the ride (the wheels still turn in order); "repeats" prints each digit of the first wheel N times. Per shot [C scanner.py:399-491]:
```
abort check (cached liveOD flag) -> xvar values -> Adjust values -> params.compute_derived() -> compute_new_derived()
 -> write params to kernel (one RPC per param with a writer) -> init_scan_kernel -> scan_kernel -> cleanup_scan_kernel
 -> delay(t_recover) banked as slack -> step_scan
```

### how_to
1. Scan: in `prepare()`, after `Base.__init__(self, ...)`: `self.xvar('t_tof', np.linspace(1e-3, 10e-3, 10))`, then `self.finish_prepare()` last. Expect `Scan: 10 x t_tof -> 10 shots (30 images)` (absorption) [C scanner.py:754-777].
2. Repeats: `self.finish_prepare(N_repeats=3)` or `self.p.N_repeats = 3` before `finish_prepare()` (the argument wins) [C dealer.py:50-52].
3. Keep your order (hand-ordered lists, vector-valued xvars, feedback): `self.finish_prepare(shuffle=False)` [C scanner.py:699-700].
4. Live knob: `self.adjust('t_tof', min_val=20e-6, max_val=20e-3)` before `finish_prepare`; the stock set is `Adjust.__init__(self)` from `kexp/base/adjust.py` [C adjust.py:3-53]. Never xvar the same key.
5. Per-experiment derived values: define `def compute_new_derived(self): ...` as a plain host method (no `@kernel`) [C scanner.py:238-251; wtests/test_scanner_derived.py::test_method_override_runs_per_step].
6. Keep the shots taken before an underflow: `Base.__init__(self, save_on_underflow=True)` [C base.py:31,74; waxa/base/scribe.py:307-308,339-345].

### reference_facts
| Fact | Value | Where | Label |
|---|---|---|---|
| `finish_prepare` defaults | `N_repeats=[]`, `shuffle=True` | kexp/base/base.py:95; waxx/base/expt.py:138 | C |
| Shuffle modes | any truthy `shuffle` → per-axis shuffle; `'axis'` behaves exactly like `True`; no full-grid mode, no `shot_order` exists in wax (all refs of the full clone searched) | scanner.py:699-700; dealer.py:77-126 | C |
| `sort_preshuffle` | values `np.sort`ed before shuffling (so unshuffled data is ascending, not your order) | dealer.py:99-100 | C |
| Equal-length xvars | share one permutation | dealer.py:105-111 | C |
| `sort_idx`/`sort_N` | one permutation per distinct xvar length; sent in INIT_RUN and END_RUN payloads; stored `data/sort_idx` (padded with −1), `data/sort_N`; file attr `unshuffle_applied` | expt.py:545-546,613-614; data_saver.py:536-545,852 | C |
| N_repeats forms | int or 1-element list → first xvar only; list of length Nvars → per xvar; other list length → ValueError; **1-element ndarray → every xvar** | dealer.py:55-73 | C |
| Stored `N_repeats` | first element only after repeating | dealer.py:75 | C |
| `N_shots` | always equals `N_shots_with_repeats` (the "I have no idea what this is for" block never sees a list) | scanner.py:751,756-765 + dealer.py:75 | C |
| Images per shot | absorption 3 (forces `N_pwa_per_shot=1`); otherwise `N_pwa_per_shot + 2` | scanner.py:685-688,768-773 | C |
| No xvar | `dummy = [0]` is added | scanner.py:690-691 | C |
| Kernel writers | `int`, numpy ints (not int64), uint* → int32; `numpy.int64` → int64; float/numpy.float64 → float; ndarray → array. **bool, numpy.bool, list, str → no writer** (checked `str(type(v))` with numpy 2.4) | scanner.py:611-635 | C |
| Forbidden key chars | colon, comma, dot, space, - + ( ) @ # $ % ^ & * = ! [ ] ; / backslash, backtick, ~ | scanner.py:150 | C |
| New key | an xvar key not in ExptParams is created with `values[0]` | scanner.py:141-147 | C |
| `t_recover` | 100 ms; banked as timeline slack, host RPCs overlap it | kexp/config/expt_params.py:141; scanner.py:399-406,483-486 | C |
| `raise_underflow` | ignored since 2026-09-27 (3a25319); prints a note | scanner.py:323-324,369-372,390-391 | C |
| `save_on_underflow` | effective only with `save_data=True` | scribe.py:307-308,339 | C |
| adjust defaults | min/max = default ∓/± 0.2; step (max−min)/50; int step ≥ 1; dtype from default; start value clamped into [min,max] | scanner.py:180-204 | C |
| adjust units | display only; SI over the wire and in ExptParams | scanner.py:39,170-174; wtests/test_adjust_panel.py::test_editing_publishes_an_exact_si_value | C |
| `logspace(a,b,n)`, `powspace(a,b,n,power=3)` | log-spaced; ease-out (points bunch toward `b`) | scanner.py:116-121 | C |
| `compute_derived` | calls **every** callable attribute of params not starting with `__`, in `dir()` (alphabetical) order, no args | waxa/config/expt_params.py:14-18 | C |
| kexp derived methods | `compute_gmramp_params` (pfrac_*_gmramp_start/list, v_pd_*_gmramp_list, dt_gmramp), `compute_d1_vvas` (v_pd_d1_c_d1cmot, v_pd_d1_c_gm, v_pd_d1_r_gm), `compute_tweezer_1064_phases` (phase_tweezer_array) | kexp/config/expt_params.py:492-541 | C |
| ExptParams size | 272 distinct `self.x =` names; one duplicate (`frequency_raman_transition_nf_1m1_20`, lines 379/382, last wins) | expt_params.py (script count) | C |
| Units | `detune_*` in Γ, Γ taken as 6 MHz (ordinary), same formula for D1 and D2; `frequency_detuned_*` absolute Hz | waxx/control/artiq/DDS.py:111-138; expt_params.py:31-32 | C |
| `imaging_state` | default `2.`; `1.` → `frequency_detuned_imaging_F1` (445 MHz), `2.` → `frequency_detuned_imaging` (24 MHz); any other value sets no detuning | expt_params.py:31-33; base.py:263-266; kexp/base/image.py:475-478 | C |
| MOT detunings | `detune_d2_c_mot = -2.35`, `detune_d2_r_mot = -5.5` (Γ) | expt_params.py:195,198 | C |
| OPX handshake (2026-09-27, b2c3210) | `t_opx_handoff_artiq_side` 350 ns, `_opx_side` 1 µs, `t_opx_integration_start` 0, `_len` 5 µs, handback latency 1 µs, rtio delay 3 µs, switch fall 2 µs | expt_params.py:434-475 | C |

### expert_nuances
- **Which value wins** (earliest → latest) [C unless marked]:
  1. `ExptParams.__init__` default, then `compute_derived()` at its end (expt_params.py:490).
  2. `Base.__init__` → `prepare_devices(expt_params=self.params)` builds the frames **now**: DDS default frequencies from `detune_*`, DAC defaults from `v_*` are captured (kexp/config/dds_id.py:68-130; dac_id.py:20-43). A later `self.p.detune_d2_c_mot = ...` does not change `dds.d2_3d_c`'s default; code that calls `set_dds_gamma(self.p....)` does use it [I from construction order, base.py:66].
  3. `self.p.x = v` in `prepare()`.
  4. `xvar()` creates a missing key (141-147); `adjust(default_val=...)` overwrites, without `default_val` keeps the current value (176-212).
  5. `finish_prepare` → `init_xvars`: `plug_in_xvars` sets each xvar key to `values[0]` (dealer.py:28-34), repeats, shuffle, `compute_derived` (scanner.py:705-706).
  6. Every shot: xvar value → Adjust value → `compute_derived()` → `compute_new_derived()` (scanner.py:509-524). **An xvar or adjust on a derived key is overwritten every shot** (e.g. scanning `v_pd_d1_c_gm` does nothing; scan `pfrac_d1_c_gm`).
  7. Only params with a writer reach the kernel (611-635).
  8. `end()`: `cleanup_scanned` sets xvars to their full arrays in shot order and reruns `compute_derived` (659-677) — so a scanned **derived** key ends in the file as the derived scalar, not the scanned list [I from 670-674]; END_RUN sends host params (expt.py:607-611); liveOD's DataSaver unshuffles every numeric array param with an axis whose length equals an xvar length (data_saver.py:734-742, 948-975).
- Adjust timing: values arrive in each SHOT_COMPLETE reply (expt.py:256) and are applied at the top of the **next** shot (scanner.py:521); an edit during the last shot is never applied [I]. Int specs are coerced back from JSON floats, keeping numpy int type so `fetch_int32/64` matches (scanner.py:43-59; expt.py:376-384).
- Abort latency: the liveOD reset flag is read from the last SHOT_COMPLETE reply; one real POLL before shot 1 (scribe.py:242-257). A reset pressed mid-shot raises `TerminationRequested` in `_notify_shot_complete` (expt.py:261-265). Both exit through `scan()`'s generic handler → device state reported **trusted** (scanner.py:348-350; expt.py:354-360).
- Exception routing since 2026-09-27 (3a25319) [C scanner.py:430-477]: `RTIOUnderflow`, `TriggerTimeout`, `RTIOOverflow` → `cleanup_scan_kernel` (with the shot's data write and SHOT_COMPLETE) → `_abort_shot` → bare `raise` keeps the core-device traceback; anything else → `cleanup_abort_kernel` (no data write) → re-raise.
- `save_on_underflow`: the failing shot's cleanup ran, so it is counted; the loop ends after that shot; terminal `run id N ended at <time> after n of N shots (expt)` (expt.py:439-442) [C]; that shot's frames may be missing [I].
- Vector-valued xvars (values of shape (N, k), "step over first index", scanner.py:128): `sort_preshuffle` uses `np.sort` along the **last** axis, reordering the numbers inside each row (verified with numpy). Use `shuffle=False` [C].
- A list param scanned directly with a list of arrays (kexp/experiments/test/list_scan_test.py:14) becomes an ndarray at `plug_in_xvars` and **does** get an array writer; a list param recomputed on the host (e.g. in `compute_new_derived`) stays a list and gets **none** [C scanner.py:611-635; dealer.py:28-34].
- Integer xvar values (`[1,2,3]`) become `numpy.int64` → int64 writer; kernel code mixing it with int32 can fail to compile [I].
- `adjust` after `xvar` on a key → printed warning, skipped; `xvar` after `adjust` → `ValueError` (scanner.py:130-131,194-196).
- INIT_RUN writes an initial params snapshot; END_RUN overwrites it (data_saver.py:784). A run killed before END_RUN keeps xvars at their first value in `params/` [I].
- The OPX-parameter comment says these are "refused" if scanned (expt_params.py:437-438) — `kexp/control/opx*` does not exist on this branch; nothing refuses [C `ls kexp/control`].

### loud_failures
```
ValueError: xvar key 't_tof' is already registered as an adjust param.
```
scanner.py:131 — `self.xvar` after `self.adjust` (or after `Adjust.__init__`) on the same key. Fix: drop one.
```
ValueError: xvar of key t_tof is assigned more than once.
```
scanner.py:134 — template `f"xvar of key {key} is assigned more than once."`.
```
ValueError: Key contains forbidden characters.
```
scanner.py:152 — e.g. `self.xvar('t.tof', ...)`.
```
ValueError: param 'my_knob' does not already exist, so a dtype or default_val must be provided
```
scanner.py:182-184 — `adjust` on a new key without `dtype`/`default_val`.
```
ValueError: adjust key 't_tof' already registered.
```
scanner.py:193.
```
Warning: adjust key 't_tof' is already an xvar; skipping adjust registration.
```
scanner.py:195 — printed only; no knob appears in the Adjust panel.
```
[adjust] WARNING: adjustable params detected with save_data=True. Values changed in the Adjust panel between shots will NOT be reflected in saved data.
```
expt.py:195-198 — every run with an adjust spec and `save_data=True`.
```
[scan] scan(raise_underflow=True) is no longer needed and is ignored: an aborted shot is always cleaned up, and the original exception is re-raised with its traceback (2026-09-27).
```
scanner.py:370-372 — remove the argument.
```
[scan] shot aborted: a triggered wait saw no edge (TriggerTimeout, see the line above). Cleaning up and ending the run.
[scan] shot aborted: an RTIO input FIFO overflowed (RTIOOverflow) -- a TTL input is toggling far faster than expected. Cleaning up and ending the run.
```
scanner.py:444-446, 457-459.
```
[Scanner] RTIOUnderflow: run 83120 aborted after cleanup; the original exception and its traceback follow.
[Scanner] RTIOUnderflow on run 83120: save_on_underflow=True — proceeding to analyze() to save partial data.
```
scribe.py:314-315, 344-345 (template `[Scanner] {what}: run {run_id} ...`).
```
RuntimeError: Acquisition for run 83120 aborted.
```
scribe.py:261 — the liveOD Abort button, seen at the top of the next shot.
```
ValueError: self.params.repeats must have either have one element or length equal to the number of xvarnames
```
dealer.py:54,65,70 — `N_repeats` list/array of the wrong length.
```
TypeError: 'float' object is not subscriptable
IndexError: invalid index to scalar variable.
```
dealer.py:73 — `N_repeats = 3.` (float) or a numpy scalar (`np.int64(3)`): neither is caught by the int/list/ndarray branches [C branch logic; Python messages verified].
```
You indicated more than one PWA per shot, but the analysis is set to absorption imaging. Setting # PWA to 1.
```
scanner.py:687.
```
<exception text>
Derived parameters were not updated.
```
scanner.py:676-677 — `compute_derived` failed on the full xvar arrays at `end()`; saved derived values are stale.
```
[DataSaver] Failed to save param 'x': <exc>
```
waxa/data/data_saver.py:792 — a param h5py cannot store (ragged list, object); that key is missing from `params/`.

### demon_candidates
1. **Wiki promises a full-grid shuffle and `run_info/shot_order`; the code never had either on main.** Scan-loop page lines 53-96 and DataVault page describe it (wiki commit fccf8e7, 2026-09-10); wax (all refs incl. `jep/random-scan-order-new`) has no `shot_order`; `kexp/analysis/rabi_posterior_cli.py:171-189` looks for it, then falls back to `data/sort_idx` or "sequential (assumed...)". Anyone planning drift decorrelation from the wiki gets per-axis shuffling (outer axis changes once per inner sweep). *Seen and confirmed.*
2. **Scanning or adjusting a derived key silently does nothing** (step 6 above). Host prints and liveOD's xvar readout show the scanned value; the kernel gets the recomputed one. *Seen and confirmed (code).*
3. **Saved array params scrambled by coincidence of length.** Any numeric list/array param with an axis equal to an xvar length (e.g. the 4-element `frequency_tweezer_list1` with a 4-point xvar, or any 5-element list with `dummy` + `N_repeats=5`) is permuted by the END_RUN unshuffle (data_saver.py:734-742). The kernel used the right values; the file is wrong. *Seen and confirmed (code); no incident known.*
4. **bool/list params never reach the kernel after compile** (no writer). Host code and prints change; the kernel keeps the first value. Flagged in `kexp/util/profiling/KERNEL_INVARIANTS_PLAN.md` "pre-existing bugs". *Confirmed (code).*
5. **Repeat metadata lies for per-xvar repeats:** `N_repeats=[1,3]` stores `N_repeats = 1` (dealer.py:75). *Confirmed.*
6. **Adjusted values: file holds one number** (the last applied), and an edit in the last shot is dropped. The only warning is the prepare-time line. *Confirmed/inferred as marked above.*
7. **1-element ndarray `N_repeats` repeats every xvar** while int/list repeat only the first (dealer.py:55-68) — shot count silently multiplies. *Confirmed.*
8. **Vector xvars reordered inside each row by `np.sort`** with the default shuffle. *Confirmed (numpy).*

### symptoms
- "I scanned `v_pd_d1_c_gm` (or `dt_gmramp`) and nothing changed; `ad.params.v_pd_d1_c_gm` is one number, not my list." → derived key; scan the source (`pfrac_d1_c_gm`, `t_gmramp`). Misleading: liveOD's xvar display shows the values you asked for.
- "The host printed a new `frequency_tweezer_list` every shot but the atoms did the same thing" → list/bool param without a writer.
- "My 2-D scan's outer axis changes only once per inner sweep although shuffle is on" → per-axis shuffle (demon 1).
- "`ad.params.frequency_tweezer_list1` in the file is in a different order than in expt_params.py" → demon 3.
- "The Adjust panel doesn't show `t_tof`" and earlier in the terminal: `Warning: adjust key 't_tof' is already an xvar; skipping adjust registration.`
- "I set N_repeats per xvar and the file says N_repeats = 1" → demon 5.

### terms_used
- **xvar** — a parameter the run steps through; like one wheel of an odometer. `self.xvar('t_tof', np.linspace(...))`.
- **shot / run / scan** — one pass of the sequence for one set of xvar values / all shots under one run ID / changing a parameter between shots. `scan_kernel` is one shot.
- **ExptParams, `self.p`** — the object holding every parameter as an attribute. `self.p.t_tof = 50e-6`.
- **derived parameter** — a param computed from others by a method of ExptParams each shot. `compute_d1_vvas` sets `v_pd_d1_c_gm` from `pfrac_d1_c_gm`.
- **host / kernel** — the PC-side Python process / the code compiled to run on the ARTIQ core device. `@kernel def scan_kernel(self)`.
- **RPC** — a kernel calling back into host Python. `fetch_float(i)` (scanner.py:556).
- **kernel writer (assignment kernel)** — a tiny compiled function `self.params.<key> = value` generated per param so the kernel copy can be updated each shot (scanner.py:611-635).
- **type (dtype): int32, int64, float, ndarray, bool, list** — what kind of value a variable holds; the kernel needs one fixed type per param. `np.int32(50)` pins int32 (waxx/config/expt_params.py:16).
- **repeat, `N_repeats`** — taking the same xvar value several times.
- **shuffle, `sort_idx`, `sort_N`** — random reordering of each xvar's values; the permutation saved to undo it.
- **unshuffle** — putting saved data back in sorted order (liveOD's DataSaver at END_RUN).
- **`xvardims`** — list of xvar lengths after repeats = the saved data's grid shape.
- **dummy xvar** — `dummy=[0]` added when you define none.
- **adjust / Adjust panel** — a live spin box in liveOD for a param; `self.adjust(...)`.
- **`compute_new_derived`** — your own per-shot host hook.
- **`t_recover`, slack** — pause between shots, and the lead the timeline keeps over real time.
- **RTIOUnderflow** — an event scheduled for a time already past; the shot is abandoned.
- **`save_on_underflow`** — keep the shots taken when a shot underflows.
- **SI units, Γ (linewidth)** — seconds/Hz/volts; detunings in units of the transition linewidth (6 MHz).
- **INIT_RUN / SHOT_COMPLETE / END_RUN** — the messages the experiment sends liveOD at start, after each shot, at the end.

### prerequisites
host vs kernel; ARTIQ timeline and slack; ExptParams; run/shot/scan; liveOD (run ID, data file); Python types; HDF5 file layout (`params/`, `data/`).

### wiki_audit
**Scan-loop-and-parameter-scanning (657 lines, 2026-09-10)** — keep structure, rewrite key sections.
- l.53-57, 74, 82-96, 335, 648, 653: full-grid shuffle, `'axis'` legacy mode, `run_info/shot_order`, `atomdata.reshuffle()` → **wrong** (never implemented on main; demon 1).
- l.62 "argument wins if you give both" → correct (dealer.py:51-52).
- l.66, 391-399 plug-in of first value for type safety → correct.
- l.68-70 "duplicate each xvar combination" → **wrong in detail**: an int repeats the first xvar's values (consecutive duplicates), not grid cells.
- l.223-253 lifecycle box "creates data file", "end() ... increments run ID" → **stale**: liveOD creates the file and assigns the run ID at INIT_RUN (expt.py:173-181).
- l.255-283 `scan()` pseudocode → **stale**: no abort check, t_recover, break_realtime or 2026-09-27 exception handling.
- l.285-297 hook table "init_scan_kernel: check data file exists (abort detection)" → **wrong**: abort detection is `_check_for_abort_signal` (liveOD flag, scribe.py:233-264).
- l.341-357 update pipeline → correct but omit Adjust values (scanner.py:521).
- l.453-597 assignment kernels → mostly correct; RPC names are `fetch_float/int32/int64/array`, not `_get_float_param` (l.564) → minor wrong; missing "bool/list get no writer" → add.
- l.599-640 cleanup: `end()` with `write_data`, `update_run_id()` → **wrong** (END_RUN payload to liveOD; expt.py:386-423). "atomdata.params.t_tof is the full array" → correct, and sorted (unshuffled).
- Missing: exception handling and `save_on_underflow`, `raise_underflow` ignored, t_recover, derived-key override, adjust semantics.
**Numerology-‐-which-parameters-do-what (79 lines)** — naming grammar correct; **wrong names**: `amp_lightsheet`, `frequency_ao_lightsheet`, `amp_imaging` are not ExptParams (`amp_imaging` is a camera_params attribute, waxx/control/cameras/camera_param_classes.py:156-164). Add "do not scan derived keys" and the imaging_state note.
**Unit-conventions-and-parameter-naming (324 lines)** — Γ ≈ 6 MHz, `detune_` vs `frequency_detuned_` → correct (DDS.py:131-138). Examples use −15 Γ for the MOT while the defaults are −2.35/−5.5 Γ → illustrative only; say so.
**Standard-terminology (20 lines)** — definitions correct; fold into the glossary. **_Commonly-used-kexp-objects** — `camera: BaslerUSB or AndorEMCCD` attribute → unverified in this sweep, likely stale (cameras are run by liveOD) [I]. **Saving-and-loading-data** — "data file is initially saved by the experiment itself" → stale (liveOD creates it) [I from expt.py:176-178]; area 09 owns it.
Preserve for Internals: assignment-kernel mechanism; odometer order; unshuffle mechanics.

### needs_a_human
- Did anyone rely on the wiki's full-grid shuffle / `shot_order` for published drift analysis? Is the `random-scan-order` work meant to be merged?
- Is the ~25 % first-shot deficit (base.py:82-86) still true, and should `warmup_shots` default change?
- Which scans are vector-valued in practice (demon 8)?

### proposed_topics
- "Scanning: xvars, repeats, shuffle, what is saved" — experimenter, tier 2 (replaces most of Scan-loop).
- "Which value wins: defaults, prepare, xvar, adjust, derived, file" — experimenter/expert lookup, tier 2.
- "Live Adjust panel" — experimenter, tier 2.
- "Parameter types and the kernel (writers, bool/list trap)" — expert lookup, tier 3.
- "Underflow and aborted shots: what happens to the run" — experimenter, tier 2 (shared with areas 03/14).
- "Scan loop internals (assignment kernels, t_recover slack)" — maintainer, tier 4.

### question_bank_answers
- **N5** `self.p.t_tof = 0.05e-3`: sets the ExptParams attribute `t_tof` to 50 µs; all params SI, `detune_*` in Γ [C expt_params.py; DDS.py:111-138].
- **N6** `self.xvar('t_tof', np.linspace(a,b,n))`; shots = product of xvar lengths with the first multiplied by N_repeats (or per-xvar list); printed `Scan: n x t_tof -> N shots (3N images)` for absorption [C dealer.py:55-73; scanner.py:745-777].
- **N15** Defaults: `kexp/config/expt_params.py`; override in the experiment after `Base.__init__`; edit the file only to adopt a new default (the file text is saved with every run as `params_file_text`, expt.py:592,623) [C].
- **E2** A list param that stays a list (recomputed on the host, or set once) has no writer (scanner.py:611-635); a list xvar given as a list of arrays becomes ndarray and does get one [C]. Bools: same trap.
- **E3** `xvar` after `adjust` raises (scanner.py:130-131); `adjust` after `xvar` warns and skips (194-196). Rule: a key is either scanned or adjusted, and xvar wins if it came first [C].
- **E4** In the **file**, `ad.params.t_tof` is **sorted** (ascending): cleanup_scanned stores shot order (scanner.py:664-665) but liveOD's DataSaver unshuffles all array params, images and DataVault at END_RUN (data_saver.py:692-742) and sets `unshuffle_applied`. Acquisition order is recoverable from `data/sort_idx` (1 permutation per xvar length) [C]. The bank's expected answer ("not unshuffled") is wrong for saved data.
- **E16** The file's `params/<key>` for an adjusted param is the host value at END_RUN: the last value applied, one number; xvars are the only per-shot record [C expt.py:607-611; I that nothing else records adjust history — no other writer found].
- **E17** `detune_d2_c_mot = -2.35` → Γ (6 MHz); `frequency_detuned_imaging = 24.e6` → Hz. `imaging_state = 1.` makes `reset_devices` (every shot, via init_scan_kernel) set `frequency_detuned_imaging_F1` (445 MHz); `2.` uses `frequency_detuned_imaging` [C base.py:237,263-266].
- **Missing questions**: "I scanned a derived param and nothing happened — why?"; "Why is my saved tweezer list in a different order?"; "Does shuffle randomize the full grid?"

### bugs_and_footguns
| Where | What happens | Hurts operator |
|---|---|---|
| wiki Scan-loop vs dealer.py:77-126 | documented full-grid shuffle/`shot_order` absent | high |
| scanner.py:509-524 + expt_params.py:492-541 | xvar/adjust on derived keys overwritten each shot, no warning | high |
| data_saver.py:734-742 | unrelated array params permuted when a length matches an xvar | medium |
| scanner.py:611-635 | bool/list params get no kernel writer, no warning | medium |
| dealer.py:99-100 | `np.sort` scrambles vector-valued xvar rows under default shuffle | medium |
| dealer.py:66-68 | 1-element ndarray N_repeats repeats all xvars | low |
| dealer.py:75; scanner.py:756-765 | per-xvar repeats stored as first element; `N_shots` dead logic | low |
| dealer.py:55-73 | float/numpy-scalar N_repeats → opaque TypeError/IndexError | low |
| expt_params.py:437-438 | comment promises OPX params are refused; nothing enforces | low |
| expt_params.py:379,382 | duplicate assignment, last wins | low |
| kexp/base/base.py:263-266 | `imaging_state` other than 1./2. silently sets no detuning | low |

---

## Area 05 — Device layer

### operator_summary
- Each ARTIQ output/input channel has a Python wrapper: `DDS` (an Urukul AD9910 channel), `DAC_CH` (a Zotino channel), `TTL_OUT` / `TTL_IN` [C waxx/control/artiq/{DDS,DAC_CH,TTL}.py].
- Wrappers of one kind are grouped in a **frame**: `self.dds`, `self.dac`, `self.ttl`, built by `Devices.prepare_devices()` during `Base.__init__` [C kexp/base/devices.py:70-114; base.py:66].
- Which physical channel gets which name is decided in `kexp/config/{dds_id,dac_id,ttl_id,camera_id}.py`; the attribute name is the name everything else uses (the Device Control GUI, the state file, experiments) [C waxx/config/dds_id.py:149-154; dac_id.py:47-53].
- The crate: 6 Urukuls × 4 = 24 DDS, one 32-channel Zotino, 88 TTLs (80 outputs, inputs on ttl40–47) [C kexp/config/dds_id.py:21-23; dac_id.py:11; ttl_id.py:10; device_db.py parsed].
- Every run re-initializes all 24 DDS chips by default (~1.4 s), although the code and docs describe a fast path that skips intact chips — the default was flipped on 2026-09-22 [C base.py:155; commit 68d8dcb8].

### mental_model
A patch panel with a label maker: the `_id` files are the labels stuck on each jack (`d2_3d_c` = Urukul 1 channel 2); the frame is the panel; unlabeled jacks keep a stock label (`urukul0_ch1`, `zotino0_ch14`, `ttl23`). The wrapper remembers the last value it *sent* (not what the hardware has) and skips sending the same value twice.

### how_to
1. **New DDS channel**: in `kexp/config/dds_id.py.__init__` add `self.my_aom = self.dds_assign(uru, ch, default_freq=80.e6, default_amp=0.3, ao_order=1)` (or `default_detuning=... , transition='D2'` instead of `default_freq`; `dac_ch_vpd=self._dac_frame.<dac>.ch` for VVA/PID power) before `self.cleanup()` [C kexp/config/dds_id.py:52-133].
2. **New DAC**: `self.my_dac = self.assign_dac_ch(ch, v=0., max_v=5.)` in `kexp/config/dac_id.py` [C dac_id.py:20-46].
3. **New TTL**: `self.my_ttl = self.assign_ttl_out(ch)` / `assign_ttl_in(ch)` in `kexp/config/ttl_id.py`; inputs only on the TTLInOut channels 40–47 [C ttl_id.py:20-69; device_db].
4. **New camera**: a `BaslerParams(serial_number=...)` / `AndorParams(...)` attribute in `kexp/config/camera_id.py`; choose it with `Base.__init__(self, camera_select=cameras.<key>)` [C camera_id.py:22-62; base.py:27].
5. **After editing an `_id` file**: restart the monitor (Device Control status row) — at start it reconciles the state file's key set with the frames (adds/removes/renames, carrying values across a rename by channel) and prints `[Monitor] Device state file rebuilt from the device frames.` [C waxx/base/monitor.py:372-405]. Do **not** run `_bat/regenerate_device_state_file.bat` while the monitor server runs (area 07, demon 3).
6. Force a full DDS init (after touching Urukul clocking/SYNC): `self.init_kernel(force_dds_init=True)` — today already the default [C base.py:155-161].

### reference_facts
| Fact | Value | Where | Label |
|---|---|---|---|
| `dds_assign` signature | `(uru, ch, default_freq=dv, default_detuning=dv, default_amp=dv, ao_order=0, double_pass=True, transition='None', dac_ch_vpd=-1)`; `dv = -0.1` | waxx/config/dds_id.py:83-85,25 | C |
| DDS with `dac_ch_vpd >= 0` | gets the frame's real `DAC_CH`; `v_pd` seeded from that DAC's default; else a dummy `DAC_CH(ch=-1)` whose methods are no-ops | dds_id.py:121-130 | C |
| detuning → frequency | `f = (461.7/2 + ao_order·Δ·6) / 2` MHz (×2 if not double pass); Γ = 6 MHz for D1 and D2; `transition` is stored but **not used** | DDS.py:111-138; only other reader kexp/util/guis/_old/dds/dds_gui.py:164 | C |
| `set_dds` args | negative = keep; only changed values are sent; frequency/amplitude/phase quantized to FTW/ASF/POW and the *quantized* value cached; `init=True` sends everything | DDS.py:177-257 (220-243) | C |
| `set_dds(frequency=0.)` | sets 0 Hz; does not touch the RF switch | DDS.py:220,231,247 | C |
| `off()` / `on()` | switch off **and** linked DAC to 0 V (remembering v_pd); `on()` restores v_pd then switches on; `dac_update=False` skips the DAC | DDS.py:313-330 | C |
| `stash_defaults` / `reset_defaults` | copy/restore frequency and amplitude only (not v_pd) | DDS.py:97-105; dds_id.py:179-187 | C |
| Phase | `t_phase_origin_mu` shifted by 2030−688 = 1342 mu; io_update delay = 91 − 4 + EEPROM delay mu | DDS.py:14-16,93-95,237 | C |
| DAC `max_v` | default 9.99 V; kexp: `outer_coil_supply_current` 7.0, `v_pd_tweezer_pid2` 10.0 | DAC_CH.py:14-18; kexp/config/dac_id.py:29,36 | C |
| DAC over `max_v` | channel written to **0 V** (not clamped), message printed asynchronously; ramps over `max_v` print and write nothing | DAC_CH.py:26-38,69-71,99-101 | C |
| DAC cache | `self.v` updated **before** `write_dac`; ramps update `self.v` only after the last point | DAC_CH.py:29-36,83,113 | C |
| TTL_OUT.pulse | does not change `state` | TTL.py:38-43 | C |
| TTL_IN | `arm()` (drains old events, opens gate), `wait_for_edge(t_delay, t_timeout)` → edge time or −1, `wait_for_line_trigger` raises `TriggerTimeout`; every TTLInOut drained each shot by `cleanup_scan_kernel_wax` (since 2026-09-23, 444a27e) | TTL.py:79-144; waxx/config/ttl_id.py:33-47; expt.py:211-220 | C |
| AD9910 fast init | skip a channel when: no core reboot since full init (core cache), CFR3 matches, SYNC receiver on, PLL locked, SMP_ERR clear; skipped channels still get CFR1/CFR2 defaults; cache key `kexp_ad9910_sync_data_24` | waxx/control/ad9910_fast_init.py:9-24,104-109,112-157; devices.py:113-118 | C |
| Fast-init record | JSON attr `dds_init` in the run's HDF5 (`{"report": {n_full, n_channels, why, t_total_s, t_check_pass_s}, "failures": [...]}`) | ad9910_fast_init.py:55-57,214-245; wtests/test_ad9910_fast_init.py::test_every_run_keeps_its_outcome_with_its_data | C |
| `force_dds_init` default | **True** since 2026-09-22 (68d8dcb8 "cut prints, conditional ry 980 siglent reset"; was False from 6c0d2947, 2026-09-18); docstring still says "By default (False)" | kexp/base/base.py:155-161 | C |
| Cameras (`cameras.<key>`) | `xy_basler` (40316451, default), `x_basler` (40320384, Line2), `z_basler` (40416468), `basler_2dmot` (40277703, replaced 2026-09-26), `andor`, `apd` | kexp/config/camera_id.py:22-62; base.py:27 | C |
| device_db | `core_addr = "192.168.1.75"` in the repo copy; hardware id = last octet → `monitor:75`, state file `device_state_config_75.json` | kexp/util/db/device_db.py:3; waxx/util/comms_server/hardware_id.py:95-116; kexp/config/ip.py:56-62 | C (repo file); which file `%db%` points to on kong [H] |

### expert_nuances
- **Mixin `__init__`s never run.** `Base(Expt, Devices, Cooling, ...)` → `Expt.__init__` → `super().__init__()` → `Scanner.__init__`, which does not call `super()`; `Devices.__init__` (the placeholder frames, devices.py:56-68) is never executed — the placeholders exist only for the IDE [C base.py:20; expt.py:65,86; scanner.py:74-114].
- Frames are built from `self.params` at `Base.__init__` time; DDS default frequencies/amplitudes and DAC default voltages are fixed then (dds_id.py:68-130; dac_id.py:22-27). `finish_prepare` and `init_kernel(dds_set=True)` stash current values as defaults (base.py:109; 191-192), and `set_all_dds` sends them with `init=True` (devices.py:290-294) [C].
- Skip-if-equal: `set_dds` compares against the cached (last *commanded*) value. If the hardware differs from the cache (after an abort, a power cycle, another process), re-sending the same value does nothing; use `init=True` or change and change back [C DDS.py:218-229].
- `make_dds_array` fills unassigned channels using waxx's **module** constants `N_uru = 1, N_ch = 4` (waxx/config/dds_id.py:16-18,169-177), not the kexp frame's 6×4. Today only (0,1) and (0,2) are unassigned, so it works by luck; an unassigned channel on Urukul 1–5 would keep the unnamed `DDS` built in `setup()` [C].
- `_write_dac_keys` runs before `populate_attrs` (dac_id.py:24-26,47-53): placeholder DAC channels (`zotino0_ch14` …) never get `set_errmessage()`, so their `max_voltage_error()` would raise `AttributeError: 'DAC_CH' object has no attribute 'errmessage'` in an async RPC [C code; flagged in KERNEL_INVARIANTS_PLAN.md].
- `dac_by_ch` finds any channel 0–31 (placeholders included), so `dac_ch_vpd` pointing at an unassigned channel silently links to a placeholder with `max_v` 9.99 [C dac_id.py:32-37,55-61].
- `ttl_frame.populate_ttl_list` "reuses previous loop value" (recon, KERNEL_INVARIANTS_PLAN) is **fixed**: since 444a27e (2026-09-23) each iteration starts from `self.ttl_list[ch]`; a class other than TTLOut/TTLInOut stays a bare `TTL` [C waxx/config/ttl_id.py:49-60].
- `assign_ttl_out/in` do not check the device_db class; a wrong direction fails later (compile or run) [I ttl_id.py:62-70].
- Fast-init cache is scoped to the channel count (adding a DDS forces one full init, then caches again) [C ad9910_fast_init.py:104-109; wtests/test_ad9910_fast_init.py::test_cache_key_is_scoped_to_the_channel_count]. Validated on hardware only for the all-intact case; reboot, power-cycle and phase-coherence checks "still owed" [C docstring 89-92].
- The monitor experiment's `init_kernel` call does not pass `force_dds_init`, so every monitor start (after every run) also does the full AD9910 init, CPLD init and `set_att(0 dB)` [C kexp/experiments/tools/monitor.py:54-64; devices.py:313-318]; effect on live outputs [H].
- `detuning_to_frequency` docstring says it returns MHz; it returns Hz [C DDS.py:113-138].

### loud_failures
```
ValueError: Only one of default_detuning and default_freq must be set in dds_id.py.
```
waxx/config/dds_id.py:139 — both given in a `dds_assign`.
```
ValueError: DAC channel 7 is forbidden.
ValueError: DAC ch 40 not assigned in dac_id.
```
waxx/config/dac_id.py:41 (`FORBIDDEN_CH`, empty in kexp), :61 (`dac_ch_vpd` ≥ 32).
```
Attempted to set dac ch outer_coil_supply_current to a voltage > specified maximum voltage (7.000) for that channel. DAC voltage was replaced by zero for these instances.
```
waxx/control/artiq/DAC_CH.py:23 (template `...dac ch {key} ... ({max_v:1.3f})...`), printed by the async RPC at :41-42 — the run continues with that channel at 0 V.
```
ValueError: Both the xy and x imaging fibers are currently derived from the PID setup (as of 2026-02-17)
```
kexp/base/devices.py:252.
```
[dds init] full init on 24 of 24 channels, 0 skipped (forced), 1400 ms
[dds init] WARNING: urukul 3 ch 1 failed its check (PLL not locked, raw 0x...) -- running the full AD9910 init on it.
[dds init] WARNING: could not store the DDS init outcome with the run: <exc>
```
waxx/control/ad9910_fast_init.py:225-227 (NORMAL verbosity when any channel is fully initialized — i.e. **every run** at the current default), :254-255, :244-245. `why` ∈ `forced`, `no cache: first run since the core device booted`, `cache has N values, expected M`, `cache hit`.
```
TriggerTimeout: no rising edge on ttl40 within the gate window
```
waxx/control/artiq/TTL.py:134-135 (template `ttl{0}` filled with the channel; exact rendering by ARTIQ [I]).

### demon_candidates
1. **Fast DDS init is off by default, docs say on.** `force_dds_init = True` since 68d8dcb8 (2026-09-22); docstring, `Devices.init_all_dds` docstring and the module doc still describe skipping as the default. Every run pays ~1.4 s and prints a `[dds init] full init ... (forced)` line people learn to ignore. *Seen and confirmed.* Whether the flip was deliberate [H].
2. **DAC over-limit writes 0 V and keeps going.** A typo or scan past `max_v` turns a coil or VVA *off*, with one async line in the terminal (DAC_CH.py:29-33). The wiki calls `max_v` a "clamp". *Confirmed.*
3. **Cached value ≠ hardware.** `DAC_CH.set` caches before writing; `set_dds` skips values equal to the cache. After a failed write or outside interference, the frame (and the monitor's state file built from it) shows the commanded value, and a re-send of it is skipped. This is why `RTIOUnderflow`/`ValueError` aborts are reported untrusted (waxx/base/scanner.py:21-25). *Confirmed.*
4. **`transition` does nothing.** A D1 AOM with `transition='D1'` uses the same 230.85 MHz crossover offset and 6 MHz Γ as D2 (DDS.py:131-136). Whether that is physically right for the D1 locks [H].
5. **Placeholder links.** `dac_ch_vpd` pointing at an unassigned DAC silently binds a placeholder (no error message attribute, no name). *Confirmed (code).*

### symptoms
- Terminal on every run: `[dds init] full init on 24 of 24 channels, 0 skipped (forced), ~1400 ms` — expected by the docs to be quiet with all skipped. Not an error; demon 1.
- Coil or beam unexpectedly off mid-scan; terminal earlier printed `Attempted to set dac ch ... DAC voltage was replaced by zero for these instances.` → value above `max_v`.
- A DDS "does not respond" to `set_dds(frequency=f)` with the frequency it already had → cache skip; use `init=True`.
- `TriggerTimeout: no rising edge on ttl40 ...` then `[scan] shot aborted: a triggered wait saw no edge ...` → line trigger cable/signal missing [H for the physical check].

### terms_used
- **DDS / Urukul / AD9910** — a chip that synthesizes an RF sine wave of chosen frequency, amplitude, phase; Urukul is the 4-channel card holding four. `self.dds.d2_3d_c`.
- **AOM, AO order, double pass** — acousto-optic modulator shifting light by the RF frequency; the diffraction order (+1/−1); light passing twice (shift doubled). `ao_order=-1`.
- **VVA / PID setpoint, `v_pd`** — a voltage (from a DAC) that sets RF power instead of the DDS amplitude. `dac_ch_vpd=self._dac_frame.vva_d1_3d_c.ch`.
- **DAC / Zotino** — card producing 32 analog voltages (±10 V). `self.dac.xshim_current_control`.
- **TTL** — a digital on/off line; TTLInOut can also timestamp incoming edges. `self.ttl.line_trigger`.
- **frame** — the object grouping all channels of one kind. `self.dds`.
- **wrapper** — our class around ARTIQ's driver adding names and caching. `DDS.set_dds`.
- **cache (cached value)** — the wrapper's memory of the last value sent. `DAC_CH.v`.
- **FTW / ASF / POW** — the integer register words for frequency, amplitude, phase.
- **io_update, SYNC, PLL, CFR** — DDS register-latch pulse, multi-chip clock alignment, the chip's clock multiplier, configuration registers (see ad9910_fast_init.py docstring).
- **device_db / core_addr** — ARTIQ's table of every device; the core device's IP. `kexp/util/db/device_db.py`.
- **hardware id** — last number of `core_addr`, used to name the monitor and its state file.
- **placeholder** — an unassigned channel with a stock name, or an IDE-only object in `__init__`.
- **MRO / `super()`** — Python's rule for which parent method runs; here it stops at `Scanner.__init__`.

### prerequisites
ARTIQ basics (core device, RTIO, kernel); AOM physics and detuning in Γ; Python classes/attributes; ExptParams; the Monitor state file (area 07).

### wiki_audit
- **Device-Frames (10 lines)** — concept correct; "frame classes defined in `kexp\config\`" → correct (bases in `waxx/config`); "instantiated in the `devices` base class" → correct (`prepare_devices`). Stub; merge.
- **_DDS-Objects (33 lines)** — attribute `att_dB` → **wrong** (no such attribute; attenuation fixed at 0 dB in `init_all_cpld`); "if not supplied, sets to stored values" → **wrong** (skips unchanged); "frequency zero turns the dds off" → **wrong** (0 Hz, switch untouched); `on/off` → incomplete (they also zero/restore the linked DAC); "instantiated in `devices.__init__()`" → **stale** (`prepare_devices`).
- **Device-configuration-reference (104 lines)** — `dds_assign` signature → correct; `default_detuning` "Requires ao_order and transition" → half wrong (`transition` unused; `double_pass` matters); `max_v` "Safety clamp — will not be driven above this" → **wrong** (it zeros the channel); TTL/DAC assign signatures → correct.
- **Adding-new-hardware (206 lines, 2026-08-05)** — AOM/TTL/DAC steps broadly right; missing: monitor reconcile of the state file after `_id` edits, composite-device definitions, camera keys; LAN/relay sections not checked in this sweep.
- **Fast-DDS-freuqency-updates (180 lines, 2026-06-11)** — table l.181 names `set_up_ffu`, `enable_aggressive_ffu`, `clean_up_ffu` → **wrong names** (real: `set_up_fast_frequency_update`, `enable_aggressive_fast_frequency_update`, `clean_up_fast_frequency_update`, waxx/control/raman_beams.py:300-340; kexp/base/base.py:333); other identifiers exist. Title misspelled. Internals tier.
- **Placeholder-objects-and-shared-references (305 lines, 2026-01-05)** — shared-reference rule and `prepare_devices` wiring → correct; "placeholders ... get overwritten when the experiment is prepared" → **imprecise**: the mixin `__init__`s never run at all (see nuances). Internals tier.
- **Composite-system-control-classes (frame parts)** — not re-audited; note the word "composite" now also means the Monitor's Composite tab devices (`kexp/config/composite_devices.py`) — glossary must separate them [I].

### needs_a_human
- Was `force_dds_init=True` (2026-09-22) meant to be permanent? Has phase coherence after a skipped init been checked?
- Which `device_db.py` does `%db%` point to on kong and on each client PC (core_addr .75 in the repo; the hardware_id docstring's example is .86)?
- Is Γ = 6 MHz with the 461.7/2 MHz offset right for the D1 AOM lock chain?
- Does the monitor's full DDS/CPLD/Zotino init at start glitch live outputs?

### proposed_topics
- "Device frames and channel names (dds/dac/ttl)" — experimenter, tier 2.
- "Adding a channel end to end (id file → monitor reconcile → composite)" — maintainer, tier 3.
- "DDS wrapper semantics: set_dds, on/off with v_pd, caching" — experimenter/expert lookup, tier 2.
- "DAC limits: max_v zeroes the channel" — experimenter, tier 1 (safety).
- "DDS fast init and `force_dds_init`" — maintainer, tier 3.
- "TTL inputs, gates and TriggerTimeout" — expert lookup, tier 3.

### question_bank_answers
- **N13** Default camera `camera_select=cameras.xy_basler` (kexp/base/base.py:27); other keys `x_basler`, `z_basler`, `basler_2dmot`, `andor`, `apd` in `kexp/config/camera_id.py:22-62`; pass `Base.__init__(self, camera_select=cameras.andor)` [C].
- **E18** Today every run does the full init (default `force_dds_init=True`, base.py:155, since 2026-09-22); with `force_dds_init=False` intact channels are skipped. Force it after touching Urukul clocking/SYNC or when phase coherence is in doubt (docstring 157-161). The outcome is stored as the `dds_init` JSON attribute of the run's HDF5 via `_extra_file_texts` (ad9910_fast_init.py:55-57,236-245; wtests/test_ad9910_fast_init.py::test_every_run_keeps_its_outcome_with_its_data); `mot_observe.py:34-37` forces it explicitly, the monitor gets it through the default [C].
- **E19** Stale edges left in a TTLInOut FIFO make the next `timestamp_mu` return at once with an old time, parking the cursor in the past → underflow on the next event; `cleanup_scan_kernel_wax` drains every TTLInOut each shot (`ttl.clear_input_events()`, expt.py:211-220; ttl_id.py:40-47), and `arm()` drains before opening a gate (TTL.py:79-90) — since 444a27e, 2026-09-23 [C].
- **E17 (DDS side)** `set_dds_gamma(delta)` takes Γ; `set_dds(frequency=...)` takes Hz; amplitude 0–1; `v_pd` volts [C DDS.py:152-257].
- **Missing questions**: "Why did my coil turn off when I set 7.5 V?" (max_v zeros); "Why does every run print `[dds init] full init on 24 of 24`?"

### bugs_and_footguns
| Where | What happens | Hurts operator |
|---|---|---|
| kexp/base/base.py:155-161 | default `force_dds_init=True` contradicts docstring; fast init never used | medium (1.4 s/run, noise) |
| waxx/control/artiq/DAC_CH.py:29-33 | over-limit value writes 0 V instead of refusing/clamping | high |
| DAC_CH.py:29-36 | cache updated before the write | medium (untrusted aborts) |
| waxx/config/dds_id.py:16-18,169-177 | `make_dds_array` uses waxx module shape 1×4 | low today |
| waxx/config/dac_id.py:24-26,47-53 | placeholder DACs lack `errmessage` → AttributeError on over-limit | low |
| waxx/control/artiq/DDS.py:111-138 | `transition` unused; docstring says MHz, returns Hz | low |
| DAC_CH.py:44-47 | `handle_dac_error` never called (dead code) | low |
| wiki Fast-DDS l.181 | wrong method names | low |

---

## Area 07 — Monitor server and device state

### operator_summary
- Between runs a small ARTIQ experiment, the **monitor** (`kexp/experiments/tools/monitor.py`), holds the core and applies what you set in the **Device Control GUI** (DDS/DAC/TTL tabs, Composite tab) about every 100 ms [C tools/monitor.py:53-71; waxx/base/monitor.py:30,1321-1334].
- The **monitor server** (headless, started by the Server Dashboard on kong) is the go-between: it keeps the **device state file** (`<data>/device_state_config_<hwid>.json`), starts/stops the monitor, and tells GUIs what changed [C waxx/util/guis/monitor_server_gui.py:115-215; kexp/config/ip.py:50-62].
- When you submit a run it takes the core; the monitor stops ("interrupted by run") and the state file is **untrusted** until the run's `end()` (or its abort handler) reports what it left the hardware at [C monitor_server_gui.py:647-673,860-950].
- The server does **not** start the monitor when it starts; you press **Start** in the Device Control status row. After each run the monitor is restarted automatically ("run complete") [C monitor_server_headless.py:94-99; monitor_server_gui.py:1225-1229; expt.py:417-423].
- If the red "Device state untrusted" banner appears, either **Run MOT Observe** (puts the machine in a known MOT state; the inner coil goes ON) or **Trust state…** after you checked the hardware [C device_summary.py:237-264; kexp/experiments/tools/mot_observe.py:1-15].

### mental_model
A hotel front desk (server) with a ledger (state file) and a night porter (monitor) who carries out requests only while no guest (experiment) has the building. When a guest checks in, the ledger is marked "unverified" until the guest checks out and says what they changed. Flow of one edit [C]:
```
GUI edit (Enter/focus-out) -> server: write JSON atomically, version += 1, broadcast
 -> monitor (every 0.1 s): get_version moved? -> read file -> diff -> precompiled per-channel kernel -> hardware
```

### how_to
1. Start everything (kong): Server Dashboard autostarts `monitor` on 192.168.1.76 [C kexp/util/dashboard/dashboard_hosts.py:22-33]; open **Device Control**; if the pill says **Monitor not running** click **Start** (notice) or right-click the pill → *Start monitor experiment* [C device_summary.py:121-170; device_control_gui.py:2043-2060].
2. Change a channel: type the value, press **Enter** (or leave the box); step buttons apply at once; "instant apply" sends as you type [wiki claim, consistent with device_control_gui.py:2615-2618; I].
3. Pulse a TTL: right-click the TTL button → Pulse; on for `TTL_PULSE_HOLD_S = 3 × 0.1 s` after the server acks, off anyway after 2 s without ack [C device_control_gui.py:54-59,1084-1097].
4. Untrusted banner: **Run MOT Observe** (≤180 s, killed after) or **Trust state…** → dialog "Trust the state file" [C state_reset.py:39; device_control_gui.py:2413-2433].
5. Run banner with **Clear fence…**: only if that run is dead (compile error, exception, closed console) [C device_control_gui.py:2520-2540].
6. Monitor server process: its LED and Start/Stop/Restart are on the **Device Control panel header** in the Server Dashboard (2026-09-27, 69509c8); Stop/Restart kill it at once and the new server does **not** start the monitor [C kexp/util/dashboard/server_dashboard_app.py:61-81].
7. After editing an `_id` file: just restart the monitor; it reconciles the state file (area 05 how_to 5).

### reference_facts
| Fact | Value | Where | Label |
|---|---|---|---|
| Monitor states (`ReadyBit`) | READY 0, LOADING 1, NOT_READY 2 | waxx/util/comms_server/comm_server.py:11-14 | C |
| `status_json` keys | `state, state_name, sub_state, reason, since, pid, expt_path` + `composite_ops, trust, run_pending, runner, reset, connections, run_loops` | monitor_server_gui.py:104-114,317-331 | C |
| `sub_state` values | LOADING: `starting`; READY: `running`; NOT_READY: `never_started`, `stopped_on_request`, `interrupted_by_run`, `exited`, `failed`, `preflight_failed` | monitor_server_gui.py:54-61; monitor_manager.py:121-124,187-342 | C |
| Exit classification | output matches "connection closed" signatures → `interrupted_by_run`; exit 0 → `exited`; else `failed` with a diagnosed hint | monitor_manager.py:280-342 | C |
| READY | set on the monitor's `monitor ready` message (sent at `monitor_loop` start, after op registration) | monitor_server_gui.py:1230-1232; monitor.py:321-325,1321-1323 | C |
| Server status tick | 8 Hz; GUIs poll ~1 Hz | monitor_server_gui.py:648,309-311 | C |
| Monitor poll | `T_MONITOR_UPDATE_INTERVAL = 0.1` s; file read only when the server version moved | waxx/base/monitor.py:30,943-1010 | C |
| State file | `<DATA_DIR>/device_state_config_<hwid>.json`; `device_state_config.json` if `db` env var unset/unreadable | kexp/config/ip.py:50-62; hardware_id.py:38-116 | C |
| Writers of the file | server (updates, replace/abort_state, trust metadata); **also** the monitor's `reconcile_state_file` at start (atomic) and `regenerate_device_state_file.bat` (plain overwrite, defaults) | monitor_server_gui.py:115-215; monitor.py:372-405; generate_state_file.py:86-165,279-300; _bat/regenerate_device_state_file.bat | C |
| Run fence | `run_pending` with token from `finish_prepare`; lifted by the run taking the core, its end/abort state, `run_withdrawn` at exit (atexit), **Clear fence…**, or 120 s **while the monitor is READY** | expt.py:201-209; monitor.py:261-303; monitor_server_gui.py:227,502-550,658-665 | C |
| Composite op gate | refused unless READY, op registered with same signature, no fence | monitor_server_gui.py:415-429 | C |
| Op queue | unclaimed ops expire after 3 s (`OP_QUEUE_TTL_S`) | waxx/util/device_state/op_queue.py:41 | C |
| Connections (AWG) | released before the `run_pending` reply, bounded 3.5 s (clients give up at 5 s); busy op waits 0.5 s then agent killed; reopened when the monitor runs | connections.py:55-60; monitor_server_gui.py:510-514,667-669 | C |
| State reset | runs `RESET_STATE_EXPT_PATH` = `tools/mot_observe.py` via `%kpy% & ar`; killed after 180 s | ip.py:65-67; state_reset.py:39 | C |
| Run loop | `RUN_LOOP_EXPTS = {'auto_tof': ('BEC TOF loop', .../auto_tof.py)}`; 2 s gap; latches off on Abort, nonzero exit, incomplete save, core taken, monitor started | ip.py:68-72; run_loop.py:1-30,56 | C |
| Scene/watchdog step timeout | 180 s | op_runner.py:33 | C |
| Hardware id | last octet of `core_addr` from device db at env var `db` → `monitor:<id>` | hardware_id.py:1-19,95-116 | C |
| Pre-run stamp | report stored as HDF5 text `device_state_at_start`; terminal prints only a failed check (hazards/untrusted off since 163c232, 2026-09-27) | kexp/base/base.py:114-138; waxx/util/device_state/run_stamp.py:63-80 | C |

**Trust transitions** (reason text as stored/tooltip) [C monitor_server_gui.py]:
| Event | Trusted? | Reason text (template) | Line |
|---|---|---|---|
| monitor goes NOT_READY `interrupted_by_run` | no | `run 83120 (mot_tof) took the core at 14:02:11 and has not reported its end state` (`an experiment` if unannounced) | 658-663 |
| `replace_state` (normal `end()`) | yes | `end state of run 83120 (mot_tof)` [+ `, the state reset requested by op@host`] | 860-903 |
| `abort_state`, trusted | yes | `state of run 83120 (mot_tof) at its abort (the liveOD Abort button)` | 905-926 |
| `abort_state`, untrusted | no | `run 83120 (mot_tof) aborted (RTIOUnderflow in a shot); the file holds its last commanded state, but a channel write that raised RTIOUnderflow may not have reached the hardware, so that channel can differ` | 920-926; expt.py:354-357 |
| `trust_ack` (Trust state…) | yes | `acknowledged on the Device Control GUI by <hostname>` | 377-380 |
Trust persists in the file metadata `state_trust` across server restarts [C monitor_server_gui.py:205-212,636-644].

### expert_nuances
- **What an abort reports** (scan()'s handlers, since 0bce942 2026-09-26 / 3a25319 2026-09-27): the kernel waits for the timeline, snapshots every channel's kernel-side cached value, and sends `abort_state`; untrusted only if the exception or the abandoned shot was in `WRITE_FAILURES = (RTIOUnderflow, RTIODestinationUnreachable, ValueError)`; TriggerTimeout/RTIOOverflow/Abort button → trusted [C waxx/base/scanner.py:21-25,334-363; expt.py:338-374; wtests/test_abort_state.py::test_a_shot_abandoned_on_a_trigger_timeout_does_not, ::test_an_exception_a_write_can_raise_is_reported_untrusted].
- **Not covered → stays untrusted**: exception before `scan()` (e.g. in `init_kernel`), liveOD reset during the camera wait (`_abort_for_reset` sends no state, scribe.py:269-284), Ctrl+C / killed process [C wtests/test_abort_state.py::test_a_reset_during_the_camera_wait_sends_no_state; I for Ctrl+C: no handler path].
- The snapshot is the **last commanded** value (frame cache), not a measurement; channels a run never wrote are reported at frame defaults [C monitor.py:230-259].
- **"Start writes nothing"** holds for channel values: the monitor seeds its cache from the file and applies nothing on the first read (`No changes detected (initial load.)`) [C monitor.py:569-626,1000-1010]. But its `init_kernel` still runs CPLD init, 0 dB attenuation, Zotino init and (default) the full AD9910 init [C tools/monitor.py:54-64; kexp/base/base.py:155,181-190]; hardware effect [H].
- Plain tab edits (`update`) are **not** gated by monitor state or the run fence (only composite ops are) [C monitor_server_gui.py:771-778 vs 415-429]; see demon 1.
- A server restart starts its version at the current epoch seconds so clients never hold a higher version [C monitor_server_gui.py:214-216].
- Schema drift (JSON has keys the running monitor lacks) → monitor signals end, restart reconciles [C monitor.py:991-1001,372-405].
- Composite-op or compile trouble never kills the monitor: definitions rejected → runs without ops; CompileError → rebuilt without ops [C tools/monitor.py:27-50].
- The Device Control LED/Start/Stop on the dashboard header control the **server process**; the pill/notice in the GUI control the **monitor experiment** — two different things [C server_dashboard_app.py:61-81; device_control_gui.py:2043-2060].
- `Start` warns when the monitor was `interrupted_by_run` or liveOD reports a run in progress: starting takes the core from that run [C device_control_gui.py:2168-2189].

### loud_failures
```
A monitor server for 'monitor:75' is already running at 192.168.1.76:<port>. Refusing to start a second server for the same hardware.
```
waxx/util/guis/monitor_server_headless.py:244-248 (template `'%s' ... %s:%d`). Fix: use the running one; check `%db%` if the id looks wrong.
```
the monitor is not ready (interrupted by run) -- composite ops run only while it is ready
a run is starting (run 83120, mot_tof) -- composite ops are refused until it ends
```
monitor_server_gui.py:419-429 (op refusal, shown on the card).
```
that run is no longer fencing composite ops
```
monitor_server_gui.py:524-526 — stale Clear fence / late withdraw; harmless.
```
Cannot start the monitor experiment:
  - <problem>
Monitor experiment FAILED (exit code 1).
  likely cause: <hint>
Monitor experiment exited on its own with code 0 -- the hardware is no longer being held in the monitor idle state.
Monitor interrupted (exit code 1) -- the core device connection was closed. Expected if an experiment was just submitted.
```
waxx/util/device_state/monitor_manager.py:200-208, 313-318, 305-307, 293-296 (server log; Server Dashboard log dock).
```
[Monitor] WARNING: the monitor server did not accept this run's end state (<msg>); the device state file still describes the hardware as it was BEFORE this run.
[Monitor] WARNING: the monitor server did not accept the aborted run's device state (<msg>) -- the monitor server runs older code; restart it; the device state stays untrusted.
[Monitor] note: could not tell the monitor server this run is starting (server unreachable); composite ops are not fenced for it.
```
waxx/base/monitor.py:196-198, 224-226, 285-286.
```
[Monitor] run 83120 aborted (RTIOUnderflow in a shot): its last commanded device state went to the monitor server, marked UNTRUSTED -- a channel write that raised RTIOUnderflow may not have reached the hardware, so that channel can differ. Check that channel, then Trust state on the Device Control GUI.
[Monitor] run 83120 aborted (the liveOD Abort button): its device state at the abort went to the monitor server (trusted).
[Monitor] WARNING: could not report run 83120's device state at the abort (<exc>); the device state stays untrusted.
```
waxx/base/expt.py:362-370.
```
[Monitor] JSON has new device keys not known to running monitor — DDS: {...}, DAC: {...}, TTL: {...}. Signaling restart — the restart reconciles the state file against the device frames.
[Monitor] ERROR: composite device definitions rejected (<exc>); running without composite ops.
[Monitor] ERROR: the monitor did not compile with its composite ops -- starting it WITHOUT them. Compiler output:
```
monitor.py:995-998; kexp/experiments/tools/monitor.py:31-32,46-47.
```
[device state] *** could not read the device state from the monitor server (<error>); nothing was checked before this run. ***
```
kexp/base/base.py:133-134 + run_stamp.py:69-71 — the only pre-run line still printed.

### demon_candidates
1. **Edits made while the monitor is not running never reach the hardware.** The server writes every `update` regardless of monitor state (monitor_server_gui.py:771-778); at start the monitor takes the file as its baseline and applies nothing (monitor.py:1000-1010). The GUI shows your value; the notice even says "edits are not applied until it is started" (device_summary.py:52), implying they will be. Same for edits during a run: the run's `replace_state` overwrites them (monitor_server_gui.py:874-884). *Best explanation — still needs checking on hardware* (code path confirmed; no GUI-side edit lock found by grep in device_control_gui.py).
2. **Trusted but wrong after "Trust state…" during a run.** `trust_ack` is accepted in any state (monitor_server_gui.py:377-380); a run that then crashes leaves a trusted file. *Inferred.*
3. **`regenerate_device_state_file.bat` while the server runs**: it overwrites the file with frame defaults (non-atomic `json.dump`, generate_state_file.py:279-300) without bumping the server version, so nothing notices; the next edit anywhere bumps the version and the monitor then applies **every** difference — all channels jump to their defaults. *Best explanation — still needs checking.*
4. **Hardware-id fallback is silent.** With env var `db` unset, `get_core_addr` logs at DEBUG and the path falls back to `device_state_config.json` (hardware_id.py:46-49; ip.py:56-62): server and a client with different `db` settings read different files / discover different ids. *Confirmed (code).*
5. **Fence expiry needs READY.** A fence from a run that died without the atexit handler (hard kill) expires after 120 s only if the monitor is READY (monitor_server_gui.py:541-550); if the monitor is also down, the run banner persists until Clear fence… or a monitor start (`monitor ready` clears it, 302-304). *Confirmed.*
6. **Monitor start re-initializes all DDS chips** by the `force_dds_init` default (area 05 demon 1). *Confirmed code; hardware effect [H].*

### symptoms — Device Control GUI (what you see → meaning → what to click)
| What you see (window "Device State Control") | Meaning | Do |
|---|---|---|
| Pill **Monitor server unreachable** (dark red `#7a1616`, device_control_gui.py:38), detail "click the status to retry"; notice (red) `Monitor server unreachable: edits do not reach the hardware` | server process down or not discovered (beacon id `monitor:<hwid>`) | Server Dashboard → Device Control header LED → Start; click the pill to retry [device_control_gui.py:2139-2165] |
| Pill **Monitor not running** (red), detail "never started"; notice (yellow) `Monitor not running: edits are not applied until it is started` + Start | server up, monitor never started (server never autostarts it) | **Start**. Edits made before this are not applied (demon 1) |
| Same, detail "stopped on request" / "exited" / "exit code 1: …" / "not started: …" | stopped by someone / ended itself / crashed / preflight failed | Start; if it fails again read the server log `Monitor experiment FAILED …` |
| Pill **Monitor not running**; notice (blue) `Monitor interrupted: an experiment was likely submitted` | a run holds the core | wait; **Start** asks "An experiment probably holds the core device…" — starting cuts that run off [2168-2189] |
| Pill **Monitor starting…** (yellow) | compiling / init_kernel (LOADING) | wait; composite ops refused meanwhile |
| Pill **Monitor ready** (green) | edits apply within ~0.1 s | — (check the trust banner too: READY does not mean trusted) |
| Red banner `Device state untrusted: the tabs may not match the hardware.` with **Run MOT Observe** / **Trust state…**; hover: `Untrusted since: <reason>` | a run took the core and reported no trusted end state (crash, Ctrl+C, abort on a write failure) | Run MOT Observe (inner coil ON at `i_mot`), or check the hardware and Trust state… [device_summary.py:237-264] |
| Yellow banner `Device state untrusted: running MOT Observe (host, 12 s)…` | reset experiment running | wait ≤180 s |
| Red banner `… Last MOT Observe failed.` | reset failed / timed out | hover for its last output lines |
| Blue banner `Run 83120 (mot_tof) announced itself and has not taken the core yet: composite ops are refused until it does or ends.` + **Clear fence…** | run in prepare/compile | wait; Clear fence only if it died [device_summary.py:266-288] |
| Blue banner `Run 83120 (mot_tof) in progress, shot 3/20 (liveOD). The hardware belongs to it.` | liveOD says a run is going | wait |
| Red `INTERLOCK TRIPPED -- the magnets are disabled. Coil ops cannot drive current until it is reset (Interlock panel).` / yellow `Interlock ok, but the magnets are DISABLED at the relay.` | interlock / relay | Interlock panel [290-301] |
| Blue `Hardware busy for ~N s (a ramp is playing out); ops sent now wait for it.` | long composite op | wait |
| Red watchdog banner `… (Composite tab: Keep on, or turn it off)` | a watchdog will act | Composite tab |
| Hazard chips `MOT: <text> · 5 min` + **Make safe…** | a device reports a hazardous state (e.g. coil at current) | Make safe… sends each card's safe op |
| Op result `expired in the queue -- the monitor never picked it up` | monitor not polling for 3 s | check pill; resend | 

Misleading signals: green "Monitor ready" with a red untrusted banner is normal after a crash; the untrusted state is no longer printed in the run's terminal (only stamped into the file) since 2026-09-27.

### terms_used
- **monitor (experiment)** — the ARTIQ program that holds the hardware between runs and applies GUI edits. `kexp/experiments/tools/monitor.py`.
- **monitor server** — the background process that owns the state file and starts the monitor. `monitor_server_headless`.
- **Device Control GUI** — window "Device State Control", tabs DDS/DAC/TTL/Composite/Sequences.
- **device state file** — JSON with every channel's last value. `device_state_config_75.json`.
- **version** — a counter the server bumps on every change; the monitor re-reads the file only when it moves.
- **trusted / untrusted** — whether the file can be believed to match the hardware.
- **run fence (run_pending)** — a flag that refuses composite ops between a run's `finish_prepare` and its taking the core.
- **token** — a random id naming one fence so a late message cannot lift a newer one.
- **composite device / op / scene / watchdog** — a named group of channels with operations (MOT On/Off); a scripted series of ops; a timer that turns something off. `kexp/config/composite_devices.py` MOT.
- **hazard** — a device state flagged as dangerous to leave (a coil at current).
- **state reset (Run MOT Observe)** — running `mot_observe.py` from the server to set a known state.
- **run loop** — the server running `auto_tof.py` back to back.
- **connection (AWG)** — a device session the server holds between runs and releases for a run.
- **beacon / discovery / hardware id** — UDP announcements by which clients find servers; the id suffix from `core_addr`.
- **atexit handler** — Python code that runs when a process exits normally (not on a hard kill).
- **snapshot kernel** — compiled code copying every channel's cached value to the host at an abort.

### prerequisites
Area 05 frames and caching; ARTIQ "one experiment holds the core at a time"; run lifecycle (`finish_prepare`, `end()`); liveOD Abort; Server Dashboard.

### wiki_audit
**Real-Time-Device-Control-(Monitor) (1021 lines, 2026-09-27)** — checked where in doubt; overall current. Split proposal: *explanation* (Overview, How it works, trust/fence), *how-to* (GUI use, Run MOT Observe, adding a device/op), *reference* (protocol, JSON, constants), *troubleshooting* (→ symptom table above).
- l.325-363 aborted runs → correct (matches scanner.py/expt.py); lists `raise_underflow=True` as a cause → **stale** (ignored since 2026-09-27).
- l.366-401 trust → correct; "the monitor writes nothing to the hardware when it starts" → **half true**: no channel values, but CPLD/AD9910/Zotino init run (tools/monitor.py:54-64).
- l.403-423 fence → correct, incl. "120 s pass with the monitor still ready".
- l.425-436 pre-run check "prints each as `[device state] *** ... ***`" (hazards) → **stale** since 163c232 (2026-09-27): only a failed check prints.
- l.616-633 "When a value is applied" → consistent with code for the path; missing demon 1 caveat.
- l.635-656 GUI layout ASCII "Status: ● READY" → **stale** (pill reads "Monitor ready"; strip, notice, Composite/Sequences tabs).
- l.658-674 TTL pulse → correct (device_control_gui.py:54-59).
- Troubleshooting l.988-1010 → thin; replace with the symptom table.
**Starting-up-the-experiment (2026-07-21)** — Monitor row "real-time device control between shots" → **wrong** (between runs); missing: the server does not start the monitor, the Device Control header LED/Start/Stop/Restart (2026-09-27), autostart list also has `tpi` ("*") [C dashboard_hosts.py:22-33]; "no separate tray launcher" → `_bat/tray_launcher.bat` still exists (legacy) [recon].
**Composite-system-control-classes (2026-07-20)** — describes kexp/control classes; overlaps the Monitor's Composite tab only by name; say so on both pages.
**kexp/util/guis/ethernet_relay/README_GUI.md** — not re-audited in this sweep.

### needs_a_human
- Can a GUI edit made while the monitor is stopped be observed not to reach the hardware (demon 1)? Is that intended?
- Does the monitor's init (CPLD/AD9910/Zotino) glitch live outputs?
- On kong, what is `%db%` and the resulting `monitor:<id>`? Do all client PCs set `db`?
- Lab rule for **Trust state…** vs **Run MOT Observe** (MOT Observe turns the inner coil on).

### proposed_topics
- "Device Control GUI: what the pill, notice and banners mean" (symptom table) — newcomer/experimenter, tier 1.
- "Trusted vs untrusted state, and Run MOT Observe" — newcomer, tier 1.
- "The run fence" — experimenter, tier 2.
- "Monitor server on the dashboard (LED, Start/Stop) vs the monitor experiment" — newcomer, tier 1.
- "State file: location, writers, reconcile, never regenerate while running" — maintainer, tier 3.
- "Monitor protocol and constants" — expert lookup, tier 4.

### question_bank_answers
- **N11** The Monitor is the between-runs ARTIQ experiment; the Device Control GUI edits the server's state file. A click reaches hardware only while the pill says **Monitor ready**: Enter/focus-out → server write + version bump → monitor sees it within ~0.1 s (monitor.py:30,943-1010). While not ready edits are stored but not applied, and are not applied later either (demon 1) [C/I as marked].
- **N12** A run took the core and never reported a trusted end state (crash, Ctrl+C, abort on a write failure, exception before `scan()`); click **Run MOT Observe** for a known state (inner coil ON) or **Trust state…** if you verified the hardware (records your hostname) [C monitor_server_gui.py:658-663; device_summary.py:237-264].
- **N18** Device Control → Composite tab → **MOT** card → **On** (2D/3D beams, push, inner coil at `i_mot`) — needs pill READY and no run fence; or the DDS/TTL tabs; or **Run MOT Observe** [C kexp/config/composite_devices.py:1593-1640; monitor_server_gui.py:415-429].
- **E13** `86` in `monitor:86` is the last octet of `core_addr` in the device db named by env var `db` (plain `monitor` if unresolvable); a second server discovering the same id refuses to start. The repo's db has `192.168.1.75` → `monitor:75` [C hardware_id.py:95-116; monitor_server_headless.py:238-249; device_db.py:3].
- **E14** Untrusted for an underflow because `RTIOUnderflow ∈ WRITE_FAILURES`: `DAC_CH.set` caches before writing and ramps cache after their last point, so the failing channel may differ from its cached value; the liveOD Abort is caught at a shot boundary (no write in flight) and reported trusted [C scanner.py:21-25; expt.py:354-367; DAC_CH.py:29-36].
- **Missing questions**: "The pill is green but my change did nothing — why?" (demon 1 / fence / composite refusal); "What do the dashboard LED and the GUI pill each control?"

### bugs_and_footguns
| Where | What happens | Hurts operator |
|---|---|---|
| monitor_server_gui.py:771-778 + monitor.py:1000-1010 | edits while monitor down/interrupted never applied; GUI text implies later application | high |
| waxx/util/guis/device_summary.py:52 | notice text misleading (see above) | medium |
| generate_state_file.py:279-300 via _bat | regenerate overwrites live file without version bump, non-atomic | medium |
| monitor_server_gui.py:377-380 | Trust state accepted during a run | low |
| hardware_id.py:46-49; ip.py:56-62 | silent fallback to unscoped state file when `db` unset | medium |
| monitor_server_gui.py:541-550 | fence TTL only while READY | low |
| wiki Monitor l.425-436, 635-656; Starting-up Monitor row | stale/wrong as listed | medium |
