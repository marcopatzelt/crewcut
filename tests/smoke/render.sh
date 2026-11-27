#!/bin/bash
# Smoke renders inside the Crewcut image. CI runs this (.github/workflows/image.yml); never run it on a laptop you
# need, it starts Chromium, Blender and ffmpeg.
#   bash /app/tests/smoke/render.sh <out_dir> [--quick]
# Renders the last frame of every 2D scene (both formats) in the neutral pack, the demo episode end to end (with its
# two motion graphics when effectcraft-cli is there), one 3D still per scene on the CPU (amd64 images only), the
# motion graphics part (tests/smoke/motion.py: the last frame of every motion template in each format with the hue
# check, a keyword_pop overlay MOV and a number_roll MP4 with their frame counts; under 10 minutes), and the
# 10-second preview, and one still of every HyperFrames template in both formats. Writes PNG/MP4 files and a summary;
# exit 1 when anything failed.
set -uo pipefail
OUT=${1:-/tmp/crewcut-smoke}
QUICK=${2:-}
mkdir -p "$OUT/2d" "$OUT/3d" "$OUT/motion"
export CREWCUT_STUDIO
CREWCUT_STUDIO=$(mktemp -d)
TOKENS=$(mktemp --suffix .json)
python3 -c 'import json; from crewcut import brand; print(json.dumps(brand.load().render_tokens()))' > "$TOKENS"
fail=0
summary="$OUT/summary.txt"
: > "$summary"

note() { echo "$1" | tee -a "$summary"; }

if [ -n "$QUICK" ]; then
  # emulated arm64: one scene, one frame, straight through the renderer
  if timeout 900 node /app/tools/render_html.js /app/templates/2d/counter.html "$OUT/2d/counter" --brand "$TOKENS" \
       --from -1 --to -1 > "$OUT/2d/counter.json" 2> "$OUT/2d/counter.err"; then
    note "2d  counter  ok"
  else
    note "2d  counter  FAILED: $(tail -3 "$OUT/2d/counter.err" | tr '\n' ' ')"; fail=1
  fi
else
  # every 2D scene, both formats, last frame
  if timeout 1200 crewcut render samples --out "$OUT/2d" > "$OUT/2d/samples.log" 2>&1; then
    note "2d  samples  ok ($(find "$OUT/2d" -name '*.png' | wc -l) images)"
  else
    note "2d  samples  FAILED: $(tail -5 "$OUT/2d/samples.log" | tr '\n' ' ')"; fail=1
  fi
  # the demo episode end to end: six 2D inserts and two motion graphics (left out with a note when effectcraft-cli
  # is missing: the plan says motion_without_engine: skip) on a generated background, assembly, loudness
  mkdir -p "$CREWCUT_STUDIO/episodes"
  cp -r /app/examples/demo "$CREWCUT_STUDIO/episodes/000-demo"
  if timeout 1500 crewcut render all "$CREWCUT_STUDIO/episodes/000-demo/edit/plan-v001.json" --local --no-gate \
       > "$OUT/demo.log" 2>&1; then
    cp "$CREWCUT_STUDIO/episodes/000-demo/export/"*.mp4 "$OUT/" 2>/dev/null
    note "demo  ok  $(tail -1 "$OUT/demo.log")"
  else
    note "demo  FAILED: $(tail -5 "$OUT/demo.log" | tr '\n' ' ')"; fail=1
  fi
fi

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

if [ -z "$QUICK" ] && command -v effectcraft-cli >/dev/null 2>&1; then
  # motion graphics: every template's last frame per format with the hue check, two real clips (budget 10 minutes)
  if timeout 600 python3 /app/tests/smoke/motion.py "$OUT/motion" > "$OUT/motion/log.txt" 2>&1; then
    note "motion  ok  $(grep -c '^motion sample .*: ok' "$OUT/motion/log.txt") samples, $(grep -c '^motion clip .*: ok' "$OUT/motion/log.txt") clips; $(grep 'took' "$OUT/motion/log.txt" | tr '\n' ' ')"
  else
    note "motion  FAILED: $(grep -E 'FAILED|Error|error' "$OUT/motion/log.txt" | tail -5 | tr '\n' ' ')$(tail -2 "$OUT/motion/log.txt" | tr '\n' ' ')"
    fail=1
  fi
else
  note "motion  skipped (quick run or no effectcraft-cli in this image)"
fi

if [ -z "$QUICK" ]; then
  if timeout 1200 crewcut brand preview --out "$OUT/preview.mp4" > "$OUT/preview.log" 2>&1; then
    note "preview  ok  $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/preview.mp4" 2>/dev/null) s"
  else
    note "preview  FAILED: $(tail -3 "$OUT/preview.log" | tr '\n' ' ')"
    fail=1
  fi
fi

if [ -z "$QUICK" ] && [ -x /app/tools/hyperframes/node_modules/.bin/hyperframes ]; then
  # HyperFrames building blocks: one still of every template in both formats, through the image's pinned CLI and Chrome
  mkdir -p "$OUT/hyperframes"
  hf_ok=0; hf_n=0
  for t in $(crewcut motion --json hf list | python3 -c 'import json,sys; print(" ".join(r["name"] for r in json.load(sys.stdin)))'); do
    for fmt in landscape portrait; do
      hf_n=$((hf_n + 1))
      if timeout 300 crewcut motion hf sample "$t" --out "$OUT/hyperframes/$t-$fmt" --format "$fmt" --at 1.2 \
           > "$OUT/hyperframes/$t-$fmt.log" 2>&1; then
        hf_ok=$((hf_ok + 1))
      else
        note "hyperframes $t $fmt FAILED: $(tail -3 "$OUT/hyperframes/$t-$fmt.log" | tr '\n' ' ')"; fail=1
      fi
    done
  done
  note "hyperframes  $hf_ok of $hf_n stills ok"
else
  note "hyperframes  skipped (quick run or no HyperFrames in this image)"
fi

note "result: $([ $fail = 0 ] && echo all ok || echo failures)"
exit $fail
