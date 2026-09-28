# Shared brief for Phase 4 writers (read first, then your page assignment)

You write wiki pages for the k-exp wiki rebuild. The editor-in-chief assigned you a disjoint set of pages; write those and nothing else. You do not edit `Home`, `_Sidebar`, `Words-You'll-See`, `Troubleshooting`, `Error-Message-Index`, `Demons` or `Where-Does-X-Live`: for those you SUBMIT entries (see "Submissions" below) and the editor merges them.

## Inputs (read them)
- Your assignment file (named in your prompt): the pages you own, each with its type, audience, tier, the research report sections that feed it, the old pages it absorbs (preserve their correct content), and the question-bank items it must answer.
- The structure plan: `SP/wiki_ia_plan.md` (page tree, concept map, page names, old→new map). Use the page names exactly as written there, both for your files and for links.
- The glossary draft: `SP/drafts/glossary.md`. Every technical term you use must be defined in the sentence where it first appears on your page, or linked to its glossary entry as `[term](Words-You'll-See#anchor)`. If a term you need is missing from the glossary, add it to your submissions.
- The research reports in `SP/reports/` named in your assignment. They are your evidence. Cite as the reports do.
- The code at `/home/user/k-exp` and `/home/user/wax` when you need to check a fact. Read-only. Never run anything.
- Style anchors: the current `Demons.md`, `PC-Setup.md`, `LiveOD---Camera-acquisition-and-previewer.md` in `SP/wiki/` for voice.

## Page anatomy (every concept or subsystem page, in this order; headings may be adapted, order may not)
1. First line: `*Page type: tutorial | how-to | reference | explanation | troubleshooting*`.
2. **In short**: 2–4 plain sentences: what this is, when you'd care, what to do. A newcomer who stops here is still correct.
3. **The idea**: the mental model, an everyday comparison, a mermaid diagram if one helps.
4. **Doing it**: the common case as numbered steps with exact commands, window titles, button labels, hosts and paths.
5. **Nuances and edge cases**: dense material for experts: order of operations, precedence and overrides, defaults, units, timing, what is saved vs what is applied, interactions with other subsystems. Every item carries a code pointer `repo/path/file.py:line` or a symbol name.
6. **When it goes wrong**: loud errors on this topic (exact text in a code block → cause → fix), and `> ⚠ **Known demon:** ...` callouts linking to `Demons#anchor`.
7. **Internals and code pointers**: a table: file / class / method / config key | one line each.
8. Footer, last line: `Last verified against code: 2026-09-28 · k-exp c8faf77 · wax acc4621`.
A pure how-to or tutorial page may shorten 3, 5 and 7 but keeps the order; a reference page may shorten 3 and 4.

## Writing rules (enforced by the editor and by a checker)
- Plain English, short sentences, active voice, one idea per paragraph. Say what to do before why; then say why (the why is what lets an expert reason about edge cases).
- Name exact things: window title, button label, file path, host PC, environment variable.
- Never write "simply", "just", "obviously", "easy". Avoid "stuff", "handle", "deal with" where a precise verb exists.
- Spell out every acronym on first use on each page: "digital-to-analog converter (DAC)".
- Symptoms are written from where the user stands: which window or terminal, the exact text they see quoted in a code block (so Ctrl-F finds it), what they expected, what did not happen, and the misleading signals (log lines that look like success, GUIs that look healthy).
- Evidence: every factual claim traces to code, a test, or a commit. Write only confirmed claims and clearly marked inferred ones ("The code implies ..."). Anything the reports mark "needs a human" goes into a `> **Needs a human:** ...` callout, not stated as fact.
- Preservation: correct material from the old pages that is too deep for the main path goes in Nuances or Internals, or you submit it for `Miscellaneous-Archaeology`; it is never dropped. Wrong material is corrected. Obsolete material goes to Archaeology with when and why it became obsolete.
- Units: SI everywhere in code; write values as the code does (`20.e-3`, seconds) and give the human unit in words alongside ("20 ms").
- Links: relative page links `[text](Page-Name)`; anchors are GitHub-style (lowercase, spaces→hyphens, punctuation dropped). Link to a concept's one home page rather than re-explaining it; a one-line definition in place is fine.
- No code changes, no fixes. If you find a bug or footgun, put it in your submissions under `bugs_and_footguns`.
- Length: aim under 400 lines per page. If a page wants more, tell the editor in your return message where it should split.

## Output
- Write each page to `SP/out/<Page-Name>.md` (GitHub wiki naming: title words joined with hyphens, exactly as in the plan).
- Write your submissions to `SP/submissions/<your-writer-id>.md` with these sections: `glossary_entries` (term, plain definition, comparison, our-code example, pages that link it), `troubleshooting_rows` (symptom from the user's view → message rows → page#anchor), `error_index_rows` (verbatim message | where seen | raised at file:line | cause | fix | page#anchor), `demon_callouts` (which demon, which page, one line), `code_map_rows` (what people search for | path | import name | one line), `archaeology` (obsolete material moved, with when/why), `bugs_and_footguns`, `needs_a_human`, `open_questions_for_editor`.
- Return as your final text: the list of pages written with line counts, and any split recommendations or open questions. Nothing else.
