# Getting started

## You need

- Docker: Docker Desktop (free for personal use and small companies), OrbStack or Colima on a Mac, Docker Engine on
  Linux (rootful or rootless). Docker Compose 2.24 or newer. Crewcut runs as the owner of your studio folder, so every
  file the crew writes is yours; under rootless Docker that owner is root inside the container (which is you on the
  host), and Crewcut tells Claude Code with `IS_SANDBOX=1` that the container is its sandbox.
- A Claude plan: Pro, Max, Team or Enterprise. Crewcut connects to it with the "Connect Claude" button.
- About 15 GB of free disk for the image and your first episodes.

## Start

The desktop app does all of this with buttons (Docker check, download, Connect Claude): [desktop.md](desktop.md),
coming with the first release. With the repository:

```bash
git clone https://github.com/marcopatzelt/crewcut.git && cd crewcut
./start.sh                # writes .env, then: docker compose up, and opens Crewcut
```

When the server answers, Crewcut opens in its own window at http://localhost:4747: an app window of Google Chrome,
Microsoft Edge, Brave, Arc or Chromium (whichever is installed first; on Linux your default browser first when it is one
of them), with your normal browser profile. Without one of them it opens in your default browser. The first start
installs Claude Code inside the container and takes a few minutes; until the server answers, the page says "Crewcut is
starting…".

On Windows, run `start.sh` in WSL or Git Bash (it opens the window with Edge), or copy `.env.example` to `.env`, run
`docker compose up -d` and open http://localhost:4747.

### Connect Claude

The first screen says "Connect Claude first." Press **Connect Claude**: Claude's own sign-in page opens in a new tab.
Sign in; the page shows a code. Paste it into the one field and press Connect. Crewcut runs the official sign-in of
Claude Code (`claude setup-token`) inside the container and keeps the one-year token in the engine volume (mode 0600,
never in your studio folder); it never sees your password. **Connect Codex (beta) instead** shows a link and a one-time
code for ChatGPT's device sign-in.

On a server without a screen, `./start.sh` also asks for a token from `claude setup-token` (hidden input, Enter skips
it); you can just as well open Crewcut in a browser later and press Connect Claude.

| To | Run |
|---|---|
| start without opening a window, only print the address | `./start.sh --no-open` |
| open a normal browser tab instead of an app window | `CREWCUT_OPEN=browser ./start.sh` |
| never open anything (servers, rented machines) | `CREWCUT_OPEN=none ./start.sh` |
| open the window again later | `crewcut open` (or `host/open-app.sh`); it also prints the address |

`crewcut open` waits up to 15 minutes for the server (`--timeout` in seconds) and takes `--no-open` and
`CREWCUT_OPEN` too.

### Keep it as an app

Crewcut can be installed like an app, so it has its own icon in the dock or start menu and opens without a browser
around it:

- **Chrome or Edge:** open http://localhost:4747 and click the install icon at the right of the address bar (or the
  menu → Cast, save and share → Install page as app; in Edge Apps → Install this site as an app).
- **Safari (macOS 14 or newer):** File → Add to Dock.

The installed app is the same page: it needs Crewcut running (`./start.sh`).

## First run

1. **Paste your links**: website, YouTube channel, social profiles. The Brand crew member builds your style pack and
   shows a profile and a 10-second sample. One yes. No links? The neutral style works too.
2. **Say an idea** in one sentence. The Scout looks for the data behind it and comes back with a topic card.
3. Answer cards with one button, or say what to change. Record when the teleprompter link appears; drop the files into
   the chat.

## Where your files are

Everything lives in `./studio` next to the app: `brand/` (your style pack), `episodes/` (one folder per episode),
`config/` (your overrides of `config/*.toml`), `.crewcut/` (database, logs). Back it up; Crewcut never uploads it.

## Optional

- Rent GPUs for 3D and long jobs: put a Vast.ai key into `.env` ([compute.md](compute.md)).
- Thumbnails through the OpenAI image API: `OPENAI_API_KEY` in `.env`.
- YouTube upload: [youtube.md](youtube.md).
- A local NVIDIA card: `docker compose -f compose.yaml -f compose.gpu.yaml up -d`.
