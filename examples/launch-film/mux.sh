#!/bin/bash
# Picture and sound together: the master (picture copied unchanged, AAC 256 kbit/s) and the web file (two-pass H.264
# 3.3 Mbit/s, AAC 192 kbit/s, under 8 MB), plus the poster frame and a loudness check.
#   bash mux.sh VERSION      (needs $OUT/ad/VERSION/crewcut-launch-VERSION.mp4 and $OUT/audio/mix.flac from sfx.py)
set -e
. "$(dirname "$0")/env.sh"
V=${1:-v1}; D=$OUT/ad/$V; CLIP=$D/crewcut-launch-$V.mp4; MIX=${MIX:-$OUT/audio/mix.flac}
[ -f "$CLIP" ] && [ -f "$MIX" ] || { echo "need $CLIP and $MIX" >&2; exit 1; }
ffmpeg -v error -y -i "$CLIP" -i "$MIX" -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 256k -ar 48000 \
  -movflags +faststart -shortest "$D/crewcut-launch-$V-sfx.mp4"
X264="-c:v libx264 -preset slow -b:v 3300k -maxrate 6000k -bufsize 8000k -pix_fmt yuv420p -profile:v high -level 4.2"
ffmpeg -v error -y -i "$CLIP" -an $X264 -pass 1 -passlogfile "$D/x264" -f mp4 /dev/null
ffmpeg -v error -y -i "$CLIP" -i "$MIX" -map 0:v:0 -map 1:a:0 $X264 -pass 2 -passlogfile "$D/x264" \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart -shortest "$D/crewcut-launch-web.mp4"
rm -f "$D"/x264*
ffmpeg -v error -y -i "$CLIP" -vf "select=eq(n\,87)" -frames:v 1 -q:v 2 "$D/poster.jpg"
# integrated loudness (I) should read about -14 LUFS, the true peak below -1 dBTP
for f in "$D/crewcut-launch-$V-sfx.mp4" "$D/crewcut-launch-web.mp4"; do
  echo "$(basename "$f"): $(du -h "$f" | cut -f1)"
  ffmpeg -nostats -i "$f" -map 0:a -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I|Peak):" | tr -s ' '
done
