#!/usr/bin/env bash
# Start Crewcut. On the first run it creates .env and ./studio and asks once for the engine token (hidden input).
set -euo pipefail
cd "$(dirname "$0")"

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

if ! grep -q '^CLAUDE_CODE_OAUTH_TOKEN=..*' .env && ! grep -q '^ANTHROPIC_API_KEY=..*' .env; then
  echo "Crewcut runs on your own Claude plan. Run 'claude setup-token' on a computer with a browser,"
  echo "then paste the token here (the input stays hidden) and press Enter:"
  IFS= read -rs token; echo
  if [ ${#token} -lt 20 ]; then echo "That does not look like a token. Run 'claude setup-token' and try again."; exit 4; fi
  set_env CLAUDE_CODE_OAUTH_TOKEN "$token"
  token=""
fi

host=""
case "$(uname -s)" in
  Darwin) host=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true) ;;
  Linux) host=$(hostname -I 2>/dev/null | awk '{print $1}') ;;
esac
[ -n "$host" ] && set_env CREWCUT_LAN_HOST "$host"

docker compose up -d
url="http://localhost:${CREWCUT_PORT:-4747}"
echo "Crewcut is starting at $url (the first start installs the engine and takes a few minutes)."
if command -v open >/dev/null 2>&1; then open "$url"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 || true; fi
