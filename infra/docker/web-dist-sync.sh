#!/bin/sh
# One-shot publish of the built SPA into the shared web_dist volume.
# Ordering is deliberate so an interruption never leaves the live site broken:
#   1. copy new hashed assets alongside the old ones (names never collide);
#   2. copy any other root files except index.html;
#   3. publish index.html LAST (the atomic "switch" — it references only
#      already-present assets);
#   4. prune assets that no longer exist in the new build (old sessions may
#      still request them briefly; pruning after publish keeps the window to
#      in-flight tabs only). Steps 1-3 failing leaves the previous site fully
#      intact; step 4 is best-effort.
set -eu

SRC=/opt/dist
DST=/srv/web

mkdir -p "$DST/assets"
cp -a "$SRC/assets/." "$DST/assets/"

# Root files (sw.js, etc.) except index.html — write to a temp name on the
# SAME volume, then atomically rename, so an interrupted copy never leaves a
# truncated live file (cp truncates the destination before writing).
for f in "$SRC"/*; do
  base=$(basename "$f")
  [ "$base" = "index.html" ] && continue
  [ "$base" = "assets" ] && continue
  cp -a "$f" "$DST/.$base.tmp"
  mv -f "$DST/.$base.tmp" "$DST/$base"
done

# index.html LAST and atomically — this is the publish "switch"; it references
# only assets already present above.
cp "$SRC/index.html" "$DST/.index.html.tmp"
mv -f "$DST/.index.html.tmp" "$DST/index.html"

for f in "$DST"/assets/*; do
  base=$(basename "$f")
  [ -e "$SRC/assets/$base" ] || rm -f "$f" || true
done

echo "web dist synced"
