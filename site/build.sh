#!/bin/sh
# Builds the landing page into site/_site (not committed). Run it in CI or before a local look:
#
#   site/build.sh [path to a clone of Leonxlnx/taste-skill]
#
# - the page and its stylesheet from site/
# - Slate, the lockups, the crew and the states straight from docs/brand (one source, never redrawn)
# - the app window from docs/readme, as WebP in two widths
# - the four files of the Taste skill's word-highlight moment (MIT), from the commit CI pins, with its licence;
#   they are linked and fetched, not kept in this repository
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SITE="$ROOT/site"
OUT="$SITE/_site"
TASTE_REPO=https://github.com/Leonxlnx/taste-skill.git
TASTE_COMMIT=f6b76575f949707b4e3c37cd86cb44b0b98643e8
TASTE=${1:-}

rm -rf "$OUT"
mkdir -p "$OUT/assets/brand/crew" "$OUT/assets/brand/states" "$OUT/assets/app" "$OUT/assets/moments/word-highlight"

cp "$SITE/index.html" "$OUT/"
cp "$SITE/assets/site.css" "$OUT/assets/"

B="$ROOT/docs/brand"
cp "$B/crewcut-lockup.svg" "$B/crewcut-lockup-dark.svg" "$B/slate-icon-small.svg" "$B/social-preview.png" \
   "$B/icons/slate-icon-180.png" "$OUT/assets/brand/"
cp "$B"/crew/*.svg "$OUT/assets/brand/crew/"
cp "$B"/states/*.svg "$OUT/assets/brand/states/"

# the app window: WebP in three widths from the README images (3520 x 2320), cropped to the window and its shadow
# (3280 x 2120 from 120,120; the page sets width 1760 and height 1138 on the <img>, the same 1.547 shape)
webp() { # source, width, target
  if command -v cwebp > /dev/null 2>&1; then cwebp -quiet -q 82 -crop 120 120 3280 2120 -resize "$2" 0 "$1" -o "$3"
  elif command -v magick > /dev/null 2>&1; then magick "$1" -crop 3280x2120+120+120 +repage -resize "$2"x -quality 82 "$3"
  else ffmpeg -loglevel error -y -i "$1" -vf "crop=3280:2120:120:120,scale=$2:-1" -quality 82 "$3"; fi
}
for t in light dark; do
  for w in 1200 1760 2400; do webp "$ROOT/docs/readme/crewcut-$t.png" "$w" "$OUT/assets/app/crewcut-$t-$w.webp"; done
done

if [ -z "$TASTE" ]; then
  TASTE=$(mktemp -d)
  git clone -q "$TASTE_REPO" "$TASTE"
  git -C "$TASTE" checkout -q "$TASTE_COMMIT"
fi
K="$TASTE/skills/taste-skill/assets/moments"
cp "$K/moments.js" "$K/lib.js" "$OUT/assets/moments/"
cp "$K/word-highlight/moment.css" "$K/word-highlight/moment.js" "$OUT/assets/moments/word-highlight/"
cp "$TASTE/LICENSE" "$OUT/assets/moments/LICENSE"

echo "site built in $OUT"
