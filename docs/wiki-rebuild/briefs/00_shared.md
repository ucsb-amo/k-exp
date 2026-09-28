# Shared brief for every Phase 1 research agent (read this first, then your own brief)

You are one of 15 research agents rebuilding the k-exp wiki. You report to the editor-in-chief, who reads your report in full. You do research and write a report; you make no structural decisions and edit no wiki pages.

## Where things are (this container)
- k-exp repo: `/home/user/k-exp` (package `kexp`). HEAD c8faf77 (2026-09-27).
- wax repo: `/home/user/wax` (`waxx-src/waxx`, `waxa-src/waxa`, each with `tests/`). HEAD acc4621 (2026-09-27).
- The current wiki, cloned: `/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad/wiki/*.md` (36 pages). Read the pages your brief names, claim by claim.
- Editor's recon (code map, page inventory, staleness ranking): `/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad/phase0_recon.md`. Read it.
- Question banks: `/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad/question_banks.md`. Read it; answer the questions in your area (see your brief) with citations.
- The `beacon` package (weldlabucsb/beacon: UDP discovery, camera server/viewer) is NOT in this container. Treat it as a black box; report exactly which beacon names the code calls and mark claims about its internals "needs a human".

## Ground rules
- READ ONLY. Do not edit, create or delete anything under `/home/user/k-exp` or `/home/user/wax`. Do not run experiments, GUIs, servers, or tests (ARTIQ, PyQt and the lab network are not available here; running things would mislead you). `grep`, `sed -n`, `python3 -c` on pure-python snippets and `git log`/`git blame`/`git show` are fine and encouraged. Use `git -C <repo> ...`.
- The code as it is today wins over the wiki, over comments, and over your memory. When a docstring and the code disagree, say so.
- Every factual claim carries a citation `repo/path/file.py:line` (or a class/function name, a test name, or a commit SHA) and a confidence label: **confirmed** (code or test shows it), **inferred** (strongly implied; say from what), or **needs a human** (physical/lab procedure, lab lore, beacon internals, anything you cannot see). Only confirmed and clearly marked inferred claims will go on the wiki.
- Quote error and log strings VERBATIM, in code blocks, exactly as the code prints them (resolve f-strings with a plausible example and show the template too).
- Symptoms are written from where the user stands: which window/terminal, exact text they see, what they expected, what did not happen, and the misleading signals (log lines that look like success, GUIs that look healthy).
- Tests are strong evidence of real behaviour (and each regression test usually marks something that broke). Read the tests for your area.
- Commit history is evidence for "why" and for dates ("since 2026-09-26"). Use `git log -S`, `git log --follow`, `git show`.
- Two readers: a newcomer (knows AMO physics, may barely program) and an expert at 2 a.m. with a pasted error. Write for both: plain summary first, then the dense nuance with pointers.
- Style anchors for voice (read at least two): `Demons.md`, `LiveOD---Camera-acquisition-and-previewer.md`, `PC-Setup.md`, `Real-Time-Device-Control-(Monitor).md` in the wiki clone. Concrete, second person, exact names, mechanisms explained.
- Report bugs and footguns you find; do not fix them.

## Report format (use these exact section headings, in this order)
1. `operator_summary`: 3–6 plain sentences for a newcomer.
2. `mental_model`: an everyday comparison, plus an optional mermaid diagram.
3. `how_to`: numbered procedures with exact commands, GUIs (window titles, button labels), hosts and paths.
4. `reference_facts`: keys, defaults, units, symbols and locations, each with a citation and a confidence label. Tables welcome.
5. `expert_nuances`: precedence, ordering, timing, defaults, silent overrides, requested-vs-applied values, interactions with other subsystems, and the *why* where code or history shows it. What a veteran wants at 2 a.m. Each item: code pointer.
6. `loud_failures`: verbatim error text → cause → fix. One entry per distinct message. Include the file:line that raises/prints it.
7. `demon_candidates`: quiet or misleading failures, each with its evidence (code pattern, commit, test, comment), date first seen if history shows it, and a confidence line (*seen and confirmed* / *best explanation — still needs checking*). Patterns to hunt: try/except that swallows or only prints; fallbacks to default/dummy/simulation; commands sent with no acknowledgement; threads that can die while the main loop continues; unconditional success messages; stale caches; silent config overrides; device IDs/hosts that drift from reality; clock/timezone/run-ID edge cases; metadata that records the request rather than what was applied.
8. `symptoms`: every symptom above, rewritten from the user's point of view (where they look, verbatim text, expected vs happened, misleading signals).
9. `terms_used`: every jargon term this area needs, each with a draft plain-language definition (no undefined words), an everyday comparison where one helps, and a real our-code example (a real name or short snippet from the repos). Include basic programming terms a non-programmer would trip on in your area.
10. `prerequisites`: the concepts a reader must know before this area makes sense (for the concept map). Name them as glossary terms.
11. `wiki_audit`: which current pages cover this area; for each, a claim-by-claim verdict: correct / stale (what changed, when) / wrong (what the code says) / unverifiable. Note duplication with other pages, and material too deep for the main path that must be preserved (Nuances/Internals/Archaeology).
12. `needs_a_human`: questions the code cannot answer (lab procedures, physical layout, lore, beacon internals).
13. `proposed_topics`: candidate topics for the wiki, each tagged audience (newcomer / experimenter / maintainer / expert lookup) and tier (1 must know to run the machine; 2 needed to write experiments; 3 look up when needed; 4 internals and archaeology), with a one-line reason.
14. `question_bank_answers`: for each question in your brief's list, your answer with citations and confidence, plus any question you think the banks are missing for your area.
15. `bugs_and_footguns`: code problems found (not fixed), each with file:line, what happens, how likely to hurt an operator (high/medium/low).

## Output
Write the full report (be thorough: 400–1200 lines is normal) to the path named in your brief under `/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad/reports/`. Then return, as your final text, ONLY: the report path, and a 10–15 line abstract (top findings, top demon candidates, top footguns, and the current-wiki pages you judge stale or wrong).
