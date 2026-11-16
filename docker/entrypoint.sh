#!/bin/bash
# Crewcut container start. Prepares the studio folder, installs the engine on the first start, checks everything
# once (doctor), then runs the command as the owner of the studio folder. Never as root.
set -euo pipefail

STUDIO=${CREWCUT_STUDIO:-/studio}
mkdir -p "$STUDIO/.crewcut/logs" "$STUDIO/.crewcut/home" /opt/engine

uid=$(stat -c %u "$STUDIO")
gid=$(stat -c %g "$STUDIO")
if [ "$uid" = "0" ]; then uid=1000; gid=1000; fi   # a folder Docker created as root: use the image's user
chown "$uid:$gid" "$STUDIO/.crewcut" "$STUDIO/.crewcut/logs" "$STUDIO/.crewcut/home" /opt/engine 2>/dev/null || true
export HOME="$STUDIO/.crewcut/home"

as_user() { setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"; }

if [ "$(id -u)" != "0" ]; then as_user() { "$@"; }; fi

# Engine: the one the user chose (Claude Code by default, Codex beta), from its official npm package, once.
mkdir -p /opt/engine/codex-home && chmod 700 /opt/engine/codex-home
chown "$uid:$gid" /opt/engine/codex-home 2>/dev/null || true
engine=$(as_user python3 -c "from crewcut import engines; print(engines.current_name())" 2>/dev/null || echo claude)
bin=claude; [ "$engine" = "codex" ] && bin=codex
if ! command -v "$bin" >/dev/null 2>&1 && [ "${CREWCUT_INSTALL_ENGINE:-1}" = "1" ]; then
  echo "crewcut: installing $engine (first start only)..."
  as_user crewcut engine install "$engine" > "$STUDIO/.crewcut/logs/engine-install.log" 2>&1 \
    || echo "crewcut: $engine could not be installed; see .crewcut/logs/engine-install.log in your studio folder."
fi

# Skills: visible to Claude Code in every folder.
as_user mkdir -p "$HOME/.claude/skills"
for d in /app/skills/*/; do
  [ -f "$d/SKILL.md" ] && as_user ln -sfn "$d" "$HOME/.claude/skills/$(basename "$d")"
done

# One check at start, with a tiny login call when the engine is logged in; in the background, the UI starts at once.
( as_user crewcut doctor --probe > "$STUDIO/.crewcut/logs/doctor.log" 2>&1 || true ) &

if [ "$(id -u)" = "0" ]; then
  exec setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
fi
exec "$@"
