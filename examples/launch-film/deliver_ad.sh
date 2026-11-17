#!/bin/bash
# Deliverables of one version into $OUT/ad/VERSION: the clip (comp Master, chunked render), 60 fps strips across every
# transition (30 frames, every 2nd frame), a frame sheet (every 0.25 s) and hue checks at chosen times.
#   bash deliver_ad.sh VERSION [clip|sheets]
# With REF=/path/to/local.mp4 also one comparison sheet per beat against a reference clip (ours | reference at
# matched times). Compare frame by frame with a reference clip of your own; that clip stays on
# your own disk and never enters the repository. The --ref-times below fit that reference; change them for yours.
set -e
. "$(dirname "$0")/env.sh"
V=${1:-v1}; ONLY=${2:-all}; D=$OUT/ad/$V; mkdir -p "$D"
E="crewcut motion --json --project $PROJECT --templates-dir $HERE/templates"
if [ "$ONLY" != sheets ]; then
  $E render video --comp Master --start 0 --end 17.5 --fps 60 --chunk 1.0 --jobs 6 --out "$D/crewcut-launch-$V.mp4" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print('clip',d['frames'],'/',d['expected_frames'],d['output'])"
fi
[ "$ONLY" = clip ] && exit 0
if [ -n "$REF" ]; then
  [ -f "$REF" ] || { echo "REF not found: $REF" >&2; exit 1; }
  refsheet(){ $E render compare --comp Master --ref "$REF" --times $2 --ref-times $3 --out "$D/compare-$1.jpg" >/dev/null; }
  refsheet beat2 "0.80,0.92,0.99,1.07,1.22,1.75,1.96,2.04,2.10,2.30" "3.21,3.33,3.40,3.48,3.63,4.16,4.37,4.45,4.51,4.71"
  refsheet beat3 "2.90,3.45,4.00,4.50,5.00,5.80,6.30,6.55" "5.30,5.75,6.60,7.20,7.80,8.60,10.00,11.30"
  refsheet beat4 "6.90,7.15,7.50,7.90,8.40,9.00,9.80" "11.80,12.05,12.50,13.10,13.80,15.20,16.00"
  refsheet beat5 "10.20,10.60,11.00,11.40,11.85" "16.40,16.80,17.10,17.40,17.60"
  refsheet beat6 "12.40,12.80,13.20,13.27,13.50,14.20,14.90" "17.80,18.00,18.30,18.33,18.60,19.40,20.10"
  refsheet beat7 "15.10,15.50,16.00,16.60,17.40" "20.30,20.50,20.80,21.20,21.90"
fi
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
