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
| 1 Research fan-out | **done** (9 full reports + 2 consolidated reports covering the other 6 areas at reduced depth) | `reports/01,02,03,06,08,09,10,11,12_*.md`; `reports/CONSOLIDATED_A.md` (areas 04, 05, 07; 646 lines); `reports/CONSOLIDATED_B.md` (areas 13, 14, 15; 932 lines, incl. a 136-row Error Message Index) |
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
| 02 | Package layering and code map | `briefs/02_layering_codemap.md` | written |
| 03 | Experiment lifecycle | `briefs/03_lifecycle.md` | written |
| 04 | Scanning and parameters | `briefs/04_scanning_params.md` | covered in `reports/CONSOLIDATED_A.md` or `_B.md` (§4); transcript extract in `salvage/` |
| 05 | Device layer | `briefs/05_device_layer.md` | covered in `reports/CONSOLIDATED_A.md` or `_B.md` (§4); transcript extract in `salvage/` |
| 06 | Hardware drivers | `briefs/06_hardware_drivers.md` | written (191 lines) |
| 07 | Monitor and device state | `briefs/07_monitor_device_state.md` | covered in `reports/CONSOLIDATED_A.md` or `_B.md` (§4); transcript extract in `salvage/` |
| 08 | Cameras and LiveOD | `briefs/08_cameras_liveod.md` | written (317 lines) |
| 09 | Data pipeline | `briefs/09_data_pipeline.md` | written (267 lines) |
| 10 | Analysis | `briefs/10_analysis.md` | written (258 lines) |
| 11 | GUIs, dashboards, telemetry | `briefs/11_guis_dashboards.md` | written (289 lines) |
| 12 | Calibrations and feedback | `briefs/12_calibrations_feedback.md` | written (224 lines) |
| 13 | Experiments catalog | `briefs/13_experiments_catalog.md` | covered in `reports/CONSOLIDATED_A.md` or `_B.md` (§4); transcript extract in `salvage/` |
| 14 | Loud failures / Error Message Index | `briefs/14_loud_failures.md` | covered in `reports/CONSOLIDATED_A.md` or `_B.md` (§4); transcript extract in `salvage/` |
| 15 | Demon hunter and wiki auditor | `briefs/15_demons_audit.md` | covered in `reports/CONSOLIDATED_A.md` or `_B.md` (§4); transcript extract in `salvage/` |

`ls reports/` is the authority: any `NN_*.md` present was written by its agent in full. The
per-agent transcripts of the stopped agents are not in the repo (they were in the old session's
`~/.claude` directory), so an area with no report must be re-researched from its brief.

## 4. The two consolidation agents (final sweep) — both finished

`reports/CONSOLIDATED_A.md` (commit b5eab98) covers areas 04, 05, 07; `reports/CONSOLIDATED_B.md`
(commit 6cb9ca0) covers 14, 15, 13. Both use the 15-section format per area. Their headline findings
and the CORRECTIONS they make to Phase 0 (take these over `phase0_recon.md` / `question_banks.md`):

- **Shuffle.** `shuffle='axis'` and `run_info/shot_order` exist nowhere in wax: there is only a
  per-axis shuffle, and liveOD unshuffles (sorts) params, images and DataVault data at END_RUN. The
  Scan-loop and DataVault pages are wrong on this, and question E4's expected answer ("not unshuffled")
  is wrong for the saved file. (A, area 04)
- **`force_dds_init` has defaulted to True since 2026-09-22** (68d8dcb8); docstrings still say the
  fast skip is the default. Question E18's hint needs this. (A, area 05)
- **`max_v` is not a clamp**: a DAC value above `max_v` writes 0 V. (A, area 05; B demon list)
- The `populate_ttl_list` bug in the recon was fixed 2026-09-23 (444a27e). The DDS `transition`
  setting is stored but never used. (A)
- **Monitor:** edits made while the monitor is stopped or a run holds the core are stored in the
  state file but never applied afterwards, although the GUI's notice says they will be; and
  `regenerate_device_state_file.bat` run while the server is up overwrites the file without the
  server noticing. Both need checking on hardware. (A, area 07)
- **liveOD raise-vs-warn** is decided by the internal `setup_camera` (frames captured), not
  `save_data`: an APD run with liveOD down only warns, saves nothing, and prints
  "setup_camera=False" although the user passed True. (B, area 14; refines E1)
- `CAMERA_OPEN_TIMEOUT` is never read (a camera that cannot open is retried forever). An error in
  the cleanup after an underflow can hide the underflow. (B)
- SLM: the 2026-09-26 reply-when-applied protocol exists but experiments never request a reply, so
  saved SLM values are still the request; the hourly SLM re-initialisation blanks the pattern
  mid-run. Data files are named after the experiment *class*, so `mot_tof.py` saves
  `..._gm_tof.hdf5`; `mot_tof.py` sets detunings on `self` instead of `self.p`. (B, area 15)
- Recon correction: the Scan-loop page says nothing about `raise_underflow`; its errors are the
  shuffle claims above. Two page names contain U+2010 hyphens; 31 absolute wiki URLs; a broken
  `Compiler-Quirks` link; the Climate page is the only orphan. (B)
- OPX: only the ARTIQ-side handshake and `qm/` experiments are on main; the OPX program code is on
  the unmerged `jep/opx-integration` branch, and `expt_params` and seqview point at modules not on
  main. `ExptBuilder` is copied into ~10 files and writes `kexp/experiments/ml_expt.py`. (B, area 13)
- The exact ARTIQ RTIO error texts still need a human (ARTIQ is not installed in the cloud container).

Read both consolidated reports in full before Phase 2, like the others.

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
- `salvage/` — transcript extracts of the six stopped research agents (areas 04, 05, 07, 13, 14, 15).
- `bootstrap_resume.sh` — recreates the scratchpad layout for a new session.
- `../wiki/` — the deliverable folder: `README.md`, `sync_wiki.sh`, `sync_wiki.ps1` (pages to come).

## 8. Conventions the next editor should keep

- Page files are GitHub-wiki named (`Title-With-Dashes.md`); `Words-You'll-See.md` keeps the apostrophe.
- Footer on every page: `Last verified against code: <date> · k-exp <sha> · wax <sha>`.
- Evidence labels: confirmed / inferred / needs a human. Only the first two reach the wiki.
- Commit messages: no model identifiers; end with the attribution lines the harness gives.

## 9. Post-handoff notices (2026-10-10)

### 9a. The code has moved since the research was done
The reports describe k-exp `c8faf77` and wax `acc4621` (both 2026-09-27). On 2026-10-10 `origin/main` is
k-exp `534d4b02` (+63 commits; most-touched: kexp/experiments (77 files); kexp/util (46 files); kexp/config (10 files); kexp/base (7 files); kexp/control (6 files); kexp/calibrations (6 files); kexp/analysis (4 files); kexp/_bat (3 files);) and wax `09f4221` (+85 commits, incl. the
`jep/calibration-writeback` merge: calibration emit, ledger and parameter write-back; most-touched:
waxx-src/waxx/util/live_od (22 files); waxx-src/waxx/util/guis (17 files); waxx-src/waxx/util/dashboard (12 files); waxx-src/waxx/control/slm (7 files); waxx-src/waxx/util/device_state (6 files); waxx-src/waxx/control/cameras (6 files); waxx-src/waxx/util/supervise.py (1 files); waxx-src/waxx/util/profiling (1 files);). Before Phase 2, run `git log --stat c8faf77..origin/main` in k-exp and
`acc4621..origin/main` in wax and re-check every report section that cites a touched file. The
calibration write-back merge in wax touches area 12 (calibrations) and probably 04 (parameters).

### 9b. Run queue briefing (reported by a manager session on kong; NOT yet verifiable from GitHub)
A coordinating Claude session on kong ("code-14") reported on 2026-10-10 that a **run queue** went live
on 2026-10-09 (wax `f7c8b31`, k-exp `01827174`, `code` repo `b3a5443`). As of this notice neither SHA is
on any branch of `ucsb-amo/k-exp` or `ucsb-amo/wax` on GitHub, and no fetched branch holds the files it
names, so treat every line below as **reported, unverified** until those commits are pushed. Its stated
sources of truth: `k-exp/kexp/_bat/shortcuts/README.md` (line 3 said to be stale and being fixed) and
`.claude/skills/run-experiment/SKILL.md` §4. Reported facts:
- The monitor server hosts a run queue; the Server Dashboard has a "Queue | State | Monitor" panel.
- `ar x.py` now means `kq run x.py`: the run is queued as a person's job unless `WAXX_OWNER=agent`.
  `ar_direct` / `artiq_run --device-db %db%` run directly, outside the queue. The agents' `run_lock.py`
  rewrites a leading `ar` to the full `artiq_run.exe` path so agent runs stay direct.
- `kq` commands: run, submit, list, show, tail, cancel, pause/resume, hold/release, insert/move/edit,
  status. Exit codes 0 / N / 1 / 2 / 3 / 4 / 6 / 130. Person jobs go ahead of agent jobs. An agent's
  TOF-loop start must send owner=agent.
- The file that runs is kong's copy, hashed at submit and at launch; paths must be under `%code%` or
  `C:\lab\skynet_log`; no stdin. `kq cancel` = liveOD Abort, which discards a running job's file. A
  person's liveOD Reset creates a person hold.

**What this makes stale in this folder** (fix in Phase 2/3 once the code is on GitHub):
- `question_banks.md` N3 ("`ar` = ARTIQ's artiq_run via the shortcut") and the expected answers of N4,
  N10 (abort now also via `kq cancel`), N18/E-items that mention `ar mot_observe.py`.
- `drafts/glossary_groups_1_4.md`, group 2, the `ar`, `art` entry; add `kq`, run queue, job, owner,
  hold, direct run.
- `phase0_recon.md` code map line for `_bat/shortcuts` (ar.lnk, art.bat) and the footgun list.
- `reports/01_startup_pcs.md` (launchers, cheat sheet), `03_lifecycle.md` ("from `ar file.py` to the
  saved file"), `CONSOLIDATED_B.md` area 13 (how operators run experiments), `CONSOLIDATED_A.md` area 07
  (the Server Dashboard panels; abort/reset semantics); any "ar = artiq_run alias" sentence anywhere.
- `drafts/ia_plan_provisional.md`: "Running-a-Standard-Experiment" and the operator cheat sheet need a
  queue section; Troubleshooting needs the `kq` exit codes; the Monitor pages need the queue panel.
- The old wiki pages Starting-up-the-experiment and Quick-Start say `ar`/artiq_run with no queue.
