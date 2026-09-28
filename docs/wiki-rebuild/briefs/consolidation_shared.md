# Consolidation sweep — shared instructions (read with your own consolidation brief)

The original 15-agent research fan-out was cut short: the requesting session is out of cloud usage and the task is being handed to another session. You are one of TWO agents doing a final sweep. You cover several research areas whose reports were not finished, at reduced depth, and you write ONE consolidated report that the next editor-in-chief can use directly.

Read first: `SP/briefs/00_shared.md` (rules, evidence labels, the 15-section report format), `SP/phase0_recon.md`, `SP/question_banks.md`, then the per-area briefs your consolidation brief names. `SP` = `/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad`.

## Before researching an area
1. `ls SP/reports/`: if `NN_<area>.md` already exists for one of your areas (its agent finished after all), do NOT redo it; read it and only add a short "gaps noticed" note in your report.
2. Salvage: START with the compact extracts `SP/salvage/NN_<area>_transcript.md` (the stopped agent's own notes, every file it read or grepped, tool results truncated). Only if you need a full tool result go to the raw JSONL. The raw transcripts are JSONL files under `TRANSCRIPTS/wf_*/agent-*.jsonl` (TRANSCRIPTS is given in your brief). For each of your areas, find the transcript that mentions `reports/NN_` (`grep -l "reports/NN_" TRANSCRIPTS/wf_*/agent-*.jsonl`) and extract what its agent already established: tool results it read, and any draft report text in a `Write` or `Bash` tool call (`grep -o '"content":"[^"]*"'` on the relevant lines, or load the JSONL with `python3 -c "import json,sys; ..."` and print the assistant messages' text and tool inputs). Use that as research already done; verify anything you reuse against the code (a file:line you cite must be one you or the transcript actually read).
3. Then read the code the per-area brief lists, at reduced depth: the main files fully, the long GUI files by docstrings and grep.

## Depth
Per area, 120–220 lines, the 15 section headings from `00_shared.md` in order, terse. Spend your effort on: `reference_facts`, `expert_nuances`, `loud_failures` (verbatim strings with file:line), `demon_candidates`, `wiki_audit`, `terms_used`, `question_bank_answers`, `bugs_and_footguns`. `operator_summary`, `mental_model`, `how_to` can be short. Every claim still carries a citation and a confidence label; verbatim strings still go in code blocks.

## Output and hand-in (important: the session that launched you may be gone before you finish)
1. Write `SP/reports/CONSOLIDATED_<X>.md` (X = A or B, from your brief): a title, a "coverage" table (area | source: fresh research / salvaged transcript / existing report | depth), then one `## Area NN — <name>` section per area containing the 15 subsections.
2. Copy it into the repo and push it yourself, so it survives:
   ```
   cp SP/reports/CONSOLIDATED_<X>.md /home/user/k-exp/docs/wiki-rebuild/reports/
   cd /home/user/k-exp && git add docs/wiki-rebuild/reports/CONSOLIDATED_<X>.md
   git commit -m "docs(wiki-rebuild): consolidated research report <X> (areas NN, NN, NN)

   Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01RiGMrRUDGr8tMs3V7tip46"
   git pull --rebase origin claude/determined-ptolemy-qdteku && git push -u origin claude/determined-ptolemy-qdteku
   ```
   If the push is rejected, `git pull --rebase` and push again (up to 4 times). Never force-push. Never touch any other file in the repo. No model names in the commit message beyond the attribution lines above.
3. Return as your final text: the report path, the commit SHA you pushed, and a 10-line abstract.
Read-only otherwise: never modify `/home/user/k-exp` outside `docs/wiki-rebuild/reports/`, never modify `/home/user/wax`, never run tests, GUIs, servers or experiments.
