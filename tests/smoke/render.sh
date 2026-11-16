#!/bin/bash
# Smoke renders inside the Crewcut image. CI runs this (.github/workflows/image.yml); never run it on a laptop you
# need, it starts Chromium, Blender and ffmpeg.
#   bash /app/tests/smoke/render.sh <out_dir> [--quick]
# Renders the last frame of every 2D scene with its own example data in the neutral pack, one 3D still on the CPU
# (amd64 images only), and the 10-second preview. Writes PNG/MP4 files and a summary; exit 1 when anything failed.
set -uo pipefail
OUT=${1:-/tmp/crewcut-smoke}
QUICK=${2:-}
mkdir -p "$OUT/2d" "$OUT/3d"
export CREWCUT_STUDIO
CREWCUT_STUDIO=$(mktemp -d)
TOKENS=$(mktemp --suffix .json)
python3 -c 'import json; from crewcut import brand; print(json.dumps(brand.load().render_tokens()))' > "$TOKENS"
fail=0
summary="$OUT/summary.txt"
: > "$summary"

note() { echo "$1" | tee -a "$summary"; }

scenes=(/app/templates/2d/*.html)
[ -n "$QUICK" ] && scenes=(/app/templates/2d/counter.html)
for scene in "${scenes[@]}"; do
  name=$(basename "$scene" .html)
  extra=()
  [ "$name" = "keyword" ] && extra=(--transparent)
  if timeout 600 node /app/tools/render_html.js "$scene" "$OUT/2d/$name" --brand "$TOKENS" --from -1 --to -1 \
       "${extra[@]}" > "$OUT/2d/$name.json" 2> "$OUT/2d/$name.err"; then
    note "2d  $name  ok"
  else
    note "2d  $name  FAILED: $(tail -3 "$OUT/2d/$name.err" | tr '\n' ' ')"
    fail=1
  fi
done

if [ -z "$QUICK" ] && command -v blender >/dev/null 2>&1 && [ -f /app/tests/smoke/still3d.sh ]; then
  if timeout 1500 bash /app/tests/smoke/still3d.sh "$TOKENS" "$OUT/3d" > "$OUT/3d/log.txt" 2>&1; then
    note "3d  still  ok"
  else
    note "3d  still  FAILED: $(tail -3 "$OUT/3d/log.txt" | tr '\n' ' ')"
    fail=1
  fi
else
  note "3d  skipped (quick run or no Blender in this image)"
fi

if [ -z "$QUICK" ]; then
  if timeout 1200 crewcut brand preview --out "$OUT/preview.mp4" > "$OUT/preview.log" 2>&1; then
    note "preview  ok  $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/preview.mp4" 2>/dev/null) s"
  else
    note "preview  FAILED: $(tail -3 "$OUT/preview.log" | tr '\n' ' ')"
    fail=1
  fi
fi

note "result: $([ $fail = 0 ] && echo all ok || echo failures)"
exit $fail
