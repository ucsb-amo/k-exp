# k-exp/docs/opx -- the ARTIQ <-> OPX+ integration write-up

A pedagogical LaTeX document describing how the K-machine codebase drives
the Quantum Machines OPX+ alongside ARTIQ: the wiring and truth table, the
`OPXManager` lifecycle, how xvars become per-shot OPX values, how the QUA
program is built, the handoff/hand-back timing (with the real numbers), the
data path into the run file, mid-loop parameter changes, a tutorial for
writing a new per-shot sequence, the mapping onto QUAM, and the on-OPX
Bayesian feedback port (with its timing, numerics, speed work and the
planned remesh).

**Status:** written 2026-09-24 against the phase-2 rebuild design spec and
synchronised with the code after every rebuild agent had landed (framework,
config/components, feedback port); section 10 (feedback) and the appendix
updated 2026-09-25 to the feedback port's speed pass "3b". Everything it
describes is offline-tested only (126 unit tests across six OPX test files;
the feedback port compiled and timed on the QOP simulator); hardware
milestones M1-M4 are open (M4, a Ramsey phase scan, only for the remesh).
One subsection is a design, not code, and is marked **[planned]**: the
remesh with pole return (section 10, from `remesh_plan.md`).

## Build

Requires a TeX distribution with `latexmk`, `pdflatex`, and the packages
`amsmath amssymb geometry booktabs listings xcolor tikz enumitem hyperref`
(all in TeX Live / MiKTeX by default). No TeX toolchain was installed on the
machine where this was written, so the sources have been checked by script
only (`check_tex.py` in the phase-2 scratchpad: environment and brace
balance, label/reference consistency, input targets; plus a byte scan for
ASCII-only content), not compiled.

```
cd k-exp/docs/opx
latexmk -pdf opx_architecture.tex
```

or `make` (see the Makefile; `make clean` removes the build products).

## Files

| file | contents |
|---|---|
| `opx_architecture.tex` | main file: preamble, macros, status box, `\input`s |
| `sections/01_two_controllers.tex` | why two controllers; the three wires; truth table; sticky elements; why the drives are latched and the switch AOM gated; why `prep_raman` stays |
| `sections/02_manager.tex` | `OPXManager` lifecycle (`use` -> `on_finish_prepare` -> per shot -> `finish`), sequence diagram, `OPXBench` |
| `sections/03_xvars.tex` | xvar declaration, repeats, per-axis shuffle, the scan loop, `build_shot_tables`, `ParamRef`, materialisation, the offline order-equivalence check (verbatim), shot arrays / host data |
| `sections/04_program.tex` | trace-once model, the emitted statement skeleton, aligns, elements, units, config-time vs shot-time parameters and the guard, the op log |
| `sections/05_handoff.tex` | timing diagrams (post-rebuild, and the 00e-era customer script), the ARTIQ event list, waste/risk table, the M1 list, crash/abort end states, `TriggerTimeout` |
| `sections/06_data.tex` | DataVault shapes, streams -> `fill_containers` -> unshuffle, `opx_data_valid`, the shot-index echo, container kinds, timestamps, the run-file attributes and how to read them |
| `sections/07_midloop.tex` | reassign vs index, the Adjust-panel guard, what is not protected, proposed guards |
| `sections/08_tutorial.tex` | writing a sequence: ctx macro -> QUA table (incl. `set_frequency(which=)`, `transition_offset_terms`, `min_cc`), per-shot arrays and loops, saving, timestamps, phase reset, transition offset, exact integer IFs, `ctx.qua` rules, simulation, common errors |
| `sections/09_quam.tex` | our components vs QUAM's, what was borrowed, what was kept, why `quam` is not a dependency |
| `sections/10_feedback.tex` | the feedback port: physics, the reset phase model and the 0.478 turns/cycle consequence, the per-step schedule with a timing diagram of one cycle, the exact applied frequency, the fixed-point algorithm (axis tables, co-rotating frame, L/32 weights, sine table, argmax law, discrete durations), the speed work (statement costs, per-pulse compute, what did not work incl. the multi-core probe), data saved and how to read it, the replay class, calibrations to redo, tests, side findings, the planned remesh with pole return, open questions |
| `sections/11_appendix.tex` | glossary, M1-M4 checklist, file map (incl. the reports) |
| `Makefile` | `make` / `make clean` |

## Sources

The design spec and the phase-1 audit reports (`ours_audit.md`,
`artiq_handshake.md`, `customer_handoff.md`, `data_plumbing.md`,
`qua_capabilities.md`, `quam_docs.md`, `feedback_spec.md`, `lead_notes.md`)
and the 2026-09-25 speed studies (`speed_brainstorm.md`, `opx_parallelism.md`
and their scripts) live in the session scratchpad, not in the repo; the code
the text cites is named by path throughout (the module docstring of
`kexp/experiments/opx_sequences/feedback.py` carries the statement list, the
numerics and the simulator tables), and the wiki page
`k-exp.wiki/OPX-integration---Quantum-Machines-OPX+.md` is the short-form
reference.

## Reports (Markdown)

- `opx_assessment_2026-09-24.md` -- QUAM assessment and what was borrowed, the
  ARTIQ<->OPX handoff timing as coded (customer scripts and the framework),
  the waste/risk findings with confidence labels, and what the rebuild changed.
- `feedback_port_report.md` -- the Bayesian-feedback port in short form: reset
  phase model and its timing consequence, the exact applied frequency, the
  fixed-point numerics, compute speed, data saved, replay class, placeholder
  calibrations and hardware prerequisites.
- `remesh_plan.md` (2026-09-25) -- the design of a remesh with pole return for
  the reset model: why the ARTIQ remesh cannot be ported, the corrective
  rotation from the posterior-mean Bloch vector, the trigger, the branch-free
  OPX realisation, phase bookkeeping, data, parameters, sign conventions (M4),
  risks. Plan only; presented in section 10 of the LaTeX document.
