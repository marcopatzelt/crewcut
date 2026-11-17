# Shared settings of the launch film scripts. Every script sources this file; override any value from the environment.
#   HERE     this folder (scripts, Blender scripts, templates/, assets/)
#   REPO     the Crewcut checkout (docs/brand/ has the Slate logo and the crew avatars)
#   WORK     the work folder on the rented machine: venv, project, plates, renders (default ./work)
#   OUT      plates and renders (default $WORK/out)
#   ASSETS   prepared PNG assets for the comp: icons, cards, word-reel backdrop (default $WORK/a, made by prep.sh)
#   PROJECT  the EffectCraft project file (default $WORK/p/ad.ecproj)
#   VENV     Python environment with Crewcut (`crewcut motion`), numpy, scipy and Pillow (made by setup.sh)
#   BLENDER  Blender 5.0.1 binary (setup.sh links /usr/local/bin/blender)
#   FONT_DIR the Manrope font files (setup.sh installs them there)
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=${REPO:-$(cd "$HERE/../.." && pwd)}
WORK=${WORK:-$PWD/work}
OUT=${OUT:-$WORK/out}
ASSETS=${ASSETS:-$WORK/a}
PROJECT=${PROJECT:-$WORK/p/ad.ecproj}
VENV=${VENV:-$WORK/venv}
BLENDER=${BLENDER:-blender}
FONT_DIR=${FONT_DIR:-/usr/share/fonts/truetype/manrope}
HDRI=${HDRI:-$WORK/hdri/kloofendal_48d_partly_cloudy_puresky_4k.hdr}
HDRI_URL=${HDRI_URL:-https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/kloofendal_48d_partly_cloudy_puresky_4k.hdr}
# the template parameters below are JSON strings with these paths inside: no spaces or quotes in them
case "$HERE|$WORK|$OUT|$ASSETS|$PROJECT" in
  *[[:space:]\"\']*) echo "launch-film: the folder paths must not contain spaces or quotes" >&2; exit 2 ;;
esac
[ -d "$VENV/bin" ] && export PATH="$VENV/bin:$PATH"
export WORK OUT ASSETS PROJECT
