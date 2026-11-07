# Using the fastest feedback loop

How to run feedback on the fastest loop, check that it ran, change its spacing, and what is and is not
validated. Written 2026-11-05 20:05; updated 20:40 for the lean posterior and the first-gap stretch (the bench's
configuration on the default loop; branch jep/fastest-lean until it lands in main).
How it was built and measured: [README.md](README.md). Names: standard loop, overlap loop, fastest loop
(never a bare "fast path").

## 1. Getting it: nothing to switch on

Every experiment that inherits `FeedbackExpt` and does not replace its loop runs the fastest loop
(`p.fast_path = 2` is the `ExptParamsFeedback` default). Write the experiment as usual:

```python
from artiq.experiment import *
import numpy as np
from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt

class my_feedback(EnvExperiment, FeedbackExpt):
    def prepare(self):
        FeedbackExpt.__init__(self, save_data=True, save_on_underflow=True)
        self.p.update_raman_frequency_bool = 1          # adaptive drive
        self.xvar('feedback_fractional_initial_offset', np.array([0., 0.5, 1.]))
        self.finish_prepare()                           # the loop and its slack are chosen here

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__))
```

`random_bayesian.py` and `deterministic_bayesian.py` are real examples. The non-adaptive drive
(`update_raman_frequency_bool = 0`, pulse lists) runs on the fastest loop too.

## 2. Check which loop ran

At `finish_prepare` the terminal prints one of:

| Line | Meaning |
| --- | --- |
| `feedback: fastest loop (single-AO moves ..., deadline guard); lean posterior; first gap +5.000 us` | fastest loop, and its posterior and first-gap stretch |
| `!! feedback: the library posterior runs, not the lean one: ...` | the class overrides a helper the lean posterior inlines (section 3) |
| `feedback: slack X us from the measured required slack (was Y us): ...` | spacing picked from the table (section 4) |
| `feedback: slack X us as the experiment set it, ...` / `... as set (p.fastest_slack_auto = 0)` | your slack kept |
| `!! feedback: the standard loop runs, not the fastest loop: <reason>.` | fell back (section 3) |

The run file records what ran. Check these, not the docstring:

- `p.fast_path`: 2 fastest, 1 overlap loop (`FeedbackExptFast`), 0 standard loop or a class with its own loop.
- `p.fastest_slack_auto`: 1 if the table's slack was applied, otherwise 0.
- `p.t_calculation_slack_compensation_mu` and `p.t_between_pulses_mu`: the spacing that ran.
- `p.fastest_posterior`: 1 lean, 0 library (the standard loop records 0).
- `p.fastest_first_gap_extra_mu`: how much longer the first gap (pulse 0 → 1) was, ns. The default (−1,
  auto) gives 5000 when the loop took the table's slack and 0 when the experiment kept its own; a value ≥ 0
  is used as set; the standard loop records 0. Replay (`kexp.analysis.feedback`) rebuilds the stretched gap
  from it. The first gap is `t_between_pulses_mu` + this for the median pulse; `data.t` has every pulse's
  time exactly.

The posterior is the lean one by default (`LeanPosterior`, the bench kernel's numerics): the same model as
`Feedback.generate_posterior`, equal to it to rounding (~1e-12 on the host;
`tests/test_fastest_lean_posterior.py`). Replay and analysis use the library posterior, so a replay of a
fastest-loop run agrees with what ran to rounding, not bit for bit. With `p.fastest_posterior = 0` the fastest
loop runs the library posterior, bit for bit on the host.

## 3. When you do not get it

**Falls back to the standard loop** (prints the `!!` line and the reason). This happens when the class:

- overrides `measurement`, `readout_pulse`, `readout_prepare_sample`, `readout_events`,
  `generate_posterior`, `propagate_hypotheses` or `weigh_hypotheses`;
- scans a parameter the read trace is built from: `t_img_pulse`, the `t_integrator_*` gate and settle
  times, `t_calculation_slack_compensation_mu`, `t_raman_set_pretrigger_mu`, `t_fifo_mu`,
  `t_io_update_pretrigger_mu`, the two FFU pipeline latencies, `N_pulses`, `n_initial_shots_before_remesh`;
- reads the APD on a Sampler channel other than 7;
- scans `frequency_raman_transition` over more than 50 kHz (single-AO moves);
- sets `N_pulses < 1`.

To scan one of those parameters on the fastest loop, run one file per value instead.

**Falls back to the library posterior** (the fastest loop still runs; prints `!! ... the library posterior
runs`): the class overrides `expected_photon_fraction` or `sincos_lut_interp`, which the lean posterior inlines.

**Not touched at all:** any class with its own `feedback_loop`. These keep their own loop and record
`p.fast_path = 0`:
- `feedback_reinit` and the S2 copies;
- adaptive Ramsey, v1–v5;
- the `alias_grid` alt and bimodal classes;
- `FeedbackExptFast`;
- the bench files in this folder.

**Refused before a run id is used** (raises in `prepare`/`finish_prepare`):

- scanning `fast_path`, `fastest_slack_auto`, `fastest_posterior` or `fastest_first_gap_extra_mu`: each is
  chosen once per run;
- `fastest_first_gap_extra_mu` negative or not a multiple of 8 ns: `ValueError`;
- `feedback_grid_size > 21` with the slack left to the table: `SlackUntested`. Nothing above 21 is
  measured; run the slack ladder first (section 4), or set your own slack, accepting the risk;
- a fixed gap too short for the chained read: `ValueError`.

**Ends a shot on the machine:**
- the deadline guard: `RTIOUnderflow("fastest loop deadline guard ...")` when a frequency word would have
  less than 1 µs of lead;
- a DDS staging/write order error: `ValueError`.

After an underflow, the next run often fails with AUX_DAC errors (memory: underflow aftereffects).

## 4. Spacing

Slack sets the spacing: median T ≈ slack + 27.06 µs. Since 2026-11-05 the fastest loop sets
`t_calculation_slack_compensation_mu = fastest_timing.required_slack_mu(p)` from the grid size. At the defaults
(lean posterior; first gap +5 µs, which auto mode applies whenever the table's slack is used) the loop runs as
the bench kernel did, so the slack is the bench's rule pass
(the floor + 3.0 µs) plus 0.5 µs for the deadline guard. Each setting off its default adds its cost back: the
library posterior +6.1 µs at m = 21; a first-gap stretch shorter than 5 µs, the shortfall on every gap. A read
longer than the bench's adds its difference:

| m (`feedback_grid_size`) | slack (µs) | median T (µs) |
| --- | --- | --- |
| 5 | −5.464 | ~21.6 |
| 11 | −4.416 | ~22.6 |
| 21 | −1.000 | ~26.1 (slack ladder 2026-11-05; was −0.416, ~26.6; library posterior: 5.69, ~32.7; no first-gap stretch: 4.00, ~31.1; the standard loop: 39.70, ~66.7) |
| 31 | 4.000 | ~31.1 (slack ladder 2026-11-05; lean only) |
| 51 | 17.000 | ~44.1 (slack ladder 2026-11-05; lean only; 13 µs failed 1 in 12 shots, so the margin is the 3 µs alone) |
| other > 21 | refused until measured | |

These are bench-derived estimates (the bench floors were 23.15, 19.2, 18.1 µs at m = 21, 11, 5; the defaults
add 3.5 µs). The default loop at these spacings has not run on the machine. The slack test at m = 21 on the
default loop measures its own floor.

- **Your own spacing:** set `self.p.t_calculation_slack_compensation_mu = int64(ns)` in `prepare()`.
  Any value other than the params default is kept. `fastest_timing.slack_mu_for(T_us)` converts a median T
  to an aligned slack.
- **The old spacing on the fastest loop:** `self.p.fastest_slack_auto = 0`. This keeps 39.70 µs of slack,
  T ≈ 66.7 µs, and (auto) no first-gap stretch, so the timeline is the one tonight's calibrations ran.
- **Same schedule is not same arithmetic.** A run that keeps its own slack (`fastest_slack_auto = 0` or its own `t_calculation_slack_compensation_mu`) keeps its RTIO schedule (no stretch, the same chain and gaps) but NOT its posterior arithmetic: the lean posterior is the default for it too, equal to the library's to rounding. A copy that must match earlier library-posterior runs bit for bit sets `p.fastest_posterior = 0`.
- **A ladder rung or any run with its own slack that should time the default configuration:** also set
  `self.p.fastest_first_gap_extra_mu = 5000` (auto gives 0 with your own slack).
- **A grid above 21, or a measured floor at any m:** use the slack ladder. Make one copy of
  `slack_ladder_rung.py` per rung in the run folder and set `GRID_SIZE`, `SLACK_US`, `N_SHOTS`. Then enter
  the floor in `fastest_timing.MEASURED_SLACK_FLOOR_US`, keyed `(m, "lean")` or `(m, "library")`, with the
  first-gap stretch the ladder ran. From then on that m and posterior use floor + 3.0 µs.
  The procedure is in README.md, "Slack test". In short: start at `fastest_timing.ladder_start_us(p, m)`
  (7 µs at m = 31, 0 µs at m = 21, at the defaults) and step down 1 µs per rung, 20 shots + 3 warm-ups, on atoms, until a rung underflows.
  The floor is the lowest clean rung; confirm it with 100 shots. Underflows are expected and fine, and so is
  an `AD9910 AUX_DAC mismatch` at init on the run after one (user, 2026-11-05). That run took no shots:
  submit it again and continue. Then read both core logs and check that the TOF loop has not latched.
- **Organizer rule:** a feedback run with a grid above 21 needs that grid's slack test first. Without it the
  default loop refuses the run before a run id is used (`SlackUntested`).

## 5. Comparing with the standard loop

Use `self.p.fast_path = 0` in a separate file and interleave the runs. `fast_path` cannot be scanned. At
equal slack and with `self.p.fastest_first_gap_extra_mu = 0` in the fastest file (the standard loop's gaps are
uniform), the two loops play the same RTIO events (host test, either posterior), apart from:
- the read starts 0–15 ns later;
- the moving AO's frequency word can differ by 1 LSB.

The standard loop always uses its own slack, 39.70 µs, and ignores the table. Comparing at different slack
also changes T, which is a physics change as well as a code change. To compare the code alone, set the same
slack in both files.

## 6. What is validated, and what to do around a run

**On atoms (2026-11-04, at the old spacing T ≈ 66.7 µs):** identity gates against the standard loop.
- On resonance: fastest 92141 and 92146 against standard 92144 and 92145.
- Across the span: fastest 92148 and 92151 against standard 92149 and 92150.

Both comparisons were consistent: χ² 14.7 and 14.6 on 11 dof. Model sensitivity was 2.4–2.6 % in rate,
so no separate single-AO Rabi check was needed then.

**Not done** (check `kq list` and the memory for anything newer):

- No run at the 11-05 spacing (T ≈ 26.6 µs at m = 21, or the first version's ≈ 37.8 µs), none with the lean
  posterior or the first-gap stretch on the default loop.
- A replay of a real fastest-loop run through the library posterior, to check the compiled lean posterior
  (fast-math may round differently from the host).
- The read model, APD levels (`v_apd_all_up/down`), contrast and photon numbers were all calibrated at
  T ≈ 66.7 µs. At the new T the integrator clear and the read history differ. Before trusting feedback
  data at the new T, recalibrate at that T, or run with `fastest_slack_auto = 0`.
- `t_integrator_settle = 2 µs` is the feedback default since 11-04. Some older APD endpoints were measured
  at 4 µs. Use values calibrated at the settle you run.

**Every run:**
- Use ≥ 3 warm-ups and `save_on_underflow=True`.
- After the run, read both core logs, the master's and the satellite's (`artiq_coremgmt -s 1 log`). A late
  word at the satellite does not raise an error; it shows only in that log.
- Read the "complete, N shots" line as the planned count, not the stored count.
- After an underflow, the next run often fails at init with `AD9910 AUX_DAC mismatch` (3 of 3 on 11-01;
  the run after that one worked every time). It takes no shots: submit it again. Inside a slack ladder,
  underflows are the expected result (README.md "Slack test").

## 7. Changing the code

The loop is `fastest_loop.py`: `FastestLoop`, `LeanPosterior` (the default posterior) and `OverlapPosterior`
(the library posterior split in two halves). `base_expt_feedback.py` hands control to it in `__init__`,
`finish_prepare`, `scan_kernel` and both cleanups. Spacing is in `fastest_timing.py`. The rules:

- Any edit to `Feedback.generate_posterior` must be mirrored by hand in `OverlapPosterior` (bit for bit) and in
  `LeanPosterior` (the same model).
- After any edit, run (serially; nothing reading B:, not in the first minute after a run's INIT_RUN):
  `.venv/Scripts/python -m pytest k-exp/tests/test_fastest_lean_posterior.py k-exp/tests/test_fastpath_posterior.py k-exp/tests/test_fastest_timing.py k-exp/tests/test_fastest_first_gap.py k-exp/tests/test_fastest_rtio_stream.py k-exp/tests/test_fastpath_rtio_stream.py k-exp/tests/test_fastest_default.py -q -p no:cacheprovider`
  (about 2 minutes; the last file compiles kernels).
  - Known failures on main as of 11-05, not from this loop: `test_adaptive_ramsey.py::test_phase_sign_check_prefers_the_sign_the_data_were_made_with`
    and `test_readcoh_posterior.py::test_off_is_bit_for_bit_the_kernel_on_main`.
  - The two `test_fastest_rtio_stream` cases reported failing earlier on 11-05 (slack 39696, offset .316) pass
    again at 20:30 on main and on the branch; what changed in between was not found.
  - `test_abort_state_compiles` fails only after the other compile tests (`KeyError 'slm_at_start'`), the
    same on unmodified main.
- Kernel changes: compile offline (`test_fastest_default.py` does) before the first run.
- The host harness cannot see CPU time, so test any timing change on the machine (section 4).
