# YouTube

Crewcut uploads through the official **YouTube Data API v3**. No browser automation, no clicking in YouTube Studio:
an API does not break when YouTube moves a button.

## Connect once

YouTube only lets an app upload after you allow it with "Sign in with Google". For that, Google needs an "OAuth client"
from a Google Cloud project. Until a shared, Google-verified project exists (planned), you create your own once:

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
