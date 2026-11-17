#!/bin/sh
# Web files of the 4K meadow loop (frames from web.sh: FRAMES/<light>/meadow_0001.jpg .. meadow_0240.jpg, 30 fps).
#   encode_web.sh FRAMES OUT
# The day light (the page uses it in light and dark mode): AV1 (SVT-AV1, the main source) at 3840 and 2560 px and a 1080 x 1920 portrait crop for
# phones; H.264 at 2560 px and for phones (browsers without AV1, Safari on most Macs); no audio, faststart.
# Posters (frame 1): WebP at 3840, 2560 and 1920 px and for phones, JPEG at 2560 px and for phones.
set -eu
F=$1; O=$2; mkdir -p "$O"
PH="crop=1215:2160:1312:0,scale=1080:1920:flags=lanczos"     # the portrait crop from the middle of the frame
DRI=${DRI:-/dev/dri/renderD128}; HW=0                                 # VAAPI: a one-frame test encode decides
[ -e "$DRI" ] && ffmpeg -hide_banner -loglevel error -vaapi_device "$DRI" -f lavfi -i color=c=green:s=256x256:d=0.1 -frames:v 1 \
  -vf format=nv12,hwupload -c:v av1_vaapi -f null - 2>/dev/null && HW=1
echo "encoder: $([ "$HW" = 1 ] && echo "GPU (VAAPI)" || echo "CPU (SVT-AV1, x264)")"
for L in ${LIGHTS:-day}; do
  IN="$F/$L/meadow_%04d.jpg"; n="$O/meadow-$L"
  # grass that moves everywhere is the hardest picture for a codec: fixed bit rates keep each file's size known.
  # The GPU encodes when VAAPI can (AV1 and H.264 in hardware, minutes on a laptop), else SVT-AV1 preset 8 and x264.
  av1() { if [ "$HW" = 1 ]; then ffmpeg -hide_banner -loglevel error -y -vaapi_device "$DRI" -framerate 30 -i "$IN" -vf "$1,format=nv12,hwupload" \
            -an -c:v av1_vaapi -rc_mode VBR -b:v "$2" -maxrate "$3" -g 120 -movflags +faststart "$4"
          else ffmpeg -hide_banner -loglevel error -y -framerate 30 -i "$IN" -vf "$1,format=yuv420p" -an -c:v libsvtav1 -preset 8 \
            -b:v "$2" -g 120 -svtav1-params rc=1:tune=0 -movflags +faststart "$4"; fi; }
  avc() { if [ "$HW" = 1 ]; then ffmpeg -hide_banner -loglevel error -y -vaapi_device "$DRI" -framerate 30 -i "$IN" -vf "$1,format=nv12,hwupload" \
            -an -c:v h264_vaapi -rc_mode VBR -b:v "$2" -maxrate "$3" -g 120 -profile:v high -movflags +faststart "$4"
          else ffmpeg -hide_banner -loglevel error -y -framerate 30 -i "$IN" -vf "$1" -an -c:v libx264 -preset medium -crf 20 \
            -maxrate "$3" -bufsize "$3" -g 120 -profile:v high -pix_fmt yuv420p -tag:v avc1 -movflags +faststart "$4"; fi; }
  av1 "scale=3840:2160" 14M 20M "$n-3840.av1.mp4"
  av1 "scale=2560:1440:flags=lanczos" 8M 12M "$n-2560.av1.mp4"
  av1 "$PH" 4M 6M "$n-phone.av1.mp4"
  avc "scale=2560:1440:flags=lanczos" 12M 18M "$n-2560.h264.mp4"
  avc "$PH" 6M 9M "$n-phone.h264.mp4"
  ffmpeg -hide_banner -loglevel error -y -i "$F/$L/meadow_0001.jpg" -vf "scale=3840:2160" "$n-poster.png"
  ffmpeg -hide_banner -loglevel error -y -i "$F/$L/meadow_0001.jpg" -vf "$PH" "$n-poster-phone.png"
  magick "$n-poster.png" -quality 82 -define webp:method=6 "$n-3840.webp"
  magick "$n-poster.png" -resize 2560x -quality 82 -define webp:method=6 "$n-2560.webp"
  magick "$n-poster.png" -resize 1920x -quality 82 -define webp:method=6 "$n-1920.webp"
  magick "$n-poster.png" -resize 2560x -strip -interlace Plane -sampling-factor 4:2:0 -quality 84 "$n-2560.jpg"
  magick "$n-poster-phone.png" -quality 82 -define webp:method=6 "$n-phone.webp"
  magick "$n-poster-phone.png" -strip -interlace Plane -sampling-factor 4:2:0 -quality 84 "$n-phone.jpg"
  rm -f "$n-poster.png" "$n-poster-phone.png"
done
ls -l "$O"
