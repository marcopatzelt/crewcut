#!/bin/bash
# One-time setup of a rented Linux GPU machine (tested image: nvidia/cuda:12.4.1-runtime-ubuntu22.04, run as root) for
# rebuilding the launch film. Installs runtime needs only: ffmpeg, rsvg-convert, Blender 5.0.1, the Manrope fonts, and
# a Python environment with Crewcut (for `crewcut motion`), numpy, scipy and Pillow. Nothing is compiled here.
#
#   bash setup.sh [effectcraft-cli archive (.tar.gz, .tar.xz or .zip)]
#
# effectcraft-cli (EffectCraft's headless renderer) comes from the archive given as the argument, or from
# $EFFECTCRAFT_CLI (a path to the binary). Crewcut's CI builds it from third_party/effectcraft; one way to get it:
#   docker create --name ec ghcr.io/marcopatzelt/crewcut-effectcraft:<tag> x && docker cp ec:/effectcraft-cli . && docker rm ec
# The tag is the one in docker/Dockerfile (ARG EFFECTCRAFT_IMAGE).
#
# Fonts: FONTS=/dir copies the Manrope files from that folder (the film used the static Manrope V5 OTFs, family
# "Manrope V5", which the templates name). Without FONTS, the static Manrope OTFs are downloaded from
# github.com/googlefonts/manrope (family "Manrope") and a fontconfig alias maps "Manrope V5" to them.
set -e
. "$(dirname "$0")/env.sh"
SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo
export DEBIAN_FRONTEND=noninteractive
ARCHIVE=$1
BLENDER_DIR=${BLENDER_DIR:-/opt/blender}
BLENDER_VERSION=5.0.1

echo "== packages"
$SUDO apt-get update -qq >/dev/null
$SUDO apt-get install -y -qq --no-install-recommends ca-certificates curl xz-utils unzip rsync \
  ffmpeg librsvg2-bin fontconfig python3 python3-pip python3-venv \
  libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libsm6 libxkbcommon0 libegl1 libglu1-mesa >/dev/null

echo "== effectcraft-cli"
if [ -n "$ARCHIVE" ]; then
  [ -f "$ARCHIVE" ] || { echo "archive not found: $ARCHIVE" >&2; exit 1; }
  $SUDO rm -rf /opt/effectcraft && $SUDO mkdir -p /opt/effectcraft
  case "$ARCHIVE" in
    *.zip) $SUDO unzip -q "$ARCHIVE" -d /opt/effectcraft ;;
    *) $SUDO tar -xf "$ARCHIVE" -C /opt/effectcraft ;;
  esac
  BIN=$(find /opt/effectcraft -type f -name effectcraft-cli | head -1)
elif [ -n "$EFFECTCRAFT_CLI" ]; then
  BIN=$EFFECTCRAFT_CLI
else
  BIN=$(command -v effectcraft-cli || true)
fi
[ -n "$BIN" ] && [ -f "$BIN" ] || { echo "effectcraft-cli missing: pass an archive or set EFFECTCRAFT_CLI" >&2; exit 1; }
$SUDO chmod +x "$BIN"
[ "$BIN" = /usr/local/bin/effectcraft-cli ] || $SUDO ln -sf "$BIN" /usr/local/bin/effectcraft-cli

echo "== Blender $BLENDER_VERSION"
if [ ! -x "$BLENDER_DIR/blender" ]; then
  T=$(mktemp -d)
  for u in https://download.blender.org/release/Blender5.0 https://ftp.nluug.nl/pub/graphics/blender/release/Blender5.0 \
           https://mirror.clarkson.edu/blender/release/Blender5.0; do
    curl -fsL -o "$T/b.tar.xz" "$u/blender-$BLENDER_VERSION-linux-x64.tar.xz" && break
  done
  [ -s "$T/b.tar.xz" ] || { echo "Blender download failed" >&2; exit 1; }
  $SUDO mkdir -p "$BLENDER_DIR" && $SUDO tar -xJf "$T/b.tar.xz" -C "$BLENDER_DIR" --strip-components=1
  rm -rf "$T"
fi
$SUDO ln -sf "$BLENDER_DIR/blender" /usr/local/bin/blender

echo "== fonts"
$SUDO mkdir -p "$FONT_DIR"
if [ -n "$FONTS" ]; then
  $SUDO cp "$FONTS"/*.[ot]tf "$FONT_DIR"/
else
  for w in regular medium semibold bold extrabold; do
    $SUDO curl -fsSL -o "$FONT_DIR/manrope-$w.otf" "https://raw.githubusercontent.com/googlefonts/manrope/master/fonts/otf/manrope-$w.otf"
  done
  $SUDO tee /etc/fonts/conf.d/60-manrope-v5.conf >/dev/null <<'XML'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><alias><family>Manrope V5</family><prefer><family>Manrope</family></prefer></alias></fontconfig>
XML
  echo "note: installed Manrope (family 'Manrope'); for the exact film look pass FONTS with the Manrope V5 OTFs"
fi
$SUDO fc-cache -f >/dev/null

echo "== Python ($VENV)"
python3 -m pip install -q --upgrade uv >/dev/null 2>&1 || python3 -m pip install -q --break-system-packages uv
python3 -m uv venv -q --python 3.12 "$VENV"
python3 -m uv pip install -q --python "$VENV/bin/python" -e "$REPO" numpy scipy pillow

echo "== check"
"$VENV/bin/crewcut" motion --help >/dev/null && echo "crewcut motion: ok"
effectcraft-cli --help >/dev/null 2>&1 && echo "effectcraft-cli: ok ($BIN)"
blender --version | head -1
ffmpeg -version | head -1
fc-list | grep -ci manrope | sed 's/^/manrope font files: /'
nproc; free -g | head -2
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "no NVIDIA GPU visible"
echo SETUP_DONE
