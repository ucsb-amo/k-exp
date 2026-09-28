# HANDOFF — k-exp wiki rebuild (for the next session)

Written 2026-09-28 by the editor-in-chief session (Claude, Fable 5.1). The requesting session ran
out of cloud usage after Phase 1 started and asked for the work to be handed to another session.
Everything needed to continue is in this folder (`docs/wiki-rebuild/`) and in `docs/wiki/`, on the
k-exp branch `claude/determined-ptolemy-qdteku`. Nothing lives only in the old session's scratchpad.

Read in this order: `PROMPT.md` (the full task spec, verbatim) → this file → `phase0_recon.md` →
`question_banks.md` → the reports in `reports/` → `drafts/`.

## 1. Where things stand

| Phase | State | Output |
|---|---|---|
| 0 Recon | **done** | `phase0_recon.md` (page inventory, staleness ranking, code map, tests, design docs, footguns), `question_banks.md` (20 newcomer + 20 expert questions with expected answers and code pointers) |
| 1 Research fan-out | **partly done** | `reports/NN_<area>.md` for every agent that finished (see §3). Two consolidation agents were launched at the end of the session to sweep the areas whose agents had not finished; their outputs, if they landed, are `reports/CONSOLIDATED_A.md` and `reports/CONSOLIDATED_B.md` (see §4) |
| 2 Master inventory | not started | to write: `wiki_inventory.md`, merged glossary (`drafts/glossary.md`), concept map |
| 3 Structure plan + 2 reviewers | not started | to write: `wiki_ia_plan.md`; a provisional sketch is `drafts/ia_plan_provisional.md` |
| 4 Writing + edit passes | not started | pages go to `docs/wiki/<Page-Name>.md` |
| 5 Verification | not started | `wiki_eval.md` |
| 6 Delivery | scaffolding only | `docs/wiki/README.md`, `docs/wiki/sync_wiki.sh`, `docs/wiki/sync_wiki.ps1` exist and are tested for syntax only |

## 2. Decisions already made (do not re-litigate; the reasons are here)

1. **Delivery target.** The wiki repo (`ucsb-amo/k-exp.wiki.git`) clones but cannot be pushed from a
   Claude cloud session: the git proxy only injects credentials for repos in the session's source set,
   and GitHub wikis are not attachable with `add_repo`. Per the spec's fallback, the deliverable is
   `docs/wiki/` on the k-exp branch plus the one-command sync scripts. A lab member runs
   `bash docs/wiki/sync_wiki.sh` from a PC that can push to k-exp to publish.
2. **Editor-in-chief must be Fable.** If the resuming session is not Fable, run the editor steps
   (Phase 2, Phase 3, integration, edit passes, sign-off) as `Agent` calls with `model: "fable"` and
   pass them `PROMPT.md`, this file and every report in full. Fan-out agents use `model: "opus"`.
3. **Workflow concurrency.** The cloud container has 4 CPUs, so the `Workflow` tool caps each
   workflow at 2 concurrent agents. Agents are API-bound, not CPU-bound, so the fan-out was split into
   8 workflows of ≤2 agents each (one workflow per pair) to run all 15 at once. Do the same for the
   writers and checkers: several small workflows, or `Agent` calls with `run_in_background: true`.
4. **Research split.** 15 briefs in `briefs/01..15_*.md` with a shared preamble `briefs/00_shared.md`
   (rules, evidence labels, the 15-section report format). The briefs refer to the old scratchpad path
   `/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad`; `bootstrap_resume.sh`
   recreates that layout in the new session's scratchpad (or rewrite the path with `sed`).
5. **Glossary groups 1–4** (code ideas, working with code, networks, ARTIQ) are drafted by the
   editor in `drafts/glossary_groups_1_4.md`, with the worked example taken from
   `kexp/experiments/default_experiments/mot_tof.py` (`self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)`).
   Groups 5–6 come from the reports' `terms_used` sections.
6. **Provisional structure** (`drafts/ia_plan_provisional.md`): Home with five doors and three paths;
   8 sidebar groups; the big merges/splits (Monitor page → how-to + internals + composite tab; LiveOD →
   how-to + internals; Scan-loop → how-to + internals; terminology + unit conventions → glossary; stubs
   for every old name). It was written before the reports and must be revised against them.

## 3. The 15 research areas and their reports

| # | Area | Brief | Report status at handoff |
|---|---|---|---|
| 01 | Startup, PCs, network | `briefs/01_startup_pcs.md` | written (319 lines) |
| 02 | Package layering and code map | `briefs/02_layering_codemap.md` | agent was writing when stopped — see §4 |
| 03 | Experiment lifecycle | `briefs/03_lifecycle.md` | written |
| 04 | Scanning and parameters | `briefs/04_scanning_params.md` | see §4 |
| 05 | Device layer | `briefs/05_device_layer.md` | see §4 |
| 06 | Hardware drivers | `briefs/06_hardware_drivers.md` | written (191 lines) |
| 07 | Monitor and device state | `briefs/07_monitor_device_state.md` | see §4 |
| 08 | Cameras and LiveOD | `briefs/08_cameras_liveod.md` | written (317 lines) |
| 09 | Data pipeline | `briefs/09_data_pipeline.md` | written (267 lines) |
| 10 | Analysis | `briefs/10_analysis.md` | written (258 lines) |
| 11 | GUIs, dashboards, telemetry | `briefs/11_guis_dashboards.md` | written (289 lines) |
| 12 | Calibrations and feedback | `briefs/12_calibrations_feedback.md` | written (224 lines) |
| 13 | Experiments catalog | `briefs/13_experiments_catalog.md` | see §4 |
| 14 | Loud failures / Error Message Index | `briefs/14_loud_failures.md` | see §4 |
| 15 | Demon hunter and wiki auditor | `briefs/15_demons_audit.md` | see §4 |

`ls reports/` is the authority: any `NN_*.md` present was written by its agent in full. The
per-agent transcripts of the stopped agents are not in the repo (they were in the old session's
`~/.claude` directory), so an area with no report must be re-researched from its brief.

## 4. The two consolidation agents (final sweep)

At the end of the session all remaining workflows were stopped and two Opus agents were launched
with `briefs/consolidation_A.md` and `briefs/consolidation_B.md`. Each covers half of the areas
whose report was missing at that moment, at reduced depth (the brief says which), and writes ONE
report `reports/CONSOLIDATED_A.md` / `reports/CONSOLIDATED_B.md` in the standard 15-section format
with per-area subsections. They were told to `git add`, commit and push their own report to this
branch when done (pull --rebase first). If a consolidated report is missing, that agent did not
finish: re-run its brief.

## 5. How to resume (step by step)

1. Start a session with the k-exp and wax repos, on branch `claude/determined-ptolemy-qdteku`
   (k-exp) and `main` (wax; the branch of the same name in wax carries no changes). Confirm the code
   SHAs the research was done against: k-exp `c8faf77` (2026-09-27), wax `acc4621` (2026-09-27). If
   either repo has moved, `git log c8faf77..HEAD` and re-check the touched areas.
2. Run `bash docs/wiki-rebuild/bootstrap_resume.sh` — it clones the wiki into the scratchpad,
   copies this folder there under the path the briefs use, and prints the paths.
3. Read `PROMPT.md`, this file, `phase0_recon.md`, `question_banks.md`, then every file in
   `reports/` in full (the spec requires the editor to read every report in full, not summaries).
4. If any area of §3 still has no report, run its brief with an Opus agent (one workflow per pair).
5. Phase 2: write `wiki_inventory.md` (topic | audience | tier | evidence | status | target page),
   merge every report's `terms_used` into `drafts/glossary.md` (groups 5–6 onto groups 1–4), merge
   every `prerequisites` into the concept map.
6. Phase 3: write `wiki_ia_plan.md` starting from `drafts/ia_plan_provisional.md`; run the two
   reviewers (`briefs/reviewer_newcomer.md`, `briefs/reviewer_veteran.md`) against the plan; revise.
7. Phase 4: assign disjoint page sets to Opus writers with `briefs/writer_shared.md` + a per-writer
   assignment file; writers write into `docs/wiki/`; the editor writes `Home`, `_Sidebar`,
   `Words-You'll-See`, `Troubleshooting`, `Error-Message-Index`, `Demons`, `Where-Does-X-Live`
   from the writers' submissions; edit pass on every page.
8. Phase 5: run the checkers (`briefs/checker_*.md`); fix; repeat; record in `wiki_eval.md`.
9. Phase 6: commit `docs/wiki/` in logical commits; push; publish the final report artifact
   (contents listed at the end of `PROMPT.md`). No pull request unless asked.

## 6. Findings worth carrying forward (from Phase 0; the reports have many more)

- `kexp/_bat/fix_run_id.bat` runs `waxa/data/increment_run_id.py`, which does not exist in wax.
  The "FIx Run ID" Start-menu shortcut is therefore dead. (footgun, high)
- `Expt.finish_prepare_wax` (waxx/base/expt.py ~l.183): with `setup_camera=False`, `save_data=True`
  and no liveOD, the run proceeds after a WARNING and saves nothing; run id stays 0. (demon candidate)
- `Scanner.generate_assignment_kernels` gives list/bool params no kernel writer: scanning a list
  param updates the host only (KERNEL_INVARIANTS_PLAN.md "pre-existing bugs"). (footgun, high)
- `Scanner.adjust` on an existing xvar key warns and skips; `xvar` on an adjust key raises.
- KERNEL_INVARIANTS_PLAN.md lists five more pre-existing bugs (TweezerTrap stale `_value_final`,
  `ttl_frame.populate_ttl_list`, fzw_frame type split, `find_io_update_delay_raman.py:103`,
  `DAC_CH.max_voltage_error`).
- The Scan-loop and DataVault pages describe `shuffle='axis'` and `run_info/shot_order`; check
  against `waxa/base/dealer.py` (report 04/09) before trusting either page.
- Staleness ranking (highest first): Starting-up-the-experiment, Code-architecture,
  Base-experiment-parent-class, Scan-loop, Quick-Start, Composite-system-control-classes,
  Adding-new-hardware, Device-configuration-reference/_DDS-Objects/Device-Frames,
  Placeholder-objects, Saving-and-loading-data. Climate page is an orphan (not in the sidebar).
- Only one in-code link points at the wiki: `k-exp/README.md:4` (wiki root). All cross-page links
  inside the wiki use absolute `https://github.com/ucsb-amo/k-exp/wiki/<Page>` URLs or bare page
  names; every old page name needs a redirect stub.

## 7. File map of this folder

- `PROMPT.md` — the task, verbatim, plus the wind-down instruction.
- `HANDOFF.md` — this file.
- `phase0_recon.md`, `question_banks.md` — Phase 0 outputs.
- `briefs/` — `00_shared.md` + 15 research briefs; `consolidation_A/B.md`; `writer_shared.md`;
  `reviewer_newcomer.md`, `reviewer_veteran.md`; `checker_facts.md`, `checker_links.md`,
  `checker_plain.md`, `checker_expert.md`, `checker_qbank_answerer.md`, `checker_qbank_grader.md`.
- `reports/` — research reports (15-section format).
- `drafts/glossary_groups_1_4.md`, `drafts/ia_plan_provisional.md`.
- `bootstrap_resume.sh` — recreates the scratchpad layout for a new session.
- `../wiki/` — the deliverable folder: `README.md`, `sync_wiki.sh`, `sync_wiki.ps1` (pages to come).

## 8. Conventions the next editor should keep

- Page files are GitHub-wiki named (`Title-With-Dashes.md`); `Words-You'll-See.md` keeps the apostrophe.
- Footer on every page: `Last verified against code: <date> · k-exp <sha> · wax <sha>`.
- Evidence labels: confirmed / inferred / needs a human. Only the first two reach the wiki.
- Commit messages: no model identifiers; end with the attribution lines the harness gives.
