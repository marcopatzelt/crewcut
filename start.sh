#!/usr/bin/env bash
# Start Crewcut. On the first run it creates .env and ./studio. Claude is connected in the window that opens
# ("Connect Claude"); only on a server without a screen does it ask for a token (hidden input).
# When the server answers, Crewcut opens in its own app window (host/open-app.sh).
#   ./start.sh              start, then open the app window
#   ./start.sh --no-open    start and only print the address
# CREWCUT_OPEN=app|browser|none picks how it opens (default app: an app window of Chrome, Edge, Brave, Arc or Chromium).
set -euo pipefail
cd "$(dirname "$0")"

open_args=()
for arg in "$@"; do
  case "$arg" in
    --no-open) open_args+=(--no-open) ;;
    -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (./start.sh --help)"; exit 2 ;;
  esac
done

command -v docker >/dev/null 2>&1 || {
  echo "Docker is not installed. Install Docker Desktop, Colima or Docker Engine, then run ./start.sh again."; exit 1; }

[ -f .env ] || { cp .env.example .env; chmod 600 .env; }
mkdir -p studio import

set_env() {  # set_env KEY VALUE: replace one line in .env without ever printing the value
  local tmp; tmp=$(mktemp)
  grep -v "^$1=" .env > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  mv "$tmp" .env; chmod 600 .env
}

# Claude: normally "Connect Claude" in the window that opens (the CLI's own sign-in, no terminal). Only on a server
# without a screen does this ask once for a token from `claude setup-token` (hidden input); Enter skips it.
screen=""
case "$(uname -s)" in
  Darwin|MINGW*|MSYS*|CYGWIN*) screen=1 ;;
  *) { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ] || grep -qi microsoft /proc/version 2>/dev/null; } && screen=1 ;;
esac
if ! grep -q '^CLAUDE_CODE_OAUTH_TOKEN=..*' .env && ! grep -q '^ANTHROPIC_API_KEY=..*' .env; then
  if [ -n "$screen" ] || [ ! -t 0 ]; then
    echo "Claude is not connected yet: press Connect Claude in Crewcut once it opens."
  else
    echo "No screen here. Either open Crewcut in a browser later and press Connect Claude, or paste a token from"
    echo "'claude setup-token' now (the input stays hidden). Press Enter to skip:"
    IFS= read -rs token; echo
    if [ -n "$token" ]; then
      if [ ${#token} -lt 20 ]; then echo "That does not look like a token. Run 'claude setup-token' and try again."; exit 4; fi
      set_env CLAUDE_CODE_OAUTH_TOKEN "$token"
    fi
    token=""
  fi
fi

# The host helper's key: it signs the one request the helper accepts ("set up YouTube in my Chrome").
if ! grep -q '^CREWCUT_HOST_TOKEN=..*' .env; then
  set_env CREWCUT_HOST_TOKEN "$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
fi

host=""
case "$(uname -s)" in
  Darwin) host=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true) ;;
  Linux) host=$(hostname -I 2>/dev/null | awk '{print $1}') ;;
esac
[ -n "$host" ] && set_env CREWCUT_LAN_HOST "$host"

docker compose up -d

# The host helper (host/crewcut-host.sh): one job, signed requests only, no network port. One copy at a time.
studio_dir=$(grep '^CREWCUT_STUDIO_DIR=' .env | tail -1 | cut -d= -f2- || true)
studio_dir="${studio_dir:-$PWD/studio}"
mkdir -p "$studio_dir/.crewcut/host" "$studio_dir/.crewcut/logs"
pidfile="$studio_dir/.crewcut/host/helper.pid"
if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then kill "$(cat "$pidfile")" 2>/dev/null || true; fi
CREWCUT_STUDIO_DIR="$studio_dir" nohup host/crewcut-host.sh > "$studio_dir/.crewcut/logs/host.log" 2>&1 &
echo $! > "$pidfile"
port="${CREWCUT_PORT:-$(grep '^CREWCUT_PORT=' .env | tail -1 | cut -d= -f2- || true)}"
url="http://localhost:${port:-4747}"
echo "Crewcut is starting at $url (the first start installs the engine and takes a few minutes)."
host/open-app.sh "${open_args[@]+"${open_args[@]}"}" "$url" || true
