#!/bin/sh
# Does this change get the Taste gate? The gate is information only and runs only for big changes (owner's rule,
# 17 Nov 2026): a deploy or a screenshot run never waits for it.
#
#   tools/ci/gate_decide.sh BEFORE AFTER "PATHS" "FOUNDATION_FILES" [STRUCTURE_REGEX]
#
# Yes when one of these holds:
#   - RUN_GATE=true (started by hand with run_gate),
#   - a commit message in COMMIT_MESSAGES contains [gate],
#   - more than 300 changed lines under PATHS,
#   - a design token (a CSS custom property definition "--name:") changed in FOUNDATION_FILES,
#   - a structural line (STRUCTURE_REGEX, default: an HTML <section>) was added or removed under PATHS,
#     or a file under PATHS was added or removed.
# Prints "gate=true|false" and "why=..." (for $GITHUB_OUTPUT) and one human line on stderr.
set -eu
before=${1:-}; after=${2:-HEAD}; paths=${3:-.}; foundation=${4:-}; structure=${5:-'<section[ >]'}
why=""
if [ "${RUN_GATE:-false}" = "true" ]; then why="started by hand (run_gate)"; fi
if [ -z "$why" ] && printf '%s' "${COMMIT_MESSAGES:-}" | grep -qF '[gate]'; then why="a commit message says [gate]"; fi
if [ -z "$why" ]; then
  if [ -z "$before" ] || printf '%s' "$before" | grep -qE '^0+$' || ! git cat-file -e "${before}^{commit}" 2>/dev/null; then
    before=$(git rev-parse --verify -q "${after}~1" || true)
  fi
  if [ -n "$before" ]; then
    # shellcheck disable=SC2086
    lines=$(git diff --numstat "$before" "$after" -- $paths | awk '$1 != "-" { s += $1 + $2 } END { print s + 0 }')
    # shellcheck disable=SC2086
    files=$(git diff --name-status --diff-filter=AD "$before" "$after" -- $paths | wc -l)
    # shellcheck disable=SC2086
    struct=$(git diff -U0 "$before" "$after" -- $paths | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -cE "$structure" || true)
    tokens=0
    if [ -n "$foundation" ]; then
      # shellcheck disable=SC2086
      tokens=$(git diff -U0 "$before" "$after" -- $foundation | grep -cE '^[+-][[:space:]]*--[A-Za-z0-9_-]+[[:space:]]*:' || true)
    fi
    if [ "$lines" -gt 300 ]; then why="$lines changed lines (more than 300)"
    elif [ "$tokens" -gt 0 ]; then why="design tokens changed ($tokens lines)"
    elif [ "$struct" -gt 0 ]; then why="a section was added or removed"
    elif [ "$files" -gt 0 ]; then why="a file was added or removed"
    fi
  fi
fi
if [ -n "$why" ]; then echo "gate=true"; echo "why=$why"; echo "Taste gate: yes ($why)" >&2
else echo "gate=false"; echo "why=small change"; echo "Taste gate: no (small change)" >&2; fi
