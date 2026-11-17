#!/bin/sh
# Web files of the meadow loop from the masters: VP9 WebM and H.264 MP4 (two-pass, no audio, faststart), 1920x1080 and
# a 540x960 portrait crop for phones; posters (frame 0) as WebP and JPEG.
#   encode.sh MASTER_DIR OUT_DIR      (MASTER_DIR holds master-day.mkv and master-dusk.mkv from loop.py)
# The files go to site/media/meadow/. Measured: about 2.2 MB per 1920 file, 0.9 MB per phone file.
set -eu
M=$1; O=$2; mkdir -p "$O"; cd "$O"
PH="crop=608:1080:656:0,scale=540:960:flags=lanczos"
enc() { # look size vf vp9_kbps x264_kbps level
  look=$1; size=$2; vf=$3; vb=$4; xb=$5; lvl=$6; in="$M/master-$look.mkv"; n="meadow-$look-$size"
  ffmpeg -hide_banner -loglevel error -y -i "$in" -vf "$vf" -an -c:v libvpx-vp9 -b:v ${vb}k -maxrate $((vb * 3 / 2))k -bufsize $((vb * 2))k \
    -g 120 -row-mt 1 -tile-columns 2 -deadline good -cpu-used 2 -pix_fmt yuv420p -pass 1 -passlogfile "p-$n" -f null -
  ffmpeg -hide_banner -loglevel error -y -i "$in" -vf "$vf" -an -c:v libvpx-vp9 -b:v ${vb}k -maxrate $((vb * 3 / 2))k -bufsize $((vb * 2))k \
    -g 120 -row-mt 1 -tile-columns 2 -deadline good -cpu-used 1 -pix_fmt yuv420p -pass 2 -passlogfile "p-$n" -cues_to_front 1 "$n.webm"
  ffmpeg -hide_banner -loglevel error -y -i "$in" -vf "$vf" -an -c:v libx264 -preset veryslow -b:v ${xb}k -maxrate $((xb * 3 / 2))k -bufsize $((xb * 2))k \
    -g 120 -profile:v high -level $lvl -pix_fmt yuv420p -pass 1 -passlogfile "x-$n" -f null -
  ffmpeg -hide_banner -loglevel error -y -i "$in" -vf "$vf" -an -c:v libx264 -preset veryslow -b:v ${xb}k -maxrate $((xb * 3 / 2))k -bufsize $((xb * 2))k \
    -g 120 -profile:v high -level $lvl -pix_fmt yuv420p -pass 2 -passlogfile "x-$n" -movflags +faststart -tag:v avc1 "$n.mp4"
  ffmpeg -hide_banner -loglevel error -y -i "$in" -vf "$vf" -frames:v 1 -pix_fmt rgb24 "$n.png"
  magick "$n.png" -quality 80 -define webp:method=6 "$n.webp"
  magick "$n.png" -strip -interlace Plane -sampling-factor 4:2:0 -quality 82 "$n.jpg"
  rm -f "$n.png" p-$n* x-$n*
}
for look in day dusk; do
  enc $look 1920 "null" 2150 2200 4.0 &
  enc $look phone "$PH" 850 950 3.1 &
done
wait
ls -l
