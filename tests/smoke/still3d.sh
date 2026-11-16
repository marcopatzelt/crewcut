#!/bin/bash
# One 3D still per neutral scene on the CPU, at a quarter size and few samples: proves Blender, the stage and the
# tokens work inside the image. CI only (called by render.sh).
#   still3d.sh <tokens.json> <out_dir>
set -uo pipefail
TOKENS=$1
OUT=$2
mkdir -p "$OUT"
DATA=$(mktemp --suffix .json)
echo '{"format": "landscape", "frames": 75, "fps": 25}' > "$DATA"
fail=0
for scene in box stack scale; do
  if timeout 600 blender -b --factory-startup --python "/app/templates/3d/$scene.py" -- --data "$DATA" \
       --brand "$TOKENS" --out "$OUT/$scene.png" --frame 60 --scale 25 --samples 16 > "$OUT/$scene.log" 2>&1 \
     && [ -s "$OUT/$scene.png" ]; then
    echo "3d $scene ok"
  else
    echo "3d $scene FAILED"; tail -5 "$OUT/$scene.log"; fail=1
  fi
done
exit $fail
