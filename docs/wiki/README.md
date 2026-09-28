# docs/wiki — the k-exp wiki, kept in the repo

This folder is the source of the GitHub wiki at <https://github.com/ucsb-amo/k-exp/wiki>.
Each `*.md` file is one wiki page, named the way GitHub names wiki pages
(`Words-You'll-See.md` is the page "Words You'll See"). `Home.md` is the front page and
`_Sidebar.md` the sidebar.

## Publishing changes to the wiki

The wiki is its own git repository (`https://github.com/ucsb-amo/k-exp.wiki.git`). To push
this folder to it in one command, from any PC that can push to `k-exp`:

```bash
bash docs/wiki/sync_wiki.sh            # commit and push
bash docs/wiki/sync_wiki.sh --dry-run  # show what would change
```

or on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File docs\wiki\sync_wiki.ps1
```

The script clones the wiki into a temporary folder, copies every page here over it
(a page deleted here is deleted there), commits with the k-exp commit hash, and pushes to
the wiki's `master` branch.

## Editing rules

- Edit pages here and sync, or edit on the wiki and copy back; do not let the two drift.
- Old page names are kept as one-line redirect stubs so existing links keep working.
- Every page ends with a `Last verified against code:` line. Update it when you re-check a
  page against the code.
- The evaluation record of the 2026-09 rebuild is `wiki_eval.md`; the structure plan is
  `wiki_ia_plan.md`; the inventory of everything that should be on the wiki is
  `wiki_inventory.md`.
