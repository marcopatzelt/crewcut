#!/bin/bash
# The web meadow, rendered on one rented RTX 4090 from examples/launch-film/meadow3d.py: a still, higher and wider camera,
# 3840 x 2160, a seamless 8 s wind loop at 30 fps (240 frames, frame 241 = frame 1). The page uses the day light in
# light and dark mode; a sunset light (DUSK) is kept here as an option, it is not on the page.
#   bash web.sh hdri            the two CC0 skies from Poly Haven
#   bash web.sh stills          framing tests at 1920 x 1080, 32 samples, in $W/stills (one Blender session per light)
#   bash web.sh loop day|dusk   the 240 frames in $W/out/<light>, JOBS Blender processes side by side (default 3, at most 4)
# Camera and light come from the variables below; the measured choice for the page is the default.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPT=${SCRIPT:-$HERE/meadow3d.py}
BLENDER=${BLENDER:-/root/blender-5.0.1-linux-x64/blender}
W=${W:-/root/web}; mkdir -p "$W/hdri" "$W/out" "$W/stills"
DAY_HDRI=$W/hdri/kloofendal_48d_partly_cloudy_puresky_4k.hdr
DUSK_HDRI=$W/hdri/${DUSK_SKY:-industrial_sunset_02_puresky}_4k.hdr
CAM="--cam-z ${CAMZ:-0.8} --lens ${LENS:-24} --shift-y ${SHIFT:--0.07} --fstop ${FSTOP:-8} --focus ${FOCUS:-9}"
COMMON="--field wide --loop 240 --fps 30 --wind-speed ${WIND:-0.45} --res 3840x2160"
DAY="--hdri $DAY_HDRI --hdri-rot ${DAY_ROT:-25} --exposure=${DAY_EXP:-0.6} --haze ${DAY_HAZE:-140} --haze-color ${DAY_HAZEC:-0.62,0.70,0.80}"
DUSK="--hdri $DUSK_HDRI --sun-match=${DUSK_AZ:-28} --sun-energy ${DUSK_SUN:-45} --sun-color ${DUSK_SUNC:-1.0,0.5,0.22} --exposure=${DUSK_EXP:--1.65} --sky-grade ${DUSK_GRADE:-0.24,0.32,0.72} --haze ${DUSK_HAZE:-110} --haze-color ${DUSK_HAZEC:-0.95,0.58,0.32}"
bl() { "$BLENDER" -b --factory-startup --python "$SCRIPT" -- "$@" 2>&1 | grep -E "Error|Traceback|line [0-9]|DONE|SUN_MATCH|Time:" | grep -v HIPEW || true; }
case "$1" in
  hdri)
    for n in kloofendal_48d_partly_cloudy_puresky ${DUSK_SKY:-industrial_sunset_02_puresky}; do
      [ -s "$W/hdri/${n}_4k.hdr" ] || curl -fsSL -o "$W/hdri/${n}_4k.hdr" "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/${n}_4k.hdr"
    done; ls -l "$W/hdri" ;;
  stills)
    G_DAY=${G_DAY:-'[{"name":"day_a205","cam_z":0.8,"lens":24,"shift_y":-0.07,"hdri_rot":205},{"name":"day_a25","hdri_rot":25},{"name":"day_a115","hdri_rot":115},{"name":"day_a295","hdri_rot":295},{"name":"day_b205","cam_z":1.2,"lens":20,"shift_y":-0.07,"hdri_rot":205},{"name":"day_c205","cam_z":0.55,"lens":28,"shift_y":-0.06}]'}
    G_DUSK=${G_DUSK:-'[{"name":"dusk_a","cam_z":0.8,"lens":24,"shift_y":-0.07},{"name":"dusk_b","cam_z":1.2,"lens":20,"shift_y":-0.07}]'}
    bl $COMMON $CAM $DAY --half --samples 32 --out "$W/stills" --grid "$G_DAY" --exposures="${DAY_EXPS:-0.3,0.6}" &
    bl $COMMON $CAM $DUSK --half --samples 32 --out "$W/stills" --grid "$G_DUSK" --exposures="${DUSK_EXPS:-0.5,1.0,1.5,2.0}" &
    wait; ls "$W/stills" | wc -l ;;
  loop)
    L=$2; case "$L" in day) LIGHT=$DAY ;; dusk) LIGHT=$DUSK ;; *) echo "loop day|dusk" >&2; exit 2 ;; esac
    # every process takes the next frame nobody has started (Blender's placeholders), so a crashed or late process
    # never leaves a gap; run the same command again to fill gaps. About 5.5 GB of GPU memory per process: 4 at most.
    J=${JOBS:-3}; mkdir -p "$W/out/$L"
    for k in $(seq 1 "$J"); do
      bl $COMMON $CAM $LIGHT --samples ${SAMPLES:-64} --out "$W/out/$L" --frames 1-240 > "$W/out/${L}_$k.log" 2>&1 &
      sleep 20
    done
    wait; ls "$W/out/$L" | wc -l ;;
  *) sed -n 2,7p "$0"; exit 2 ;;
esac
