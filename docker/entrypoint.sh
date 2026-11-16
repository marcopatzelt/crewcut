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

# Engine: the newest version of the one the user chose (Claude Code by default, Codex beta), installed next to the
# last good one and switched only after a smoke test (crewcut/engines/versions.py). The first start waits for it; later
# starts update in the background so the UI is there at once. Offline: the current version simply stays.
mkdir -p /opt/engine/codex-home /opt/engine/versions /opt/engine/current && chmod 700 /opt/engine/codex-home
chown -R "$uid:$gid" /opt/engine 2>/dev/null || true
engine=$(as_user python3 -c "from crewcut import engines; print(engines.current_name())" 2>/dev/null || echo claude)
if [ "${CREWCUT_INSTALL_ENGINE:-1}" = "1" ]; then
  if [ -e "/opt/engine/current/$engine" ]; then
    ( as_user crewcut engine update "$engine" > "$STUDIO/.crewcut/logs/engine-update.log" 2>&1 || true ) &
  else
    echo "crewcut: installing $engine (first start only)..."
    as_user crewcut engine update "$engine" > "$STUDIO/.crewcut/logs/engine-update.log" 2>&1 \
      || echo "crewcut: $engine could not be installed; see .crewcut/logs/engine-update.log in your studio folder."
  fi
fi

# Skills from other projects (Humanizer, MIT): the newest release from GitHub at every start, next to the last one,
# switched only when it is a valid skill (crewcut/extskills.py). Never part of the image or the repository.
mkdir -p /opt/engine/skills && chown "$uid:$gid" /opt/engine/skills 2>/dev/null || true
if [ "${CREWCUT_INSTALL_SKILLS:-1}" = "1" ]; then
  ( as_user crewcut skills update > "$STUDIO/.crewcut/logs/skills-update.log" 2>&1 || true ) &
fi

# The user's Claude Code settings: <studio>/.claude/ is Claude Code's own folder inside the container (settings.json,
# CLAUDE.md, skills/, agents/, commands/, MCP). Optional: your host's ~/.claude mounted read only at /host-claude is
# copied in once (never the login file). Crewcut itself comes as a plugin (--plugin-dir) and never edits these files.
as_user mkdir -p "$STUDIO/.claude"
[ -e "$HOME/.claude" ] || as_user ln -s "$STUDIO/.claude" "$HOME/.claude"
if [ -d /host-claude ] && [ ! -e "$STUDIO/.claude/.copied-from-host" ]; then
  for item in settings.json CLAUDE.md skills agents commands; do
    if [ -e "/host-claude/$item" ] && [ ! -e "$STUDIO/.claude/$item" ]; then as_user cp -r "/host-claude/$item" "$STUDIO/.claude/"; fi
  done
  as_user touch "$STUDIO/.claude/.copied-from-host"
fi
as_user crewcut plugin > /dev/null 2>&1 || echo "crewcut: the Claude Code plugin could not be built"

# One check at start, with a tiny login call when the engine is logged in; in the background, the UI starts at once.
( as_user crewcut doctor --probe > "$STUDIO/.crewcut/logs/doctor.log" 2>&1 || true ) &

if [ "$(id -u)" = "0" ]; then
  exec setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
fi
exec "$@"
