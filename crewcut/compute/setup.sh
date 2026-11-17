#!/bin/bash
# Crewcut setup on a rented GPU. Runs as root over SSH, right after the upload probe.
#
#   setup.sh --deadline <unix time> [--blender 5.0.1 | --blender none]
#
# --blender none: the job needs no Blender (for example the matting job); the Blender check and install are skipped.
#
# Exit 0 = SETUP_OK. Exit 2 = systematic problem (stop renting). Exit 3 = host problem (destroy, try the next offer).
#
# This machine never receives a key, a login or a recording. The watchdog deletes the machine at its deadline with
# the instance's own key (CONTAINER_API_KEY, which Vast puts into the container and which only works for this machine).
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
B=/opt/crewcut
DEADLINE=""
BLENDER_V=5.0.1

fail() {
  echo "SETUP_FAIL $1: $2"
  exit "$1"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --deadline) DEADLINE=$2; shift 2;;
    --blender) BLENDER_V=$2; shift 2;;
    *) fail 2 "unknown option $1";;
  esac
done
[ -n "$DEADLINE" ] || fail 2 "--deadline missing"
mkdir -p "$B" /work/out && chmod 700 "$B"

echo "== watchdog"
if ! { [ -f "$B/watchdog.pid" ] && kill -0 "$(cat "$B/watchdog.pid")" 2>/dev/null; }; then
  [ -f /tmp/crewcut-watchdog.sh ] && install -m 700 /tmp/crewcut-watchdog.sh "$B/watchdog.sh"
  [ -f "$B/watchdog.sh" ] || fail 2 "watchdog script missing"
  setsid nohup bash "$B/watchdog.sh" "$DEADLINE" > /dev/null 2>&1 < /dev/null &
  echo $! > "$B/watchdog.pid"
fi
echo "watchdog: running, deadline $(date -u -d "@$DEADLINE" '+%Y-%m-%d %H:%M UTC')"
if tr '\0' '\n' < /proc/1/environ 2> /dev/null | grep -q '^CONTAINER_API_KEY=.'; then
  echo "instance key for self-delete: present"
else
  echo "WARNING: no CONTAINER_API_KEY, the machine cannot delete itself (the local guard still does)"
fi

echo "== GPU"
nvidia-smi -L 2> /dev/null | head -8
nvidia-smi -L > /dev/null 2>&1 || fail 3 "no GPU visible (nvidia-smi)"

echo "== tools"
NEED=""
for t in rsync curl xz; do command -v "$t" > /dev/null 2>&1 || NEED="$NEED $t"; done
if [ -n "$NEED" ]; then
  apt-get update -qq > /dev/null 2>&1 || fail 3 "apt-get update"
  apt-get install -y -qq --no-install-recommends rsync curl ca-certificates xz-utils > /dev/null 2>&1 \
    || fail 3 "apt-get install tools"
fi

echo "== Blender"
if [ "$BLENDER_V" = none ]; then
  echo "blender: not needed for this job"
else
  if [ ! -x /opt/blender/blender ] && ! command -v blender > /dev/null 2>&1; then
    echo "not in the image: installing Blender $BLENDER_V to /opt/blender"
    apt-get install -y -qq --no-install-recommends libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libsm6 \
      libxkbcommon0 libegl1 libglu1-mesa fontconfig > /dev/null 2>&1 || fail 3 "apt-get install Blender libraries"
    SERIES=${BLENDER_V%.*}
    F="blender-$BLENDER_V-linux-x64.tar.xz"
    cd /opt || fail 3 "cd /opt"
    for U in "https://download.blender.org/release/Blender$SERIES" \
             "https://ftp.nluug.nl/pub/graphics/blender/release/Blender$SERIES" \
             "https://mirror.clarkson.edu/blender/release/Blender$SERIES"; do
      rm -rf "$F" "blender-$BLENDER_V-linux-x64" "blender-$BLENDER_V.sha256"
      curl -fsL --max-time 900 -o "$F" "$U/$F" || continue
      if curl -fsL --max-time 60 -o "blender-$BLENDER_V.sha256" "$U/blender-$BLENDER_V.sha256"; then
        grep " $F\$" "blender-$BLENDER_V.sha256" | sha256sum -c - > /dev/null 2>&1 || { echo "checksum wrong at $U"; continue; }
        echo "checksum ok"
      else
        echo "WARNING: no checksum file at $U"
      fi
      tar xJf "$F" && break
    done
    rm -f "$F" "blender-$BLENDER_V.sha256"
    [ -x "/opt/blender-$BLENDER_V-linux-x64/blender" ] || fail 3 "Blender download"
    rm -rf /opt/blender && mv "/opt/blender-$BLENDER_V-linux-x64" /opt/blender
    ln -sf /opt/blender/blender /usr/local/bin/blender
  fi
  BL=/opt/blender/blender
  [ -x "$BL" ] || BL=$(command -v blender)
  "$BL" --version 2> /dev/null | head -1 | grep -q Blender || fail 3 "Blender does not start"
  echo "blender: $("$BL" --version 2> /dev/null | head -1)"
fi

echo "== app"
if [ -d /app/templates/3d ]; then echo "app: present"; else echo "app: missing"; fi
echo "SETUP_OK"
