#!/bin/bash
# Crewcut container start. Prepares the studio folder, installs the engine on the first start, checks everything
# once (doctor), then runs the command as the user who owns the studio folder on the host.
set -euo pipefail

STUDIO=${CREWCUT_STUDIO:-/studio}
mkdir -p /opt/engine
mkdir -p "$STUDIO/.crewcut/logs" "$STUDIO/.crewcut/home" 2>/dev/null || true   # a folder nobody may write: see below

# Who runs Crewcut: the owner of the studio folder, so every file the crew writes belongs to you on the host.
# - Docker on Linux (rootful), Docker Desktop and OrbStack on a Mac: the folder's owner (1000, 501, ...).
# - Rootless Docker or Podman: your host user is root (0) inside the container, and root here is an ordinary user on
#   the host (/proc/self/uid_map does not map 0 to 0). Then Crewcut runs as 0, which is you; Claude Code's permission
#   bypass refuses root unless IS_SANDBOX=1 says it runs in a sandbox, which this container is.
# - A folder Docker created itself (owned by root on a rootful host): the image's user 1000, as before.
# Whoever it is must be able to write the folder; otherwise root takes over (the same sandbox rule), and if even root
# cannot, the container stops with one line that says why.
owner_uid=$(stat -c %u "$STUDIO")
owner_gid=$(stat -c %g "$STUDIO")
host_root=$(awk '$1 == 0 { print $2; exit }' /proc/self/uid_map 2>/dev/null || echo 0)
if [ "$(id -u)" != "0" ]; then
  uid=$(id -u); gid=$(id -g)                        # started with --user: stay that user
elif [ "$owner_uid" != "0" ]; then
  uid=$owner_uid; gid=$owner_gid
elif [ "${host_root:-0}" != "0" ]; then
  uid=0; gid=0                                       # rootless: root in here is you on the host
else
  uid=1000; gid=1000                                 # rootful, a folder Docker made as root: the image's user
  # Docker just made it (nothing in it but our own folder): it becomes the image user's, as ./start.sh would make it
  if [ -z "$(ls -A "$STUDIO" 2>/dev/null | grep -vx '.crewcut')" ]; then chown "$uid:$gid" "$STUDIO" 2>/dev/null || true; fi
fi

as_user() { setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"; }
if [ "$(id -u)" != "0" ]; then as_user() { "$@"; }; fi

writable() { as_user sh -c 'f="$1/.crewcut-write-test.$$"; : > "$f" && rm -f "$f"' sh "$STUDIO" 2>/dev/null; }
if [ "$(id -u)" = "0" ] && [ "$uid" != "0" ]; then
  chown "$uid:$gid" "$STUDIO/.crewcut" 2>/dev/null || true
  if ! writable; then
    echo "crewcut: the studio folder (owner $owner_uid:$owner_gid) is not writable for $uid:$gid; running as root inside the container"
    uid=0; gid=0
  fi
fi
if ! writable; then
  echo "crewcut: cannot write the studio folder $STUDIO (owner $owner_uid:$owner_gid, mode $(stat -c %a "$STUDIO"))." \
       "Make it yours and writable on the host (chown and chmod u+rwx), then start Crewcut again."
  exit 78
fi
[ "$uid" = "0" ] && export IS_SANDBOX=1

# Crewcut's own folders belong to the same user (an earlier start may have given them to another one).
for d in "$STUDIO/.crewcut" "$STUDIO/.claude"; do
  [ -e "$d" ] || continue
  if [ -n "$(find "$d" -xdev \( ! -user "$uid" -o ! -group "$gid" \) -print -quit 2>/dev/null)" ]; then
    chown -R -h "$uid:$gid" "$d" 2>/dev/null || true
  fi
done
export HOME="$STUDIO/.crewcut/home"
# `docker compose exec` (Connect Claude from the desktop app) runs as root: it reads who Crewcut runs as from here.
printf '%s:%s\n' "$uid" "$gid" > /run/crewcut-user 2>/dev/null || true

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
