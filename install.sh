#!/bin/sh
# Installs the Crewcut desktop app on a Mac in one line:
#
#   curl -fsSL https://raw.githubusercontent.com/marcopatzelt/crewcut/main/install.sh | sh
#
# It downloads the newest release's zip for this Mac (Apple silicon or Intel) with curl, checks it against the
# SHA-512 in the release's latest-mac.yml, puts Crewcut.app into /Applications (or ~/Applications) and opens it.
# Why no Gatekeeper dialog appears: macOS asks only about files that carry the quarantine mark, which browsers and Mail
# set and curl does not. The app is ad-hoc signed (Apple silicon starts nothing unsigned) but not notarized, because
# Crewcut has no Apple Developer ID yet. Downloaded in a browser, the .dmg needs one extra step: docs/desktop.md.
set -eu

REPO="marcopatzelt/crewcut"
say() { printf '%s\n' "$*"; }

[ "$(uname -s)" = Darwin ] || {
  say "This installs the Mac app. On Windows and Linux, download Crewcut from https://github.com/$REPO/releases/latest"
  exit 1
}
case "$(uname -m)" in
  arm64) ARCH=arm64 ;;
  x86_64) ARCH=x64 ;;
  *) say "This Mac ($(uname -m)) is not one Crewcut is built for."; exit 1 ;;
esac

json=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null) || {
  say "There is no Crewcut release yet. Until then, run Crewcut with ./start.sh (see the README)."
  exit 1
}
asset() { printf '%s' "$json" | grep -o "\"browser_download_url\": *\"[^\"]*$1\"" | head -1 | sed 's/.*"\(https[^"]*\)"$/\1/'; }
zip_url=$(asset "-mac-$ARCH.zip")
yml_url=$(asset "latest-mac.yml")
[ -n "$zip_url" ] || { say "The newest release has no Mac app for $ARCH yet."; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM
name=$(basename "$zip_url")
say "Downloading $name ..."
curl -fL --progress-bar -o "$tmp/$name" "$zip_url"

if [ -n "$yml_url" ]; then
  curl -fsSL -o "$tmp/latest-mac.yml" "$yml_url"
  want=$(awk -v f="$name" 'index($0, "url: " f) { getline; sub(/^.*sha512: */, ""); print; exit }' "$tmp/latest-mac.yml")
  got=$(openssl dgst -sha512 -binary "$tmp/$name" | base64 | tr -d '\n')
  if [ -z "$want" ] || [ "$want" != "$got" ]; then
    say "The download does not match the release's checksum. Nothing was installed."
    exit 1
  fi
  say "Checksum verified."
fi

ditto -x -k "$tmp/$name" "$tmp/app"
[ -d "$tmp/app/Crewcut.app" ] || { say "The zip holds no Crewcut.app. Nothing was installed."; exit 1; }

dest=/Applications
[ -w "$dest" ] || { dest="$HOME/Applications"; mkdir -p "$dest"; }
if [ -d "$dest/Crewcut.app" ]; then
  osascript -e 'quit app "Crewcut"' >/dev/null 2>&1 || true
  sleep 1
  rm -rf "$dest/Crewcut.app"
fi
ditto "$tmp/app/Crewcut.app" "$dest/Crewcut.app"
say "Crewcut is in $dest. Opening it."
open "$dest/Crewcut.app"
