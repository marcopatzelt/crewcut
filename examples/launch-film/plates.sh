#!/bin/bash
# The plates of the film, rendered on the rented GPU into $OUT (Blender: Cycles + OptiX; the pixel grid: Pillow).
# Each plate's frame f shows comp time t0 + (f - 1) / 60, so plates and comp line up by construction.
#   bash plates.sh [stages]    stages: comma list of pixelgrid,slate,type,converge,meadow (default all)
# Measured on one RTX 4090: slate 101 frames ~10 min, type 170 frames ~8 min, meadow 300 frames ~35 min (three Blender
# processes in parallel; MEADOW_JOBS). The converge plate is the slate script again (94 frames, same samples).
set -e
. "$(dirname "$0")/env.sh"
STAGES=${1:-pixelgrid,slate,type,converge,meadow}
has(){ [[ ",$STAGES," == *",$1,"* ]]; }
FONT_3D=${FONT_3D:-$(ls "$FONT_DIR"/*[Ee]xtra[Bb]old*.[ot]tf 2>/dev/null | head -1)}
mkdir -p "$OUT"

# beat 2: squares on a fixed grid that switch on and off as a wave from the click (Pillow, no GPU)
if has pixelgrid; then
  rm -rf "$OUT/pixelgrid"; python3 "$HERE/pixelgrid.py" --out "$OUT/pixelgrid"
fi
# beat 2: the white 3D Slate pops in, turns, grows bristles and swirls apart (comp time 0.95 = frame 1)
if has slate; then
  rm -rf "$OUT/slate3d"
  bash "$HERE/bl.sh" slate3d.py --svg "$HERE/assets/slate-white.svg" --out "$OUT/slate3d" --frames 1-101 --samples 128 \
    --t0 0.95 --tin 0.99 --tshatter 1.62
  ls "$OUT/slate3d" | wc -l
fi
# beat 6: the heavy 3D word with a lilac flower and a yellow star (local time 0 = beat start)
if has type; then
  [ -f "$FONT_3D" ] || { echo "no Manrope ExtraBold in $FONT_DIR (run setup.sh or set FONT_3D)" >&2; exit 1; }
  rm -rf "$OUT/type3d"
  bash "$HERE/bl.sh" type3d.py --font "$FONT_3D" --out "$OUT/type3d" --frames 1-170 --samples 96
  ls "$OUT/type3d" | wc -l
fi
# beat 7: the green Slate swirls apart, then the frames are copied in reverse order so the flakes converge into it
if has converge; then
  rm -rf "$OUT/slate7" "$OUT/slate7r"
  bash "$HERE/bl.sh" slate3d.py --svg "$REPO/docs/brand/slate.svg" --out "$OUT/slate7" --frames 28-121 --samples 128 \
    --t0 0.0 --tin 0.1 --tshatter 1.0 --width 460 --flakes "#0F6E5C,#34C3A4"
  mkdir -p "$OUT/slate7r"; n=0
  for f in $(ls "$OUT"/slate7/slate_*.png | sort -r); do   # conv_0001 = widest swirl, the last file = the whole logo
    n=$((n + 1)); cp "$f" "$OUT/slate7r/conv_$(printf %04d $n).png"
  done
  ls "$OUT/slate7r" | wc -l
fi
# beats 2-3: the photoreal meadow behind the iris (comp time 2.03 = frame 1), lit by a CC0 HDRI from Poly Haven
if has meadow; then
  if [ ! -s "$HDRI" ]; then mkdir -p "$(dirname "$HDRI")"; curl -fsSL -o "$HDRI" "$HDRI_URL"; fi
  F0=${MEADOW_FIRST:-1}; F1=${MEADOW_LAST:-300}; J=${MEADOW_JOBS:-3}; mkdir -p "$OUT/meadow"
  N=$(( (F1 - F0 + J) / J ))
  for k in $(seq 0 $((J - 1))); do
    a=$((F0 + k * N)); b=$((a + N - 1)); [ $b -gt $F1 ] && b=$F1
    bash "$HERE/bl.sh" meadow3d.py --out "$OUT/meadow" --hdri "$HDRI" --frames $a-$b --samples 64 > "$OUT/meadow_$k.log" 2>&1 &
  done
  wait
  ls "$OUT/meadow" | wc -l
fi
echo "plates done: $STAGES"
