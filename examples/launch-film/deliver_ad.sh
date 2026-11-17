#!/bin/bash
# Deliverables of one version into $OUT/ad/VERSION: the clip (comp Master, chunked render), 60 fps strips across every
# transition (30 frames, every 2nd frame), a frame sheet (every 0.25 s) and hue checks at chosen times.
#   bash deliver_ad.sh VERSION [clip|sheets]
set -e
. "$(dirname "$0")/env.sh"
V=${1:-v1}; ONLY=${2:-all}; D=$OUT/ad/$V; mkdir -p "$D"
E="crewcut motion --json --project $PROJECT --templates-dir $HERE/templates"
if [ "$ONLY" != sheets ]; then
  $E render video --comp Master --start 0 --end 17.5 --fps 60 --chunk 1.0 --jobs 6 --out "$D/crewcut-launch-$V.mp4" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print('clip',d['frames'],'/',d['expected_frames'],d['output'])"
fi
[ "$ONLY" = clip ] && exit 0
strip(){ T=$(python3 -c "print(','.join(f'{$2+i*2/60:.4f}' for i in range(30)))"); $E render sheet --comp Master --times $T --cols 6 --max-side 400 --out "$D/strip-$1.jpg" >/dev/null; }
strip 2-click 0.88; strip 2-iris 1.70; strip 3-push 3.35; strip 3-4-wipe 6.35; strip 4-5 9.55; strip 5-6 11.75; strip 6-smash 12.85; strip 6-7 14.6
T=$(python3 -c "print(','.join(f'{i*0.25:.2f}' for i in range(70)))"); $E render sheet --comp Master --times $T --cols 7 --max-side 320 --out "$D/framesheet.jpg" >/dev/null
# hue check: no single hue above ~30 % of the coloured pixels (natural scenes such as grass and sky excepted)
PAL=$D/.palette.png
for t in 0.5 1.3 3.0 4.6 8.5 11.0 13.8 16.8; do
  $E render frame --comp Master --time $t --out "$PAL" >/dev/null
  echo "hue $t $(crewcut motion --project "$PROJECT" render palette "$PAL" 2>&1 | tail -1)"
done
rm -f "$PAL"
ls -la "$D"
