#!/usr/bin/env bash
# Build the read-only static demo and publish it to the gh-pages branch (GitHub Pages, free).
# Needs the local API running (pages are rendered from it at build time) and the
# Time Machine export: uv run python scripts/export_demo.py
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_NAME="${REPO_NAME:-NexusPulse-AI}"
( cd apps/web && MSYS_NO_PATHCONV=1 NEXT_PUBLIC_STATIC_DEMO=1 NEXT_PUBLIC_BASE_PATH="/$REPO_NAME" npx next build )
OUT="apps/web/.next-static-out"
rm -rf "$OUT" && cp -r apps/web/.next-static "$OUT" && touch "$OUT/.nojekyll"
TMP="$(mktemp -d)"
git worktree add -f --detach "$TMP" >/dev/null
( cd "$TMP" && git checkout --orphan gh-pages-tmp >/dev/null 2>&1 && git rm -rfq . >/dev/null 2>&1 || true
  cp -r "$OLDPWD/$OUT/." . && git add -A && git commit -qm "Static demo build" && git push -qf origin HEAD:gh-pages )
git worktree remove --force "$TMP"
git branch -D gh-pages-tmp >/dev/null 2>&1 || true
rm -rf "$OUT"
echo "Published to the gh-pages branch."
