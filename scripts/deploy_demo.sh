#!/usr/bin/env bash
# Build the read-only static demo and publish it to the gh-pages branch (GitHub Pages, free).
# Needs the local API running (pages are rendered from it at build time) and the
# Time Machine export: uv run python scripts/export_demo.py
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_NAME="${REPO_NAME:-NexusPulse-AI}"
# Clear the fetch cache so pages use the current API responses, not those of an earlier build.
rm -rf apps/web/.next-static/cache/fetch-cache apps/web/.next/cache/fetch-cache
( cd apps/web && MSYS_NO_PATHCONV=1 NEXT_PUBLIC_STATIC_DEMO=1 NEXT_PUBLIC_BASE_PATH="/$REPO_NAME" npx next build )
OUT="apps/web/.next-static-out"
rm -rf "$OUT" && cp -r apps/web/.next-static "$OUT" && touch "$OUT/.nojekyll"
# The export writes segment prefetch files nested (about/__next.about/__PAGE__.txt) but the
# client requests them dot-joined (about/__next.about.__PAGE__.txt). Add flat copies so link
# prefetches don't 404 on a static host.
find "$OUT" -type f -path "*/__next.*/*" ! -path "*/_next/*" ! -path "*/server/*" ! -path "*/cache/*" ! -path "*/static/*" | while read -r f; do
  rel="${f#"$OUT"/}"; dir="${rel%%/__next.*}"; seg="${rel#"$dir"/}"
  [ "$dir" = "$rel" ] && { dir=""; seg="$rel"; }
  cp "$f" "$OUT/${dir:+$dir/}${seg//\//.}"
done
TMP="$(mktemp -d)"
git worktree add -f --detach "$TMP" >/dev/null
( cd "$TMP" && git checkout --orphan gh-pages-tmp >/dev/null 2>&1 && git rm -rfq . >/dev/null 2>&1 || true
  cp -r "$OLDPWD/$OUT/." . && git add -A && git commit -qm "Static demo build" && git push -qf origin HEAD:gh-pages )
git worktree remove --force "$TMP"
git branch -D gh-pages-tmp >/dev/null 2>&1 || true
rm -rf "$OUT"
echo "Published to the gh-pages branch."
