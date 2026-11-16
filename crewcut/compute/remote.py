"""What runs on the rented machine: the watchdog (started by Vast's onstart hook and checked again by setup.sh) and
the setup script. Both are plain bash; neither ever receives a key.
"""

from __future__ import annotations

from pathlib import Path

SETUP_REMOTE = "/tmp/crewcut-setup.sh"
WATCHDOG_REMOTE = "/tmp/crewcut-watchdog.sh"

# Delete-safeguard 2 of 3: deletes this instance at its deadline, even when the studio is offline or crashed.
# The instance key goes to curl on stdin (-K -), never as an argument and never into a log.
WATCHDOG = r"""#!/bin/bash
# Crewcut watchdog: deletes this rented machine at its deadline (unix time in $1, or "now").
D=${1:-0}; [ "$D" = now ] && D=0
L=/opt/crewcut/watchdog.log
mkdir -p /opt/crewcut
command -v curl > /dev/null 2>&1 || (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  curl ca-certificates) > /dev/null 2>&1
while [ "$(date +%s)" -lt "$D" ]; do sleep 20; done
E=$(tr '\0' '\n' < /proc/1/environ 2> /dev/null)
ID=${CONTAINER_ID:-$(sed -n 's/^CONTAINER_ID=//p' <<< "$E" | head -1)}
[ -n "$ID" ] || ID=$(sed -n 's/^VAST_CONTAINERLABEL=C\.//p' <<< "$E" | head -1)
K=${CONTAINER_API_KEY:-$(sed -n 's/^CONTAINER_API_KEY=//p' <<< "$E" | head -1)}
echo "$(date -u +%FT%TZ) deadline reached, deleting instance ${ID:-unknown}" >> "$L"
for i in 1 2 3 4 5; do
  printf 'header = "Authorization: Bearer %s"\n' "$K" \
    | curl -s -m 30 -K - -X DELETE "https://console.vast.ai/api/v0/instances/$ID/" >> "$L" 2>&1
  echo >> "$L"
  sleep 30
done
"""

# Before the probe: rsync must exist on the machine (the fallback CUDA image does not have it).
PREPARE = ("command -v rsync > /dev/null 2>&1 || (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install "
           "-y -qq rsync) > /dev/null 2>&1; command -v rsync > /dev/null 2>&1 && echo ok")


def onstart(deadline: float) -> str:
    """The onstart hook given to Vast at rent time: writes and starts the watchdog before we even reach SSH."""
    d = int(deadline)
    return ("mkdir -p /opt/crewcut && cat > /opt/crewcut/watchdog.sh <<'CREWCUT_EOF'\n" + WATCHDOG + "CREWCUT_EOF\n"
            "chmod 700 /opt/crewcut/watchdog.sh\n"
            "if ! { [ -f /opt/crewcut/watchdog.pid ] && kill -0 \"$(cat /opt/crewcut/watchdog.pid)\" 2> /dev/null; }; "
            f"then setsid nohup bash /opt/crewcut/watchdog.sh {d} > /dev/null 2>&1 < /dev/null & "
            "echo $! > /opt/crewcut/watchdog.pid; fi\n")


def setup_file() -> Path:
    return Path(__file__).with_name("setup.sh")


def write_watchdog(folder: Path) -> Path:
    p = Path(folder) / "crewcut-watchdog.sh"
    p.write_text(WATCHDOG, encoding="utf-8")
    p.chmod(0o700)
    return p
