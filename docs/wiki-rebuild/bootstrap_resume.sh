#!/usr/bin/env bash
# Recreate the working layout the briefs expect, in a new session.
#   bash docs/wiki-rebuild/bootstrap_resume.sh [SCRATCHPAD_DIR]
# Default SCRATCHPAD_DIR is the path the original briefs use, so no brief needs editing.
set -euo pipefail
SP="${1:-/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
mkdir -p "$SP"
cp -r "$HERE"/. "$SP"/
mkdir -p "$SP/out" "$SP/submissions" "$SP/checks"
cp -r "$REPO_ROOT/docs/wiki"/. "$SP/out"/ 2>/dev/null || true
if [ ! -d "$SP/wiki/.git" ]; then
  git clone --quiet https://github.com/ucsb-amo/k-exp.wiki.git "$SP/wiki"
fi
if [ "$SP" != "/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad" ]; then
  grep -rl "/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad" "$SP/briefs" \
    | xargs -r sed -i "s#/tmp/claude-0/-home-user/db7054f3-75e8-5d58-9981-ce723c029a42/scratchpad#$SP#g"
fi
echo "scratchpad ready at: $SP"
echo "  briefs:   $SP/briefs"
echo "  reports:  $SP/reports  ($(ls "$SP/reports" | wc -l) files)"
echo "  wiki:     $SP/wiki     (clone of k-exp.wiki, read-only from a cloud session)"
echo "  out:      $SP/out      (pages in progress; copy back to docs/wiki/ before committing)"
