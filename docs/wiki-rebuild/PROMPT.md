# Original task specification (verbatim, from the requesting session, 2026-09-28)

Use a workflow for this task. I'm explicitly opting into multi-agent orchestration.

# Who is in charge

A **Fable agent is the editor-in-chief** of this project and makes every decision that needs judgment. The editor-in-chief:
- runs recon (Phase 0)
- decides how the research is split up
- reads every research report in full
- owns the master inventory (Phase 2) and the structure plan (Phase 3)
- is the only one who edits the pages everything else hangs off (Phase 4)
- edits every page after its writer finishes, for clarity, ordering and consistent voice
- decides what to do with every verification finding
- signs off on delivery

**Opus subagents** do the research (up to 15), the writing, and the checking. They report to the editor-in-chief and don't make structural decisions.

If this session isn't running on Fable, the editor-in-chief steps must be agent calls with `model: "fable"`: Phase 0 synthesis, Phase 2, Phase 3, integration, the edit passes, and final sign-off. Every fan-out agent uses `model: "opus"`. Pass the editor-in-chief this whole prompt and every report in full, not summaries.

# Mission

Rebuild the k-exp wiki (https://github.com/ucsb-amo/k-exp.wiki.git, branch `master`) into a reference that works for **two readers at once**:

- **The newcomer**: a grad student or postdoc who knows AMO physics but not our code, and may know little programming. They need to run the machine (start it up, run standard sequences, take and view data, recover, shut down), and later to extend it, without being overwhelmed.
- **The experienced user in trouble**: someone who knows the system but has hit an odd, subtle or intermittent problem, and needs the exact nuance of *our* implementation fast. They'll arrive by pasting an error message, a class name, a config key or a symptom. They don't want a tutorial. They want the mechanism, the edge case, and the file and line.

Neither reader is secondary. A page that only serves newcomers is too shallow, and a page that only serves experts is too dense. Every page serves both through **layering** (see Page anatomy).

The wiki covers all three packages: `kexp` (in `ucsb-amo/k-exp`), and `waxx` and `waxa` (in `ucsb-amo/wax`). `wax` has no wiki of its own. The wiki must describe the code **as it is today** on the default branches. When the wiki and the code disagree, the code wins.

## How we'll know it worked (acceptance tests)

Before any writing, the editor-in-chief writes **two question banks** based on the code, the tests, commit history and the existing pages.

- **Newcomer bank (20 questions)**: running the machine, first experiments, finding things, and basic recovery. For example: "How do I start everything after a power cut?" and "What's the difference between a run and a shot?"
- **Expert bank (20 questions)**: nuanced, specific and tied to our implementation. For example: a verbatim error line with "why does this happen only on the second scan point?", "which setting wins if X is set in both `expt_params` and the experiment?", "what does the saved data record for the SLM: the pattern that was requested or the one that was applied?", and "why would LiveOD show images but no OD?"

The work is done only when all of these hold:
1. A fresh agent that has read only the wiki answers every question correctly.
2. A separate agent checks each answer against the code.
3. Newcomer answers are reachable within **2 clicks from Home**.
4. Expert answers are reachable within **1 step from their natural entry point**: search, the Error Message Index, the code map, or the Glossary.

Record the results in `wiki_eval.md`.

## Writing rules (every writer, enforced by the editor-in-chief and a checker)

**Clear language**
- Use plain English, short sentences, active voice, one idea per paragraph.
- Name exact things: the window title, the button label, the file path, the host PC.
- Don't write "simply", "just", "obviously" or "easy". Don't use vague words like "stuff", "handle" or "deal with" where a precise verb exists.
- Say what to do before explaining why, then explain why, because the *why* is what lets experts reason about edge cases.

**No jargon unless it's defined**
- Every technical term is either defined in the sentence where it first appears on that page, or links to its entry in **Words You'll See**, the new glossary page described below. This applies to basic programming words too.
- Spell out every acronym on first use on each page, for example "digital-to-analog converter (DAC)".

**Symptom descriptions**
- Describe a symptom from where the user is standing: which window or screen they're looking at, the **exact text they see, quoted in a code block** (so Ctrl-F and GitHub wiki search find it), what they expected to happen, and what did *not* happen.
- Write "The LiveOD window shows images but the OD panel stays blank", not "OD computation fails".
- Include the misleading signals too: log lines that look like success, and GUIs that look healthy.

**Ordering and grouping**
- Group topics by **what the reader is doing** (starting up, running, looking at data, fixing things), not by which package the code lives in. Package boundaries belong on the code map and maintainer pages.
- Follow the machine's own flow wherever it applies: power and PCs → servers and GUIs → devices → experiment → cameras → saved data → analysis.
- Introduce a concept before it is used, both within a page and along each reading path. The editor-in-chief builds a **concept map** in Phase 3 (which concept needs which concepts first) and orders pages and sections so the reading paths never jump ahead. If a forward reference can't be avoided, give a one-line definition in place and link ahead.

**Evidence**
- Every factual claim traces to `repo/path/file.py:line`, a class or function name, a test, or a commit SHA. Label each claim **confirmed** (code or test shows it), **inferred** (strongly implied, stated as such), or **needs a human** (physical or lab procedure, or lab lore). Only confirmed claims and clearly marked inferred claims go in the wiki. "Needs a human" items go on a list for me.

**Preservation**
- Correct material that is too deep for the main path moves to a page's Nuances or Internals section, or to `Miscellaneous-Archaeology`. It is never deleted. Wrong material gets corrected. Obsolete material goes to Archaeology with a note on when and why it became obsolete.
- Renamed or merged pages keep a one-line redirect stub. Grep both repos for `k-exp/wiki/` links and keep every one of them valid.

**Other rules**
- No code changes. This is docs only. Report bugs and footguns you find; don't fix them.
- **Style anchor**: the recently rewritten pages (`Demons`, `LiveOD---Camera-acquisition-and-previewer`, `PC-Setup`, `Real-Time-Device-Control-(Monitor)`; check `git log` for others) set the voice: concrete, second person, exact names, and they explain mechanisms. Match that voice.
- Keep the definitions in `Standard-terminology` and `Unit-conventions-and-parameter-naming` and fold them into the new glossary without contradicting them.

## Page anatomy (layering for both readers)

Every concept or subsystem page follows this order. The editor-in-chief can adapt the headings but not the order.

1. **Page type**, stated in the first line: tutorial, how-to, reference, explanation, or troubleshooting.
2. **In short**: 2–4 plain sentences on what this is, when you'd care, and what to do. A newcomer who stops here is still correct.
3. **The idea**: the mental model, with an everyday comparison and a mermaid diagram if one helps.
4. **Doing it**: the common case, as numbered steps with exact commands, GUIs and paths.
5. **Nuances and edge cases**: dense material for experts, such as order of operations, precedence and overrides, defaults, units, timing, what gets saved versus what gets applied, and interactions with other subsystems. Each item carries a code pointer.
6. **When it goes wrong**: loud errors on this topic (exact text → cause → fix) and "⚠ Known demon" callouts linking to Demons.
7. **Internals and code pointers**: a table of the key files, classes, methods and config keys, with one line each.
8. Footer: `Last verified against code: <date> · k-exp <sha> · wax <sha>`

## "Words You'll See": the glossary (a main deliverable)

This is one page, `Words-You'll-See`, linked from Home and from every first use of a term. It absorbs `Standard-terminology`, leaving a redirect stub. The entries are grouped, and the groups are ordered so that each one builds only on the groups before it:

1. **Basic code ideas** (assume no programming background): file, folder/path, program, process, script, module, package, import, variable, value, type, list, dictionary, function, argument (and keyword argument, and default value), return value, class, object/instance, attribute, method, `self`, constructor (`__init__`), inheritance/parent class/mixin, decorator, exception and traceback, thread, log, and anything else the writers find they need.
2. **Working with the code**: repository, branch, commit, pull, editable install, environment variable, config file, terminal/command line, `.bat` script.
3. **Networks and servers**: IP address, port, host, server/client, "the server is up", firewall, Remote Desktop and how it differs from sitting at the PC.
4. **ARTIQ and real-time control**: core device, kernel vs. host code, compile, RTIO, the timeline, slack, underflow and collision, dataset, the master and the dashboard, TTL, DDS, DAC, sampler, shuttler.
5. **Our system's terms**: `kexp`/`waxx`/`waxa`, Base, experiment, run, shot, run ID, xvar, scan, `expt_params`, device frames, composite devices, Monitor, LiveOD, DataVault, `atomdata`, demon, and so on.
6. **Lab and physics shorthand**: MOT, ODT, OD, tweezer, SLM, imaging types, and the unit conventions.

Every entry contains:
- a **plain definition** of one or two sentences, with no undefined words
- an **everyday comparison** where one helps (for example, "a class is a blueprint; an object is one thing built from it")
- **how it looks in our code**, as a real short snippet or name from the repos, such as `expt.dds.imaging.set(...)`: "`expt` is an object, `dds` is one of its attributes, `set` is a method, and the value in parentheses is an argument"
- links to where it matters

The basic code ideas group opens with a short worked example: take one real line from a standard experiment and label every part of it. A newcomer should be able to read that section once and follow any code snippet in the wiki.

# Phase 0: Recon (editor-in-chief)

1. Clone the wiki to the scratchpad and test whether you can push, with a no-op dry run. If you can't push, the deliverable becomes `docs/wiki/` on this session's k-exp `claude/...` branch, plus a one-command sync script.
2. **Inventory the current pages**: for each page, record its title, audience, line count, last-commit date, the code paths and symbols it names, and whether the sidebar links to it.
3. **Map the code**, with one line per module on what it does:
   - `k-exp/kexp/{base,config,control,calibrations,analysis,experiments,util,_bat}`
   - `wax/waxx-src/waxx/{base,config,control,util}`
   - `wax/waxa-src/waxa/{base,data,analysis,fitting,image_processing,plotting,browser,climate,calibrations,helper,config,dummy}`
   Also read the in-repo design docs (`waxx/util/live_od/MIGRATION_PLAN.md`, `kexp/util/profiling/KERNEL_INVARIANTS_PLAN.md`, `kexp/util/guis/ethernet_relay/README_GUI.md`) and both `tests/` directories. The tests are strong evidence of real behavior.
4. **Find where the wiki is probably stale**: for each page, compare its last edit against `git log` for the code it describes, and rank the audit priorities.
5. Write both question banks.
6. Finalize the research split (the suggestions are below) and give every agent the Phase 0 outputs.

# Phase 1: Research fan-out (up to 15 Opus subagents, in parallel)

Suggested split. The editor-in-chief re-cuts it to match the code.

1. **Startup and PCs**: `_bat/` launchers, `bootstrap_pc.ps1`, auto-launch and tray scripts, startup order, env vars (`WAXA_DATA_UNC`, drive remapping), `config/ip.py`, network and firewall. Cover cold start and "after a power cut".
2. **Package layering and the code map**: what goes in `kexp`, `waxx` or `waxa`, and why; dependency direction; editable installs; a "where does X live?" table keyed by what people search for.
3. **The experiment lifecycle**: `waxx/base/expt.py`, `kexp/base/base.py`, the Base mixins (`cooling`, `image`, `control`, `devices`, `cameras`, `clients`, `adjust`, `feedback`); submit → build/prepare → kernel → data saved; host vs. kernel code; ARTIQ compile and runtime errors.
4. **Scanning and parameters**: `waxx/base/scanner.py`, `waxa/base/xvar.py`, `config/expt_params.py`, the scan loop, multi-dimensional scans, shuffling, which setting wins (precedence), and which parameter does what.
5. **The device layer**: `config/*_id.py`, device frames, DDS calibration, `ad9910_fast_init` and FFU, composite devices, and adding hardware from start to finish.
6. **Hardware control drivers**: `kexp/control` and `waxx/control`, including tweezer AWG, SLM (server and client), Rydberg lasers, big coil, Raman, beat lock, painted beams and light sheet, quarto, serial, ethernet relay, and doubled RF. For each: what it physically controls, protocol/host/port, what healthy looks like, and how it fails.
7. **Monitor and real-time device state**: `waxx/base/monitor.py`, `util/device_state`, abort and reset, dashboard monitor controls, Run MOT Observe, `link_latch`.
8. **Cameras and LiveOD**: acquisition, the previewer and exactly where its migration stands, run integrity, the camera host, the Basler GUI, camera IDs.
9. **The data pipeline**: DataVault, `waxa/base/{scribe,dealer}.py`, `waxa/data/*`, run IDs (including `fix_run_id.bat`), the data directory, what is inside a data file, and requested versus applied values.
10. **Analysis**: `load_atomdata`, OD and auto ROI, fitting, `slice_atomdata`, plotting, cross-section calibration, `waxa/analysis/*`, `kexp/analysis/*`. Include a worked example from run ID to fitted plot.
11. **GUIs, dashboards and telemetry**: every GUI in `kexp/util/guis/` and `waxx/util/guis/`, the data browser, the dashboard and viewer registry, seqview, notifications, telemetry, climate/Zabbix. Produce a table of purpose, launcher, host and what healthy looks like.
12. **Calibrations and feedback**: `kexp/calibrations` (including the SLM spot finder run gate), feedback loops, M-LOOP. Cover what drifts, how you'd notice, and when and how to recalibrate.
13. **Experiments catalog**: `kexp/experiments/` classified as canonical, personal or in progress, or legacy. Cover the roughly 10 experiments operators really run and what each is for, plus the `qm`/OPX status.
14. **Loud failures**: exceptions, timeouts, interlocks, RTIO underflow and collision, kernel invariants and profiling. Compile an **exact error text → cause → fix** list for the Error Message Index.
15. **Demon hunter and wiki auditor**: quiet failures (see Demons below), plus a claim-by-claim audit of every existing page (correct, stale, wrong or unverifiable, with evidence), duplication, orphan pages and broken links.

**Report format for every Phase 1 subagent** (include it in each subagent's prompt):
- `operator_summary`: 3–6 plain sentences for a newcomer.
- `mental_model`: an everyday comparison, plus an optional mermaid diagram.
- `how_to`: numbered procedures with exact commands, GUIs, hosts and paths.
- `reference_facts`: keys, defaults, units, symbols and locations, each with a citation and a confidence label.
- `expert_nuances`: precedence, ordering, timing, defaults, silent overrides, requested versus applied values, interactions with other subsystems, and the *why* where the code or history shows it. Aim for what a veteran would want at 2 a.m.
- `loud_failures`: verbatim error text → cause → fix.
- `demon_candidates`: quiet or misleading failures, each with its evidence.
- `symptoms`: every symptom above, rewritten from the user's point of view (where they look and what they see, verbatim).
- `terms_used`: every jargon term this area needs, with a draft plain-language definition and our-code example, for the glossary.
- `prerequisites`: the concepts a reader must know before this area makes sense, for the concept map.
- `wiki_audit`: which current pages cover this area, and what in them is correct, stale, wrong or missing.
- `needs_a_human`: questions the code can't answer.
- `proposed_topics`: candidate topics, each tagged with an audience (newcomer / experimenter / maintainer / expert lookup) and a tier (1 = must know to run the machine, 2 = needed to write experiments, 3 = look up when needed, 4 = internals and archaeology).

# Demons and Troubleshooting (main deliverables)

- **Troubleshooting** covers *loud* failures: the message tells you something is wrong. It is organized by symptom, grouped in machine-flow order.
- **Error Message Index**: one page listing verbatim error and log strings, alphabetized by their first distinctive words, each linking to its fix. This is the expert's main entry point.
- **Demons** covers *quiet or misleading* failures: the system says nothing, or says something reassuring and false. The rule for deciding: if the message tells you what's wrong, it's Troubleshooting; if the system misleads you or stays silent, it's a Demon.

**Hunting for demons.** Agent 15 leads this, and every agent contributes candidates.
- **Code patterns**:
  - `try/except` blocks that swallow or only print the error
  - fallbacks to default, simulation or dummy modes (`waxa/dummy` included)
  - commands sent with no acknowledgement
  - threads that can die while the main loop keeps running
  - success messages printed unconditionally
  - stale caches
  - silent config overrides
  - device IDs or hosts that can drift from reality
  - clock, timezone and run-ID edge cases
  - saved metadata that records what was requested rather than what was applied
- **History**: commit messages and diffs mentioning fix, workaround, hack, silently, actually, wasn't, race, stale, hang, or restart; code comments with `HACK`, `XXX`, `NOTE`, `workaround`, `don't`, or `must`; regression tests (each usually exists because something broke).
- **Existing pages**: gotchas buried in other pages.

**Demon entry format**. Match the existing page exactly:
- a heading that states the symptom as the user would describe it
- the date first seen, from the evidence
- a confidence line: *seen and confirmed*, or *best explanation — still needs checking*
- **What you see**: where the user is looking, the verbatim text (including the misleading lines), and what didn't happen
- **What is going on**: the mechanism, in plain words, with code pointers
- **Why it matters**: which data or state is untrustworthy, and for which runs
- **What to do**: confirm it, fix it, prevent it

Keep the existing SLM/Remote Desktop entry. Add only entries with evidence; plausible but unproven ones go on the needs-a-human list. Past about 12 entries, group them by subsystem with a symptom index at the top. Every demon gets a "⚠ Known demon" callout on its subsystem page and a line in Troubleshooting.

# Phase 2: Master inventory (editor-in-chief)

Merge every report into a single deduplicated list of **everything that should probably be on the wiki**, saved as `wiki_inventory.md`. Each entry gives the topic, audience, tier, evidence, current status (correct / stale / wrong / missing) and target page. Be generous here; Phase 3 prunes. Also merge every `terms_used` into the draft glossary, and every `prerequisites` into the concept map.

# Phase 3: Structure and ordering (editor-in-chief; be aggressive)

Write `wiki_ia_plan.md` containing:
- the page tree
- the concept map, as a mermaid graph of which concept needs which, with the reading paths drawn in their order
- the old → new page mapping
- every merge, split, move and retirement, each with a one-line reason

Requirements for the plan:
- **Home fits on one screen.** It has one paragraph on what the machine and code are, then:
  - **three reading paths** of 5–8 pages each, ordered along the concept map: "Run the machine today", "Write my first experiment", "Maintain or extend the code"
  - **five lookup doors** for people in a hurry: Error Message Index, Troubleshooting (by symptom), Demons (quiet failures), Words You'll See, and Where does X live? (code map)
- **Sidebar**: 8 or fewer groups, following the machine flow and the order a newcomer learns in; lookup doors pinned at the top. Tier 3–4 material stays reachable but off the main path.
- **Grouping**: related concepts sit together, and one concept lives on exactly one page. Everywhere else links to it rather than re-explaining it, apart from a one-line definition in place where needed.
- **One page type per page**, following the Diátaxis model: tutorial, how-to, reference or explanation, plus troubleshooting and demons.
- **Size**: split pages over about 400 lines or with more than one purpose; merge stubs under about 30 lines unless they're lookup targets. Aim for fewer, better pages, and justify every new page.
- Fix misleading or misspelled names (for example, `Fast-DDS-freuqency-updates`) with redirect stubs. Drop the `_` prefix convention unless it carries meaning.
- Include a one-page **operator cheat sheet**: startup, health checks, a standard run, end of day, and the five most common recoveries.

**Review the plan before writing.** Two Opus agents role-play and try their question bank against the plan alone, flagging gaps, forward references, bad groupings and dead ends:
- (a) a newcomer who doesn't program, walking each reading path
- (b) a veteran arriving with a pasted error line

The editor-in-chief revises the plan, then writing starts.

# Phase 4: Writing

- Opus writers each own a **disjoint** set of pages and follow the page anatomy and writing rules.
- Only the editor-in-chief edits `Home`, `_Sidebar`, `Words-You'll-See`, `Troubleshooting`, `Error-Message-Index`, `Demons` and the code map. Writers submit entries for these pages, and the editor-in-chief merges them.
- After each writer finishes, the editor-in-chief does an **edit pass** on that page for ordering, grouping, clarity, jargon, voice and consistency with other pages.

# Phase 5: Verification (fresh Opus agents that did no writing)

1. **Fact-checkers**, one per page group: check every command, path, symbol, key, default and step against the code.
2. **Link checker**: every internal link and anchor resolves, and every `k-exp/wiki/` link in the code still resolves.
3. **Plain-language checker**: flag every undefined term (checked against Words You'll See), every undefined acronym, every symptom not written from the user's point of view or missing its verbatim text, every forward reference that breaks the concept map, every first screen that's a wall of text, and every sentence a non-programmer would have to read twice.
4. **Expert-usefulness checker**: for each subsystem page, is the Nuances section actually useful at 2 a.m.? Flag vague statements ("may cause issues") that need the specific mechanism, condition and code pointer.
5. **Question-bank test**: wiki-only agents answer both banks, and a separate agent grades them against the code.

The editor-in-chief decides the fix for every finding. Repeat until every question passes and every checker's findings are resolved. Record the results in `wiki_eval.md`.

# Phase 6: Delivery (editor-in-chief signs off)

- Commit to the wiki repo as a small number of logical commits, one per page group, with clear messages. (If the wiki can't be pushed to, commit `docs/wiki/` and the sync script to the k-exp `claude/...` branch.) No PRs unless I ask.
- Publish a final report as an artifact I can share with the lab. It should cover:
  - the new structure, the concept map and the reading paths
  - the old → new page map
  - what the old wiki got wrong
  - new Demon entries, with their confidence
  - the **needs-a-human list**, grouped by the page each item belongs to, so a lab member can fill them in
  - code footguns and inconsistencies found (not fixed), ranked by how likely they are to hurt an operator
  - both question banks' results
  - follow-ups (for example, a wiki-freshness CI check that flags pages whose cited files changed, and docstrings that would make the next update easier)

---
Follow-up instruction from the same session (after Phase 1 had started): "reduce the scope of research by consolidating all the subagents + processes to just two that can do a final sweep so that i can pass the task to another session, write docs so that another session can pick it up (running out of cloud usage)".
