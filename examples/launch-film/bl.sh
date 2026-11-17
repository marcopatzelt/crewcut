#!/bin/bash
# Runs one Blender scene script of this folder in the background (no window) and prints only errors, the timing lines
# and the DONE marker.
#   bash bl.sh <script.py> [script arguments]
. "$(dirname "$0")/env.sh"
S=$1; shift
"$BLENDER" -b --factory-startup --python "$HERE/$S" -- "$@" 2>&1 | grep -E "Error|Traceback|line [0-9]|DONE|Time:" | grep -v HIPEW | tail -8
