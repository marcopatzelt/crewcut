#!/bin/sh
# Builds the landing page into site/_site (not committed). Run it in CI or before a local look:
#
#   site/build.sh
#
# - the page, its stylesheet and script from site/, the pictures from site/media/ (wallpapers, frames, thumbnails;
#   see site/media/CREDITS.md)
# - Slate, the lockups, the crew and the states straight from docs/brand (one source, never redrawn)
# - the app windows from docs/readme (the README window images rendered in CI), cut to the window, as WebP
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SITE="$ROOT/site"
OUT="$SITE/_site"

rm -rf "$OUT"
mkdir -p "$OUT/assets/brand/crew" "$OUT/assets/brand/states" "$OUT/assets/app"

cp "$SITE/index.html" "$OUT/"
cp "$SITE/assets/site.css" "$SITE/assets/site.js" "$OUT/assets/"
cp -R "$SITE/media" "$OUT/media"

B="$ROOT/docs/brand"
cp "$B/crewcut-lockup.svg" "$B/crewcut-lockup-dark.svg" "$B/slate-icon-small.svg" "$B/social-preview.png" \
   "$B/icons/slate-icon-180.png" "$OUT/assets/brand/"
cp "$B"/crew/*.svg "$OUT/assets/brand/crew/"
cp "$B"/states/*.svg "$OUT/assets/brand/states/"

# the app windows: WebP in three widths from the README images (3520 x 2396 at twice the density: the macOS window
# on a green wallpaper), cut to the window alone (3198 x 2074 from 162,162); the page sets width 1760 and height 1141
# on each <img> (the same 1.542 shape). The size check stops the build when tools/ci/readme_shots.mjs changes the
# composition: then measure the window again and change the numbers.
png_size() { od -An -tu1 -j16 -N8 "$1" | awk '{ printf "%dx%d", $1*16777216+$2*65536+$3*256+$4, $5*16777216+$6*65536+$7*256+$8 }'; }
webp() { # source, width, target
  if command -v cwebp > /dev/null 2>&1; then cwebp -quiet -q 84 -crop 162 162 3198 2074 -resize "$2" 0 "$1" -o "$3"
  elif command -v magick > /dev/null 2>&1; then magick "$1" -crop 3198x2074+162+162 +repage -resize "$2"x -quality 84 "$3"
  else ffmpeg -loglevel error -y -i "$1" -vf "crop=3198:2074:162:162,scale=$2:-1" -quality 84 "$3"; fi
}
for pair in "crewcut-dark episode-dark" "crewcut-episodes-light episodes-light" "crewcut-episodes-dark episodes-dark"; do
  set -- $pair
  src="$ROOT/docs/readme/$1.png"
  size=$(png_size "$src")
  if [ "$size" != "3520x2396" ]; then echo "build.sh: docs/readme/$1.png is $size, not 3520x2396: measure the window and update the crop" >&2; exit 1; fi
  for w in 1200 1760 2400; do webp "$src" "$w" "$OUT/assets/app/$2-$w.webp"; done
done

echo "site built in $OUT"
