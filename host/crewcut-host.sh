#!/usr/bin/env bash
# Crewcut's host helper: the one thing the container cannot do itself. It runs next to Crewcut on your computer
# (./start.sh starts it), and does exactly one job: when you press "Connect YouTube" in Crewcut, it starts your own
# Claude Code with Claude in Chrome (claude --chrome) on the fixed prompt in host/prompts/youtube-setup.md, so Claude
# sets up the YouTube Data API in your Google Cloud console while you watch. Afterwards it moves the downloaded client
# file to studio/config/youtube-client.json. Uploads never go through the browser: always the API.
#
# It never runs a command or a prompt it is sent. A request is a small file in studio/.crewcut/host/requests/ that names
# the job, a time and the checksum of the prompt; it must carry an HMAC signature made with CREWCUT_HOST_TOKEN (in
# .env, never inside the studio folder). Unsigned, old (over two minutes), repeated or mismatching requests are deleted
# and reported. No network port.
#
#   host/crewcut-host.sh            watch (started by ./start.sh)
#   host/crewcut-host.sh --once     handle the requests that are there now, then stop (tests)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
STUDIO="${CREWCUT_STUDIO_DIR:-$ROOT/studio}"
BOX="$STUDIO/.crewcut/host"
PROMPT="$HERE/prompts/youtube-setup.md"
MAX_AGE="${CREWCUT_HOST_MAX_AGE:-120}"
DOWNLOADS="${CREWCUT_DOWNLOADS:-$HOME/Downloads}"
VERSION=1

if [ -z "${CREWCUT_HOST_TOKEN:-}" ] && [ -f "$ROOT/.env" ]; then
  CREWCUT_HOST_TOKEN=$(grep '^CREWCUT_HOST_TOKEN=' "$ROOT/.env" | head -1 | cut -d= -f2- || true)
fi
[ -n "${CREWCUT_HOST_TOKEN:-}" ] || { echo "crewcut-host: no CREWCUT_HOST_TOKEN (run ./start.sh once)"; exit 2; }
mkdir -p "$BOX/requests" "$BOX/runs" "$BOX/used"

sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum | cut -d' ' -f1; else shasum -a 256 | cut -d' ' -f1; fi; }
hmac() { printf '%s' "$1" | openssl dgst -sha256 -hmac "$CREWCUT_HOST_TOKEN" -r | cut -d' ' -f1; }
field() { sed -n "s/^$1=//p" "$2" | head -1; }
say() {  # a status line the container shows in the chat: say <id> <state> <text>
  printf '{"id":"%s","state":"%s","text":"%s","at":%s}\n' "$1" "$2" "$3" "$(date +%s)" >> "$BOX/status.jsonl"
}
now() { date +%s; }

beat() {
  local claude chrome
  claude=$(command -v claude || true)
  chrome=$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || command -v microsoft-edge \
    || { [ -d "/Applications/Google Chrome.app" ] && echo "/Applications/Google Chrome.app"; } || true)
  printf '{"version":%s,"pid":%s,"at":%s,"claude":"%s","chrome":"%s"}\n' "$VERSION" "$$" "$(now)" "$claude" "$chrome" \
    > "$BOX/helper.json.tmp" && mv "$BOX/helper.json.tmp" "$BOX/helper.json"
}

open_terminal() {  # run a command in a visible terminal window, so the person sees Claude and can answer it
  local cmd="$1"
  case "$(uname -s)" in
    Darwin) osascript -e "tell application \"Terminal\" to do script \"$cmd\"" >/dev/null ;;
    *)
      if command -v x-terminal-emulator >/dev/null 2>&1; then x-terminal-emulator -e bash -lc "$cmd" &
      elif command -v gnome-terminal >/dev/null 2>&1; then gnome-terminal -- bash -lc "$cmd" &
      elif command -v konsole >/dev/null 2>&1; then konsole -e bash -lc "$cmd" &
      else return 1; fi ;;
  esac
}

collect_client() {  # wait up to 30 minutes for client_secret_*.json in Downloads, newer than the start of the run
  local id="$1" since="$2" f dest="$STUDIO/config/youtube-client.json" end=$(( $(now) + ${CREWCUT_HOST_COLLECT_S:-1800} ))
  while [ "$(now)" -lt "$end" ]; do
    for f in "$DOWNLOADS"/client_secret_*.json; do
      [ -f "$f" ] || continue
      [ "$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f")" -ge "$since" ] || continue
      if grep -q '"installed"' "$f" && grep -q '"client_id"' "$f"; then
        mkdir -p "$STUDIO/config"
        install -m 600 "$f" "$dest" && rm -f "$f"
        say "$id" "done" "The YouTube client file is in place."
        return 0
      fi
    done
    sleep 3
  done
  say "$id" failed "No client file arrived in the Downloads folder within 30 minutes."
  return 1
}

run_setup() {
  local id="$1" since cmd
  since=$(now)
  command -v claude >/dev/null 2>&1 || { say "$id" failed "Claude Code is not installed on this computer."; return 1; }
  cmd="cd '$HERE' && claude --chrome --name crewcut-youtube-setup --allowedTools 'mcp__claude-in-chrome' --disallowedTools Bash Write Edit NotebookEdit WebFetch WebSearch -- \"\$(cat '$PROMPT')\""
  if [ "${CREWCUT_HOST_HEADLESS:-0}" = "1" ] || ! open_terminal "$cmd"; then
    # no terminal window available: run without a screen and keep the event stream for the container
    ( cd "$HERE" && claude --chrome -p "$(cat "$PROMPT")" --output-format stream-json --verbose \
        --allowedTools 'mcp__claude-in-chrome' --disallowedTools Bash Write Edit NotebookEdit WebFetch WebSearch \
        > "$BOX/runs/$id.jsonl" 2>&1 || true ) &
  fi
  say "$id" running "Claude is setting up the YouTube API in your Chrome. Sign in there when Google asks."
  ( collect_client "$id" "$since" || true ) &
}

handle() {
  local f="$1" kind id at nonce psha sig want
  kind=$(field kind "$f"); id=$(field id "$f"); at=$(field at "$f"); nonce=$(field nonce "$f")
  psha=$(field prompt_sha256 "$f"); sig=$(field sig "$f")
  rm -f "$f"
  case "$id" in ''|*[!A-Za-z0-9-]*) echo "crewcut-host: rejected a request without a valid id"; return 0 ;; esac
  want=$(hmac "kind=$kind;id=$id;at=$at;nonce=$nonce;prompt_sha256=$psha")
  if [ -z "$sig" ] || [ "$sig" != "$want" ]; then say "$id" rejected "The request was not signed by this Crewcut."; return 0; fi
  case "$at" in ''|*[!0-9]*) say "$id" rejected "The request has no valid time."; return 0 ;; esac
  if [ $(( $(now) - at )) -gt "$MAX_AGE" ] || [ "$at" -gt $(( $(now) + 30 )) ]; then say "$id" rejected "The request is too old. Press the button again."; return 0; fi
  if [ -e "$BOX/used/$nonce" ]; then say "$id" rejected "This request was used before."; return 0; fi
  touch "$BOX/used/$nonce"
  if [ "$kind" != "youtube-setup" ]; then say "$id" rejected "Unknown job: $kind."; return 0; fi
  if [ "$psha" != "$(sha256 < "$PROMPT")" ]; then
    say "$id" rejected "The setup prompt of this helper differs from Crewcut's. Update the repository (git pull) and restart."
    return 0
  fi
  run_setup "$id"
}

once() { local f; for f in "$BOX"/requests/*.req; do [ -f "$f" ] && handle "$f"; done; beat; }

if [ "${1:-}" = "--once" ]; then once; exit 0; fi
echo "crewcut-host: watching $BOX/requests (Ctrl+C to stop)"
trap 'rm -f "$BOX/helper.json"; exit 0' INT TERM
while true; do once; sleep 1; done
