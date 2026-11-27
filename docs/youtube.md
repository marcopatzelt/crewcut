# YouTube

Crewcut uploads through the official **YouTube Data API v3**, and only through it. No clicking in YouTube Studio for
uploads: an API does not break when YouTube moves a button.

## Connect once

YouTube only lets an app upload after you allow it with "Sign in with Google". For that, Google needs an "OAuth client"
from a Google Cloud project of yours. Until a shared, Google-verified project exists (planned), it is created once.

Crewcut keeps the pending sign-in state and PKCE verifier in its private database until the callback completes.
The verifier must survive between the two requests; a new Flow object alone cannot complete the exchange.
After upgrading from a version that reported `Missing code verifier`, start a new connection rather than reloading
the old callback. Successful sign-in clears both pending values. Tests use a synthetic client and no Google account.

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
2. "APIs & Services" > "Library": enable **YouTube Data API v3** (and **YouTube Analytics API** for retention and the 48-hour check).
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
| A Short's link comment to the long video (`crewcut youtube comment`), after YouTube has processed it | `commentThreads.insert` (`youtube.force-ssl`) | part of the publish card; pinning has no API |
| "Altered or synthetic content" answer | `status.containsSyntheticMedia` | shown on the publish card with a reason |
| Retention around the motion moments (`crewcut youtube retention <episode>`) | YouTube Analytics API, read-only | none (unproven: see below) |
| Video results for a calendar-day period (`crewcut youtube results`) | YouTube Analytics API, read-only | none |
| A/B test "Test & compare" | no public API | Crewcut builds the variants and links you to the right page in YouTube Studio |

`crewcut youtube upload` refuses to run unless there is an accepted **publish** card whose file checksum matches the
current `export/upload.json`: you approve exactly what goes out. Put `publish_at` with its timezone in the package
before asking for approval. `--schedule` may repeat that exact value, but cannot override it after approval.
Without a schedule, visibility follows the approved package's `privacy` field, defaulting to **private**.

## Video results

`crewcut youtube results <episode> --start YYYY-MM-DD --end YYYY-MM-DD [--video ID]` reads views, watch time,
average view duration/percentage, likes, comments, shares and subscriber changes for an explicit calendar-day period.
The video ID otherwise comes from `export/upload-result.json`. It works for long videos and Shorts.

Reports live in `review/results-<start>-<end>.json`, with source, dates, missing metrics and limitations. Missing rows
are not invented zeroes and do not overwrite a previous report. No episode step, rule or approval changes.
Calendar days are not a precise rolling 48-hour window, and YouTube can delay data.

Thumbnail impressions, click-through rate and unique viewers are not part of this query. Use the channel owner's
YouTube Studio evidence for those instead of substituting unrelated metrics. Supported query metrics follow
Google's [metric reference](https://developers.google.com/youtube/analytics/metrics) and
[channel report reference](https://developers.google.com/youtube/analytics/channel_reports).

## Read back a publication

`crewcut youtube verify <episode>` compares the recorded video's title, description, tags, category, language,
visibility, schedule and declared audience with `export/upload.json`. It checks requested caption tracks for a
matching language/name and a serving, non-draft state. `--package` selects another package within the episode.

The command only reads YouTube. It writes `review/publication-check.json` locally and exits nonzero on differences.
It never changes a video, starts a job, grants approval or marks the upload step complete. A missing video or failed
request leaves the previous report untouched. After the scheduled time it expects public visibility; a delayed
publication is reported as a difference, not silently accepted.

This is a metadata check, not an audiovisual review. Thumbnail pixels, caption text, A/B tests, end screens and playlist
membership remain explicitly unchecked. It uses Google's [videos.list](https://developers.google.com/youtube/v3/docs/videos/list)
and [captions.list](https://developers.google.com/youtube/v3/docs/captions/list), with synthetic regression tests.

## Retention around motion moments

`crewcut youtube retention <episode>` reads the audience retention curve of the episode's published video
(`reports.query`, metric `audienceWatchRatio` by `elapsedVideoTimeRatio`) and lays it over the motion moments of the
newest edit plan: how many points of the audience were kept over each moment and the 5 s after it, against the video's
own slope around it. Code: `crewcut/youtube/analytics.py`.

- It needs the read-only permission `https://www.googleapis.com/auth/yt-analytics.readonly`. Crewcut asks for it in
  the sign-in (`crewcut/youtube/auth.py` `SCOPES`), and the YouTube Analytics API must be enabled in the Google Cloud
  project. **A login made before you enabled that API, or with a client that did not ask for this permission, must sign
  in once more** (`crewcut youtube auth`, or "connect YouTube" in the chat) to grant it; the command says so when the
  permission is missing.
- The video id comes from `export/upload-result.json` (or `--video ID`). The result goes to `review/retention.json`,
  into the motion report (`crewcut motion report`) and into the notes of the library templates ("number_roll: held
  viewers in 3 of 4 uses").
- **A hint, not proof.** Every finding is "watch". The same finding (template and direction) becomes a lesson in
  `brand/rules/motion.md` only after it repeats in 3 videos.
- **No data** (a new video, a Short without a per-second curve, a channel without the permission): it prints "no
  retention data" and writes nothing.
- **Unproven:** built and tested against a recorded answer of the API (`tests/core/data/`), never against a real
  channel. It stays marked unproven here until a published video has returned data.

## Honest limits

- **Visibility:** Google's current [upload reference](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)
  no longer restricts unverified API projects to private uploads. Omitting visibility can default to public at Google;
  Crewcut explicitly defaults to private and still requires a publish card. Check the returned visibility after upload.
- **Quota:** limits are project-specific. The current upload reference lists a separate Video Uploads quota bucket;
  check the project's Google Cloud quotas rather than assuming the older shared 10,000-unit allowance.
- **Custom thumbnails** need a verified channel (phone verification in YouTube).
- The upload path is written and unit-tested; an upload against a real channel has **not** been run yet.
