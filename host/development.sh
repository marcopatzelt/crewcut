#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose --env-file /dev/null -p crewcut-development -f "$root/compose.development.yaml")
case "${1:-status}" in
  start) "${compose[@]}" up -d ;;
  stop) "${compose[@]}" stop ;;
  status) "${compose[@]}" ps ;;
  config) "${compose[@]}" config ;;
  *) printf 'Usage: %s [start|stop|status|config]\n' "$0" >&2; exit 2 ;;
esac
