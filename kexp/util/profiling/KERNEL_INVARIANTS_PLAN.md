# Plan: `kernel_invariants` across the device-control classes

Status: **plan only — nothing declared yet.** Written 2026-09-18 from a read-only
review of every attribute write in `kexp` (incl. all ~470 experiment files),
`waxx` and `waxa`. Line numbers are as of that date.

No compiler change is involved. `kernel_invariants` is a plain class attribute
on *our* classes; ARTIQ's own drivers (`ad9910.py`, `urukul.py`, `ttl.py`) all
use it already.

## What it buys (be honest about the size)

- **No writeback** for the attribute at kernel exit. Today every
  (object x kernel-referenced attribute) is one `setattr` RPC at the end of each
  kernel: roughly 24 DDS x ~15 attrs + DAC/TTL channels + ~200 on the control
  objects and the experiment object.
- **Load hoisting** in hot loops (`PaintedBeam._ramp_*` 1000 steps, feedback
  posterior loops). The value is *not* frozen across runs: every `ar` run
  recompiles and picks up current host values.
- It is **not** a large compile-time win. The compile-time lever is the ~270
  generated param writers in `Scanner.generate_assignment_kernels`. Measure with
  `startup_timer.py` before and after each stage; drop a stage that shows nothing.

## ARTIQ rules that decide everything (verified in `artiq/compiler`)

1. A kernel/portable/`kernel_from_string` **assignment** to an invariant attribute
   is a hard compile error (`validators/constness.py:44-52`). Loud = good.
2. **Element** writes to an invariant array (`self.arr[i] = x`) are legal by the
   validator (`constness.py:26-30`) but suppress the array's writeback.
   *Not yet proven by compiling on this codebase* -> arrays are a separate, last stage.
3. The set is read off the **instance** by normal attribute lookup
   (`embedding.py:522,570`). A subclass that declares its own set **replaces**
   the parent's. Always write `kernel_invariants = Parent.kernel_invariants | {...}`.
4. Declared-but-missing attribute: warning if never used in a kernel, hard error
   if used (that error exists regardless of invariants).
5. Same class, different attribute *types* across instances (None vs object) is a
   hard error as soon as a kernel touches it. The `ch=-1` dummy `DAC_CH` in
   `DDS.py:64-69` / `dds_id.py:122-132` exists for this. Keep it.
6. `@portable` helpers count as kernel code when called from a kernel.

## Never invariant

| Attribute(s) | Why |
|---|---|
| **anything on `ExptParams`** | `scanner.py:422` generates `self.params.<key> = value` for every int/float/ndarray attr; bools/lists flip type under `xvar()`; ~23 params are assigned directly in experiment kernels (`p.t_tof` in 7 files, ...); `vars(self.params)` is archived post-run via writeback (`expt.py:350`) |
| `DDS.frequency, amplitude, v_pd, sw_state` | kernel-written; read post-run by `generate_state_file.py:79-85` (Monitor state) |
| `DDS._frequency_default, _amplitude_default, dac_control_bool` | written by `@portable` `_stash_defaults/_restore_defaults/update_dac_bool`, all reached from kernels (`base.py:149,196`) |
| `DDS._ftw, _asf, _pow, _last_ftw, _last_v_pd, phase_mode, phase_offset, t_phase_origin_mu, _phase_t_last_set, _t_last_set_mu, _t_last_change_mu, _t_io_update_delay_mu` | kernel-written (`DDS.py`, `raman_beams.py:420-425,470-471`) |
| `DAC_CH.v` | kernel-written, also from outside: `painted_lightsheet.py:80`, `awg_tweezer.py:172,174`; read post-run |
| `DAC_CH.errmessage` | does not exist on placeholder / dummy channels |
| `TTL_OUT.state`, `TTL_IN.t_input_gate_end` | kernel-written; `state` read post-run |
| `Sampler_CH.gain`, `Shuttler_CH._ch_relay_state`, `Grabber._roi_counter/_gate_on` | kernel-written |
| `DataContainer.shot_data` | **rebound in a kernel** at `experiments/test/sampler_data_saver_test.py:41` |
| `igbt_magnet.i_supply, i_pid, pid_on` | kernel-written (`big_coil.py:81-303`) |
| `TweezerTrap.position, frequency, amplitude, dummy_out` | kernel-written |
| `TweezerTrap.values` (1e6 floats) | not kernel-referenced today; **never reference it from a kernel** (8 MB per trap embedded). Add a source comment. |
| `tweezer.traps` | rebound by an RPC mid-kernel (`spectrum_DDS_tweezer.py:654`) |
| `RydbergBeamBase._used`; `ttl_shutter` on the *base* class | kernel-written; `ttl_shutter` is None on the 980 beam (rule 5) |
| `BeatLockImagingPID._fit_a/_b/_c/_rms/_shots`, `BeatLockImaging.phase_mode` | kernel-written |
| `RamanBeamPair`: 24 state attrs (`frequency_transition`, `_fast_freq_*`, `_phi*_mu`, ...) | kernel-written |
| `xvar.counter`, `counter.img_idx/light_img_idx` | kernel-written |
| on the experiment: `_setup_awg` (`base.py:135`), `_imaging_conditions_recorded`, `_dummy_array` (`scanner.py`, the `N, self._dummy_array = self.fetch_array(idx)` rebind) | kernel-written |
| `camera_params.exposure_time` | kernel-written in `experiments/test/hf_image_test.py:44` |
| `Feedback.Omega, omega_z_lightshift` | kernel-written in subclasses (`base_expt_feedback.py:124,179`) |
| array attrs shared host-side (`Sampler_CH.samples`/`sampler_frame.data`, `_relay_state`, `Grabber.data/timestamps`) | changes host-visible data flow silently; leave alone |

## Stages (each = one commit, one timed test run, revert on any doubt)

### Stage 0 — tooling and baseline (no code change)
- Record baseline with `startup_timer.py --timing-json` on the smoke set (below).
- One run with `"report_invariants": True` in the device_db `core` arguments
  (a device_db argument, not a compiler edit): the compiler prints the attributes
  it saw never written. Use as a cross-check of the sets below; it only covers the
  experiment compiled, so it cannot replace the tables.

### Stage 1 — leaf wrappers (`waxx/control/artiq/`) — biggest pool, errors are loud
```python
DDS:         {"urukul_idx", "ch", "aom_order", "double_pass",
              "dds_device", "cpld_device", "dac_ch_obj", "dac_ch"}
             # dac_ch: its only kernel write was the unused non-PID BeatLockImaging.init
             # (beat_lock.py:63), commented out 2026-09-18. BeatLockImagingPID.init
             # overrides it and never called it. If the non-PID lock is ever revived
             # with that line, dac_ch must come back out of this set.
             # dac_control_bool stays OUT: update_dac_bool() still writes it from set_dds.
DAC_CH:      {"ch", "dac_device", "max_v"}
TTL:         {"ch", "ttl_device"}          # TTL_OUT / TTL_IN / DummyTTL inherit, add nothing
Sampler_CH:  {"ch", "sampler_device"}      # Sampler_Last_CH inherits
Shuttler_CH: {"ch", "shuttler_idx", "_dc", "_dds", "_relay", "_trigger", "_STATE_BASE"}
Grabber:     grabber_artiq.kernel_invariants | {"_channel_base", "_sentinel", "grabber_device"}
             # today's bare set silently drops the parent's (rule 3)
```

### Stage 2 — frames (`waxx/config/*_id.py` + kexp subclasses, always with `|`)
```python
dds_frame (waxx):  {"_dac_frame", "dds_array", "dds_list"}
dds_frame (kexp):  parent | {<the 22 named DDS channels>}
dac_frame:         {"dac_device", "dac_ch_list"}      kexp: parent | {<named DAC channels>}
ttl_frame:         {"camera"}                         kexp: parent | {<named TTLs>}
sampler_frame:     {"sampler_device", "gains"}        # NOT "data"
shuttler_frame:    {"_STATE_BASE", "_config", "_trigger", "_relay"}   # NOT "_relay_state"
DataVault (waxx):  {"_expt", "_list_1d_f64", "_list_2d_f64", "_list_1d_i32",
                    "_list_2d_i32", "_list_1d_i64", "_list_2d_i64"}
DataContainer:     {"_is_sentinel"}                   # subclasses inherit
```
Generate the named-channel sets from the assignment calls rather than typing them,
so a newly added channel cannot be forgotten or misspelt.

### Stage 3 — control classes, scalars and object refs only
```python
igbt_magnet:   {"v_control_dac","i_control_dac","pid_dac","pid_ttl","igbt_ttl","ttl_blanking",
                "params","max_voltage","slope_current_per_vdac_supply",
                "offset_current_per_vdac_supply","slope_current_per_vdac_pid",
                "offset_current_per_vdac_pid"}        # hbridge_magnet inherits, declares nothing
lightsheet:    {"pid_dac","ttl_sw","pid_int_zero_ttl","alignment_shim_dac","params",
                "paint_amp_dac","v_paint_min","core"}
tweezer:       {"ao1_dds","ao2_dds","pid1_dac","pid2_dac","sw_ttl","pid1_int_hold_zero",
                "pid2_enable_ttl","params","paint_amp_dac","v_paint_min","core","awg_trg_ttl"}
TweezerTrap:   {"mesh","cateye","awg_trig_ttl","p","core"}
RamanBeamPair: existing | {"dds0","dds1","dds_sw","p","params","_amp_to_asf","_turns_to_pow",
                "_f_to_ftw","_amplitude_0","_amplitude_1","_frequency_center_0",
                "_frequency_center_1","_frequency_ratio","_frequency_diff_sign"}
BeatLockImaging:    {"dds_sw","dds_beatref","ttl_pid_manual_override","params","p"}
BeatLockImagingPID: BeatLockImaging.kernel_invariants | {"dds_pid","dac_pid",
                "ttl_pid_int_clear","integrator","sampler","_core"}
RydbergBeamBase:    {"siglent","dac_pid","ttl_pid_clear","_eo_shift_direction",
                "_cavity_ao_frequency","_cavity_ao_order","_wavemeter","_lock_dc",
                "_siglent_freq_dc","_core"}
RydbergDDSSwitchBeam: base | {"dds_sw","ttl_shutter"}
RydbergTTLSwitchBeam: base | {"ttl_sw"}
doubled_rf: {"dds","params"}     Integrator: {"ttl_integrate","ttl_reset","sampler_ch"}
SLM: {"core"}    SDG6000X_CH: {"core"}    RunInfo: {"imaging_type"}    xvar: {"position"}
CameraParams (base): {"amp_imaging","exposure_delay","key","optical_path_key",
                "t_camera_trigger","t_dark_image_delay","t_light_only_image_delay"}
```
Prerequisite fix before `_N_beatref_mult/_beat_sign/_frequency_minimum_beat` could
ever be added: `beat_lock.py:50-56` only assigns them when the argument is the
sentinel (passed values are dropped and the attribute never exists).

### Stage 4 — the experiment object (`Base`) — needs a design decision first
~33 safe names (`core, params, p, data, dds, ttl, dac, sampler, shuttler, slm, camera,
camera_params, run_info, _counter, scope_data, magnetometer, imaging, integrator, tweezer,
lightsheet, inner_coil, outer_coil, raman, raman_nf, ry_405, ry_980, rf, setup_camera,
_ridstr, xvarnames, scan_xvars, _param_keylist_*, _xvar_writer_*`).

Hazard: `class FeedbackExpt(Base, Feedback, ...)` — a set on `Base` comes first in
the MRO and **silently replaces `Feedback.kernel_invariants`** (`feedback.py:14`).
Options: (a) merge in `Base.__init_subclass__` by unioning every base's set;
(b) skip this stage. Also: experiments reassign `self.p`, `self.data` in `prepare()`
(host, pre-compile — fine), but any experiment that assigns one of these names
inside a kernel would break; none found in the scan.

### Stage 5 — arrays (only after a bench test of rule 2)
Compile a throwaway experiment that element-writes an invariant ndarray and reads
it back, to prove rule 2 on this ARTIQ build. Only then consider
`RamanBeamPair._dummy/_frequency_array/t_timeline/t_rtio`,
`BeatLockImagingPID._probe_v_pd/_probe_rate`, the `Feedback` scratch arrays.
`shot_data`, `samples`, `_relay_state`, `Grabber.data/timestamps` stay out regardless.

## Smoke set (run after every stage, all via `startup_timer.py`)
| Experiment | Exercises |
|---|---|
| `experiments/default_experiments/mot_tof.py` | plain path; also assigns `p.v_zshim_current` in a kernel |
| one under `HF_experiments/feedback/` | `Feedback` set + MRO shadowing (Stage 4) |
| one under `JP/monitored_rabi/` | `RamanBeamPair` fast-frequency writes to DDS internals |
| `experiments/test/sampler_data_saver_test.py` | `shot_data` kernel rebind |
| a tweezer run and a lightsheet-ramp run | `DAC_CH.v` written from `_ramp_end` |
| `experiments/tools/monitor.py` | Monitor's generated kernels call `set_dds/set_sw/set_state/set` |
| any run to completion | Monitor state JSON still shows the right post-run frequency/amplitude/v_pd/sw_state/TTL state/DAC v |

Pass = compiles with no new warnings, state JSON identical to a pre-change run of
the same experiment, atoms as before.

## Pre-existing bugs found on the way (not part of this plan; report only)
- `TweezerTrap.cubic_move/sine_move/linear_amplitude_ramp`: an RPC computes
  `_value_final` on the host, then the kernel immediately reads its own stale copy
  (`spectrum_DDS_tweezer.py:237-238, 372-374, 403-405`).
- `Scanner.generate_assignment_kernels` gives list/bool params no writer:
  scanning `frequency_tweezer_list` / `amp_tweezer_list` would update the host only.
- `ttl_frame.populate_ttl_list` (`ttl_id.py:32-42`) reuses the previous loop value
  for an unknown device class.
- `fzw_frame.add_wavemeter` returns `Wavemeter` or `DummyWavemeterClient` — a rule-5
  type split if `ry_405/ry_980` wavemeters are ever touched from a kernel.
- `experiments/JP/monitored_rabi/calibrations/find_io_update_delay_raman.py:103`
  assigns `dds._last_frequency`, which does not exist on `DDS` (cannot compile today).
- `DAC_CH.max_voltage_error()` raises AttributeError on channels without `errmessage`.
