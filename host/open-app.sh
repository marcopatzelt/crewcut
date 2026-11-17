#!/usr/bin/env bash
# Opens Crewcut in its own app window once the server answers. ./start.sh calls it; `crewcut open` does the same in
# Python (crewcut/opener.py), so both behave alike.
#
#   host/open-app.sh [--no-open] [URL]          URL defaults to http://localhost:${CREWCUT_PORT:-4747}
#
# CREWCUT_OPEN picks how: app (default) an app window of Chrome, Edge, Brave, Arc or Chromium with your own browser
# profile (no fresh profile, so no first-run dialogs); browser a normal tab of the default browser; none only prints
# the address. Without a Chromium-based browser, app falls back to the default browser.
# CREWCUT_OPEN_TIMEOUT: seconds to wait for the server (default 900: the first start installs the engine).
set -uo pipefail

mode="${CREWCUT_OPEN:-app}"
url=""
for arg in "$@"; do
  case "$arg" in
    --no-open) mode=none ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "open-app: unknown option $arg" >&2; exit 2 ;;
    *) url="$arg" ;;
  esac
done
url="${url:-http://localhost:${CREWCUT_PORT:-4747}}"
case "$mode" in
  app|browser|none) ;;
  *) echo "open-app: CREWCUT_OPEN must be app, browser or none (not '$mode'); using app" >&2; mode=app ;;
esac

echo "Crewcut: $url"
[ "$mode" = none ] && exit 0

answers() {
  if command -v curl >/dev/null 2>&1; then curl -fsS -o /dev/null --max-time 3 "$1/" 2>/dev/null
  elif command -v wget >/dev/null 2>&1; then wget -q -O /dev/null -T 3 "$1/" 2>/dev/null
  else return 0; fi  # nothing to ask with: open at once, the page retries by itself
}

timeout="${CREWCUT_OPEN_TIMEOUT:-900}"
if ! answers "$url"; then
  echo "Waiting for Crewcut to answer, then it opens in its own window (the first start takes a few minutes)..."
  start=$(date +%s)
  until answers "$url"; do
    if [ $(( $(date +%s) - start )) -ge "$timeout" ]; then
      echo "Crewcut did not answer within $(( timeout / 60 )) minutes. Open $url when it is up; 'docker compose logs -f' shows what it is doing."
      exit 1
    fi
    sleep 2
  done
fi

detach() { nohup "$@" >/dev/null 2>&1 </dev/null & }

windows=""
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) windows=1 ;;
  Linux) grep -qi microsoft /proc/version 2>/dev/null && windows=1 ;;
esac

# Windows (Git Bash or WSL): Edge is always there.
if [ -n "$windows" ] && command -v cmd.exe >/dev/null 2>&1; then
  if [ "$mode" = app ]; then MSYS_NO_PATHCONV=1 cmd.exe /c start "" msedge "--app=$url" >/dev/null 2>&1 && exit 0; fi
  MSYS_NO_PATHCONV=1 cmd.exe /c start "" "$url" >/dev/null 2>&1 && exit 0
  echo "Open $url in your browser."; exit 0
fi

if [ "$(uname -s)" = Darwin ]; then
  if [ "$mode" = app ]; then
    for app in "Google Chrome" "Microsoft Edge" "Brave Browser" "Arc" "Chromium"; do
      if [ -d "/Applications/$app.app" ] || [ -d "$HOME/Applications/$app.app" ]; then
        open -na "$app" --args --app="$url" --window-size=1440,900 && exit 0
      fi
    done
  fi
  open "$url" && exit 0
  echo "Open $url in your browser."; exit 0
fi

# Linux and the rest: only with a screen (not over ssh, not inside a container).
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  echo "No screen here. Open $url in a browser on this computer."; exit 0
fi
if [ "$mode" = app ]; then
  # The default browser first when it can make app windows, then the others in a fixed order.
  default=$(xdg-settings get default-web-browser 2>/dev/null || true)
  candidates="google-chrome google-chrome-stable chromium chromium-browser microsoft-edge microsoft-edge-stable brave-browser brave"
  case "$default" in
    *google-chrome*) candidates="google-chrome google-chrome-stable $candidates" ;;
    *chromium*) candidates="chromium chromium-browser $candidates" ;;
    *edge*) candidates="microsoft-edge microsoft-edge-stable $candidates" ;;
    *brave*) candidates="brave-browser brave $candidates" ;;
  esac
  for bin in $candidates; do
    if command -v "$bin" >/dev/null 2>&1; then detach "$bin" --app="$url"; exit 0; fi
  done
  if command -v flatpak >/dev/null 2>&1; then
    for id in com.google.Chrome org.chromium.Chromium com.microsoft.Edge com.brave.Browser; do
      if flatpak info "$id" >/dev/null 2>&1; then detach flatpak run "$id" --app="$url"; exit 0; fi
    done
  fi
fi
if command -v xdg-open >/dev/null 2>&1; then detach xdg-open "$url"; exit 0; fi
echo "Open $url in your browser."
