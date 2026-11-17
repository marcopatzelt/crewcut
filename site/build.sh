#!/bin/sh
# Builds the landing page into site/_site (not committed). Run it in CI or before a local look:
#
#   site/build.sh
#
# - the page, its stylesheet and script from site/, the pictures from site/media/ (the app, wallpapers, thumbnails,
#   frames; see site/media/CREDITS.md)
# - Slate, the lockups, the crew and the states straight from docs/brand (one source, never redrawn)
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SITE="$ROOT/site"
OUT="$SITE/_site"

rm -rf "$OUT"
mkdir -p "$OUT/assets/brand/crew" "$OUT/assets/brand/states"

cp "$SITE/index.html" "$OUT/"
cp "$SITE/assets/site.css" "$SITE/assets/site.js" "$OUT/assets/"
cp -R "$SITE/media" "$OUT/media"

# the launch film: one source in docs/launch (also used by the README), copied, never stored twice
mkdir -p "$OUT/media/film"
cp "$ROOT/docs/launch/crewcut-launch-web.mp4" "$ROOT/docs/launch/poster.webp" "$ROOT/docs/launch/poster.jpg" "$OUT/media/film/"

B="$ROOT/docs/brand"
cp "$B/crewcut-lockup.svg" "$B/crewcut-lockup-dark.svg" "$B/slate-icon-small.svg" "$B/social-preview.png" \
   "$B/icons/slate-icon-180.png" "$OUT/assets/brand/"
cp "$B"/crew/*.svg "$OUT/assets/brand/crew/"
cp "$B"/states/*.svg "$OUT/assets/brand/states/"

echo "site built in $OUT"
