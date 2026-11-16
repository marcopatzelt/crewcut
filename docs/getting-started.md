# Getting started

## You need

- Docker: Docker Desktop (free for personal use and small companies), Colima (free) or Docker Engine on Linux.
  Docker Compose 2.24 or newer.
- A Claude plan with Claude Code (`claude setup-token` once, on any computer with a browser).
- About 15 GB of free disk for the image and your first episodes.

## Start

```bash
git clone https://github.com/marcopatzelt/crewcut.git && cd crewcut
claude setup-token        # on a computer with a browser; copy the token
./start.sh                # asks for the token once, then: docker compose up
```

Open http://localhost:4747. The first start installs Claude Code inside the container and takes a few minutes.
On Windows, run `start.sh` in WSL or Git Bash, or copy `.env.example` to `.env`, fill in the token and run
`docker compose up -d`.

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
