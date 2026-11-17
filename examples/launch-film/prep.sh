#!/bin/bash
# Prepared PNG assets for the comp, into $ASSETS (run once before ad.sh):
#   icon-notes/chat/folder/camera.png   the four dock icons (assets/icons/*.svg, drawn for Crewcut)
#   icon-crewcut.png                    the Crewcut app icon (docs/brand/slate-icon.svg)
#   cards/crew-<id>.png                 pastel crew cards from the crew avatars (docs/brand/crew/*.svg)
#   cards/<name>.png                    rounded cards from YOUR images (CARDS_SRC, see below)
#   reel-backdrop.png                   the blurred picture behind the word reel (REEL_BACKDROP)
#
#   CARDS_SRC=/path/to/your/images [REEL_BACKDROP=/path/to/picture.png] bash prep.sh
#
# The grid in beat 4 shows your own work: thumbnails, screenshots, renders (JPG or PNG, any aspect ratio). The film
# used the author's own thumbnails and renders; they are not in the repository. Without CARDS_SRC the grid is made of
# crew cards only. REEL_BACKDROP defaults to docs/screenshot-dark.png.
set -e
. "$(dirname "$0")/env.sh"
mkdir -p "$ASSETS/cards"
for i in notes chat folder camera; do
  rsvg-convert -w 512 -h 512 "$HERE/assets/icons/$i.svg" -o "$ASSETS/icon-$i.png"
done
rsvg-convert -w 512 -h 512 "$REPO/docs/brand/slate-icon.svg" -o "$ASSETS/icon-crewcut.png"
python3 "$HERE/crewcards.py" "${CREW_SRC:-$REPO/docs/brand/crew}" "$ASSETS/cards"
if [ -n "$CARDS_SRC" ]; then python3 "$HERE/cards.py" "$CARDS_SRC" "$ASSETS/cards"; fi
cp "${REEL_BACKDROP:-$REPO/docs/screenshot-dark.png}" "$ASSETS/reel-backdrop.png"
ls "$ASSETS" "$ASSETS/cards" | head -60
