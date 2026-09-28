#!/usr/bin/env bash
# Push docs/wiki/ to the GitHub wiki (ucsb-amo/k-exp.wiki, branch master) in one command.
#
#   bash docs/wiki/sync_wiki.sh              # commit + push
#   bash docs/wiki/sync_wiki.sh --dry-run    # show what would change, push nothing
#
# Run it from any machine that can push to the k-exp repo (the wiki shares its
# permissions). It clones the wiki into a temporary folder, copies every page
# from docs/wiki/ over it (pages removed here are removed there too, except the
# wiki's own history), commits with a message naming the k-exp commit, and pushes.
set -euo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
SRC="$REPO_ROOT/docs/wiki"
WIKI_URL="${WIKI_URL:-https://github.com/ucsb-amo/k-exp.wiki.git}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "cloning $WIKI_URL"
git clone --quiet "$WIKI_URL" "$TMP/wiki"

# Copy pages. --delete removes wiki pages that no longer exist in docs/wiki/
# (redirect stubs keep old names alive, so nothing a link points at is lost).
rsync -a --delete \
  --exclude '.git' --exclude 'sync_wiki.sh' --exclude 'sync_wiki.ps1' \
  --exclude 'README.md' --exclude '*.py' \
  "$SRC/" "$TMP/wiki/"

cd "$TMP/wiki"
if git diff --quiet && [ -z "$(git status --porcelain)" ]; then
  echo "wiki already matches docs/wiki/: nothing to push"
  exit 0
fi

git add -A
echo "changes:"
git status --short
if [ "$DRY" = 1 ]; then
  echo "dry run: not committing"
  exit 0
fi

SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
git commit --quiet -m "Sync from k-exp docs/wiki @ $SHA"
git push origin HEAD:master
echo "pushed to $WIKI_URL (master)"
