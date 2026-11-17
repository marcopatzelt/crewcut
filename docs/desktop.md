# The desktop app

Crewcut as an app for macOS, Windows and Linux (`desktop/`, Electron). It runs the same Docker stack as `./start.sh`,
connects Claude with one button and shows the studio in its own window. It is built in CI only
(`.github/workflows/desktop.yml`); there is no release yet, so for now the files are workflow artifacts.

## What it does

| Step | What happens |
|---|---|
| Docker | It looks for Docker (also where Docker Desktop, OrbStack, Colima and Rancher Desktop put the `docker` command, since an app started from the Finder or the start menu has no terminal PATH). Missing or stopped, it says so in one sentence, with a link and Try again: Docker Desktop, OrbStack or Colima on a Mac, Docker Desktop on Windows, Docker Engine on Linux. Docker Compose 2.24 or newer. |
| Studio folder | Where your videos live; `~/Crewcut` unless you choose another. Mounted at `/studio`, like `./studio` with `./start.sh`. |
| Download | It pulls `ghcr.io/marcopatzelt/crewcut:<the app's version>` itself, through Docker's Engine API, and shows the real progress ("1.2 GB of 3.4 GB"). A development build (a version like `0.1.0-dev.42`) runs `:edge`, the newest image of the main branch. |
| Start | `docker compose up -d` with the repository's own `compose.yaml` (shipped unchanged inside the app) plus `desktop/stack/desktop.yaml` (no build, no pull by Compose), project name `crewcut`, so it is the same stack as `./start.sh`. The first start installs Claude Code inside the container (a few minutes); the screen shows the time and the container's last log line. |
| Connect Claude | The app runs `crewcut engine connect claude --print-token` in the container: Claude Code's own `claude setup-token` with `BROWSER=true`, so it prints its sign-in link. The app opens the link in your default browser (only links to claude.ai, claude.com, console.anthropic.com or platform.claude.com), you sign in on Claude's page and paste the code it shows into one field. The CLI prints a one-year token; the app keeps it in the **system keychain** (Electron `safeStorage`: the macOS Keychain, Windows DPAPI, GNOME Keyring or KWallet) and gives it to the container as `CLAUDE_CODE_OAUTH_TOKEN` when it starts the stack, never in a file. Without a keychain (some Linux desktops) the token stays in the container's engine volume instead, as in the web UI. **Connect Codex (beta)** runs `codex login --device-auth`: the app opens OpenAI's page and shows the code; the login stays in the engine volume, where Codex renews it itself. |
| The app | Then the window shows http://localhost:4747, the same page as in a browser. |

On later starts it checks Docker, starts the stack (pulling a new image once when the app's version changed) and
opens Crewcut.

**Quit** stops the stack (`docker compose stop`). In the settings (Crewcut → Settings…, or Ctrl+, / Cmd+,) you can
switch on **Keep the crew working in the background**: closing the window then leaves Crewcut in the menu bar (Mac) or
the tray (Windows, Linux) and the crew keeps working; Quit from there stops it. Off by default. The settings also show
who is connected (Disconnect, Connect again), Codex, the studio folder and the version.

## The window

No browser around the page and no second title bar: the page fills the window and its top bar is the title bar.

- **macOS:** `titleBarStyle: "hiddenInset"`; the real traffic lights sit in the middle of the 46 px top bar, and the
  page keeps its breadcrumbs clear of them through `env(titlebar-area-x)` (`titleBarOverlay: true`).
- **Windows and Linux:** the system's window buttons sit over the top bar (`titleBarOverlay`, 46 px high) in the
  colours of the tokens: `--panel` behind them, `--ink` for the symbols, light or dark as the page is (the page tells
  the app when the theme changes).
- The empty parts of the top bar move the window (`-webkit-app-region: drag`); buttons, links, the search field and
  the overlays don't.
- The window remembers its size and position (on the screen it was on, if that screen is still there).
- Links to anything other than the local Crewcut open in the default browser. Pages: `contextIsolation` on, `sandbox`
  on, no `nodeIntegration`; the window only navigates to `http://localhost:4747` and the app's own pages; only the local
  page may use the microphone (the composer's speech input). The local page gets three calls from the app (connect,
  settings, theme); the app's own pages get the steps of the first start; the main process checks the sender of every
  call.

## Download and install

*Coming with the first release.* Until then, Crewcut runs with `./start.sh` (README) and the app's files are the
artifacts of the `desktop` workflow runs.

| System | File | First start |
|---|---|---|
| macOS, in one line | | `curl -fsSL https://raw.githubusercontent.com/marcopatzelt/crewcut/main/install.sh \| sh` downloads the zip for your Mac with curl, checks its SHA-512 against the release, puts Crewcut.app into /Applications and opens it. No Gatekeeper dialog: macOS checks only files with the quarantine mark, which browsers set and curl does not. |
| macOS (Apple silicon or Intel) | `Crewcut-<version>-mac-arm64.dmg` or `-mac-x64.dmg` | Open the dmg, drag Crewcut to Applications, open it once. macOS says it cannot check the app for malicious software (it is not notarized yet: Crewcut has no Apple Developer ID). Then System Settings → Privacy & Security → scroll down to "Crewcut was blocked…" → **Open Anyway**, and confirm. Only once. |
| Windows | `Crewcut-<version>-windows-x64.exe` | The installer is not signed yet, so Microsoft Defender SmartScreen shows "Windows protected your PC". Click **More info**, then **Run anyway**. Only once. |
| Linux | `Crewcut-<version>-linux-x86_64.AppImage` or `.deb` | AppImage: `chmod +x Crewcut-*.AppImage` and start it. Debian or Ubuntu: `sudo apt install ./Crewcut-*.deb`. |

## Updates

The app checks GitHub Releases (electron-updater) at start and every six hours. On Windows and Linux (AppImage) it
downloads a new version and installs it when you quit. A Mac app without a Developer ID is only ad-hoc signed, and
macOS's updater refuses to replace such an app, so on a Mac the app says a new version is out and opens the download;
running the one-line install command again also updates it. With a Developer ID (see below) the Mac updates like the
others.

## Building, signing, releasing

CI only: `.github/workflows/desktop.yml` runs the unit tests (`npm test` in `desktop/`: image tags, settings, Docker
progress, the sign-in lines, the stack's command and environment, the window colours against `tokens.css`), then
builds on `macos-15-intel` (dmg and zip, arm64 and x64; the Apple silicon runners are often short of capacity), `windows-latest` (NSIS) and `ubuntu-24.04` (AppImage and
.deb), starts each app once to take pictures of its first screens (Linux under xvfb) and uploads everything as
workflow artifacts. It never publishes anything.

Signing is dormant until the secrets exist:

| Secret | For |
|---|---|
| `CSC_LINK`, `CSC_KEY_PASSWORD` | a Developer ID Application certificate (.p12, base64) for the Mac, or a code-signing certificate for Windows |
| `APPLE_API_KEY` (the .p8 text), `APPLE_API_KEY_ID`, `APPLE_API_ISSUER` | notarizing with an App Store Connect API key (preferred) |
| `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` | notarizing with an Apple ID instead |

Without `CSC_LINK` the Mac app is ad-hoc signed (`mac.identity: "-"`, with the hardened runtime off, which ad-hoc
signing needs) and the Windows installer is unsigned. The image the app runs comes from `image.yml`: every push to
main publishes `:edge`, a version tag `v1.2.3` publishes `:1.2.3` and `:latest`. A release is a `v*` tag plus a
GitHub release with the desktop files; the owner makes both.

Run it from the source (on a machine where that is allowed): `cd desktop && npm ci && npm start`.
