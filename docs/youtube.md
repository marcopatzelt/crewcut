# YouTube

Crewcut uploads through the official **YouTube Data API v3**, and only through it. No clicking in YouTube Studio for
uploads: an API does not break when YouTube moves a button.

## Connect once

YouTube only lets an app upload after you allow it with "Sign in with Google". For that, Google needs an "OAuth client"
from a Google Cloud project of yours. Until a shared, Google-verified project exists (planned), it is created once.

### The easy way: Claude in Chrome sets it up (Claude Code)

Say "connect YouTube" (or run `crewcut youtube connect`). One card: **Set it up in my Chrome**. On your yes:

1. The host helper (`host/crewcut-host.sh`, started by `./start.sh` next to Docker) starts **your own Claude Code on
   your computer** with `--chrome`, in a visible window, on one fixed prompt (`host/prompts/youtube-setup.md`).
2. Claude opens the Google Cloud console in your Chrome, creates the project "Crewcut uploads", enables YouTube Data API
   v3 and YouTube Analytics API, sets up the consent screen (External, Testing, you as test user), creates a Desktop
   client and downloads its JSON file. It never types a password or a code: when Google asks you to sign in or confirm,
   it stops and you do it in the window.
3. The helper moves the file to `studio/config/youtube-client.json` (owner-only permissions).
4. The chat shows the "Sign in with Google" link. Allow Crewcut once; the chat says "YouTube is connected".

What it needs on your computer: Claude Code signed in with `/login` (Claude in Chrome does not work with the token of
`claude setup-token`), Chrome or Edge with the [Claude in Chrome](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn)
extension signed in to the same claude.ai account. `crewcut doctor` and the card say what is missing.

How the helper stays safe: it runs one job only. The container writes a request file into
`studio/.crewcut/host/requests/` with the job name, the time, a one-time value and the checksum of the setup prompt,
signed with HMAC-SHA256 and `CREWCUT_HOST_TOKEN` (in `.env`; `./start.sh` creates it). Only Crewcut's server knows the
key: the crew's runs never get it in their environment. The helper deletes and reports requests that are unsigned,
older than two minutes, used before, for another job, or for a prompt whose checksum differs from its own. It never
runs a command or a prompt it is sent, and it opens no network port. Claude's run may use only the Chrome tools (no
shell, no file writing, no web fetch).

With **Codex** as the engine this setup is planned: browser control from `codex exec` is untested (and not documented
for Linux). Use the manual way below.

### By hand (any engine)

1. Open the Google Cloud console and create a project (any name).
2. "APIs & Services" > "Library": enable **YouTube Data API v3** (and **YouTube Analytics API** for the 48-hour check).
3. "OAuth consent screen": user type **External**, fill in the app name and your e-mail, add yourself as a **test user**.
4. "Credentials" > "Create credentials" > "OAuth client ID" > application type **Desktop app**. Download the JSON file.
5. Save it in your studio folder as `config/youtube-client.json`.
6. Say "connect YouTube" in the chat (or run `crewcut youtube auth`). Open the link, allow access. The browser comes back
   to `http://localhost:4747/oauth/youtube` and the chat says "YouTube is connected".

The token is stored in `studio/.crewcut/youtube-token.json` (owner-only permissions) and is never shown.

## What the API does in Crewcut

| Task | API | Card |
|---|---|---|
| Upload video, title, description, tags, category, language | `videos.insert` (resumable) | publish (every time) |
| Schedule (`publishAt`), private / unlisted / public | `videos.insert` status | publish |
| Thumbnail | `thumbnails.set` | the thumbnail card before |
| Captions (SRT) | `captions.insert` | part of the publish card |
| "Altered or synthetic content" answer | `status.containsSyntheticMedia` | shown on the publish card with a reason |
| 48-hour check: views, click rate, retention | YouTube Analytics API | planned |
| A/B test "Test & compare" | no public API | Crewcut builds the variants and links you to the right page in YouTube Studio |

`crewcut youtube upload` refuses to run unless there is an accepted **publish** card whose file checksum matches the
current `export/upload.json`: you approve exactly what goes out. Without `--schedule` and without `publish_at` in the
package, the video is uploaded as **private**.

## Honest limits

- **Unverified projects:** Google locks videos uploaded through an API project that has not passed Google's audit to
  **private**. With your own test project this is expected; you can publish the uploaded video yourself in YouTube Studio,
  or apply for the audit. A shared verified project for all Crewcut users is planned.
- **Quota:** an upload costs a large part of the default daily quota (10,000 units). One channel is fine.
- **Custom thumbnails** need a verified channel (phone verification in YouTube).
- The upload path is written and unit-tested; an upload against a real channel has **not** been run yet.
