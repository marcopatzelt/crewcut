#!/bin/sh
# Builds the landing page into site/_site (not committed). Run it in CI or before a local look:
#
#   site/build.sh
#
# - the page, its stylesheet and the two drawn landscapes from site/
# - Slate, the lockups, the app icon, the crew and the states straight from docs/brand (one source, never redrawn)
# - the app window from docs/readme (the newest README window images from CI), cut to the window, as WebP
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SITE="$ROOT/site"
OUT="$SITE/_site"

rm -rf "$OUT"
mkdir -p "$OUT/assets/brand/crew" "$OUT/assets/brand/states" "$OUT/assets/app"

cp "$SITE/index.html" "$OUT/"
cp "$SITE/assets/site.css" "$SITE/assets/landscape-light.svg" "$SITE/assets/landscape-dark.svg" "$OUT/assets/"

B="$ROOT/docs/brand"
cp "$B/crewcut-lockup.svg" "$B/crewcut-lockup-dark.svg" "$B/slate-icon.svg" "$B/slate-icon-small.svg" "$B/social-preview.png" \
   "$B/icons/slate-icon-180.png" "$OUT/assets/brand/"
cp "$B"/crew/*.svg "$OUT/assets/brand/crew/"
cp "$B"/states/*.svg "$OUT/assets/brand/states/"

# the app window: WebP in three widths from the README images (3520 x 2396 at twice the density: the macOS window on
# a green wallpaper), cut to the window alone (3198 x 2074 from 162,162) so it floats on the page's own landscape;
# the page sets width 1760 and height 1141 on the <img> (the same 1.542 shape). The size check below stops the build
# when tools/ci/readme_shots.mjs changes the composition: then measure the window again and change the numbers.
png_size() { od -An -tu1 -j16 -N8 "$1" | awk '{ printf "%dx%d", $1*16777216+$2*65536+$3*256+$4, $5*16777216+$6*65536+$7*256+$8 }'; }
for t in light dark; do
  size=$(png_size "$ROOT/docs/readme/crewcut-$t.png")
  if [ "$size" != "3520x2396" ]; then echo "build.sh: docs/readme/crewcut-$t.png is $size, not 3520x2396: measure the window and update the crop" >&2; exit 1; fi
done
webp() { # source, width, target
  if command -v cwebp > /dev/null 2>&1; then cwebp -quiet -q 84 -crop 162 162 3198 2074 -resize "$2" 0 "$1" -o "$3"
  elif command -v magick > /dev/null 2>&1; then magick "$1" -crop 3198x2074+162+162 +repage -resize "$2"x -quality 84 "$3"
  else ffmpeg -loglevel error -y -i "$1" -vf "crop=3198:2074:162:162,scale=$2:-1" -quality 84 "$3"; fi
}
for t in light dark; do
  for w in 1200 1760 2400; do webp "$ROOT/docs/readme/crewcut-$t.png" "$w" "$OUT/assets/app/crewcut-$t-$w.webp"; done
done

echo "site built in $OUT"
