# One application, separate data

Keep the personal studio outside the code repository. Never use its data, login files, recordings or screenshots as
development fixtures. Code improvements are made once, tested with synthetic data, then installed as a deliberate
update of the personal application. Personal channel preferences belong in the studio's `brand/`, not in code.

## Development

`docker compose -p crewcut-development -f compose.development.yaml up -d` starts an isolated instance on localhost:4757.
It uses separate named volumes, reads no `.env` file, passes no account credentials and mounts no personal folders.
The prompter is local-only on port 4758. Stop it with the same command prefix followed by `stop` instead of `up -d`.
Do not use the ordinary `compose.yaml` for parallel development: that can reuse the personal stack.
Do not add personal credentials or mount the real studio to this instance. Authenticate separately only if needed.

## Personal version

Keep the installed application and its runtime at a known version. Development desktop builds normally follow `edge`.
To hold an already downloaded runtime, give its exact image ID a private local tag, and set `CREWCUT_TAG` to that tag
in the personal app launcher. Do not move that tag when updating development. This changes the next launch only;
it does not restart the current application. Set `CREWCUT_NO_UPDATES=1` in that launcher to disable automatic desktop
updates as well. Back up the studio before any deliberate upgrade, including its SQLite
database through SQLite's backup interface. Never copy a live database file by itself.

## Import earlier studio work

Preview with `python -m crewcut.studio_import SOURCE PRIVATE_STUDIO`; add `--apply` to copy.
The destination must be outside a repository and separate from the source. Originals are never modified or linked.
Each episode is copied into a staging folder and becomes visible only after its files and manifest are complete.
Repeated imports skip completed episodes and refuse to overwrite unrelated episodes or interrupted staging folders.
Imports start no jobs and keep uploads off. Existing publication metadata is historical, not permission to publish.

Scripts become readable drafts. Old projects, plans, recordings, review documents and media stay under each episode's
`legacy/` folder. Studio documents, templates and assets go into `library/video-studio/`. Old plans are not automatically
made runnable: their paths and tool formats need review. Existing work is never falsely marked newly approved.

Hidden directories, credentials by filename, old working environments, archives, raw frame sequences and render
caches are excluded. This is not a secret scanner: imported documents remain private and must never be published as
fixtures. The copy manifest records source paths, byte counts and SHA-256 hashes calculated during copying.

Check the public diff before publishing, including example channel data and screenshots. A Git ignore rule does not
protect files that were already tracked. Publishing remains a separate owner-approved action.

See [the migration gap register](studio-import-gaps.md) for remaining product work and its acceptance checks.

## Reconcile imported progress

Run `python -m crewcut.import_history EPISODE` with `CREWCUT_STUDIO` set to the private studio.
The default is a preview. Add `--evidence FILE.json` for an explicitly matched provider observation.
Add `--apply` only after reviewing the proposed changes. Each change saves the previous project and an audit
under the episode's `history-audit/` folder. Active episode jobs block the update.
Use `--keep-progress` to update historical metadata without replacing steps or the current next action.

An observation binds a YouTube `video_id` to one exact record, with `distribution` and `checked_at`.
No title matching or network lookup occurs. Missing records and old schedules do not prove publication.
Dates and historical completion remain separate from new approvals. Unknown work stays explicitly unverified.
Reconciliation preserves later edits, starts no jobs and never publishes. Keep its evidence and audits private.

## Desktop profiles

Installed desktop builds default to `CREWCUT_PROFILE=personal`, preserving existing data and login locations.
Source launches default to `development`. Set `CREWCUT_PROFILE=development` to run an installed build separately.
An unknown profile name fails rather than falling back to personal data.

Development uses its own app-data/browser-session directory, instance lock, saved login, default studio folder
(`~/Crewcut Development`), Compose project (`crewcut-desktop-development`) and engine volume. It uses localhost
ports 4757/4758, ignores the personal port/tag overrides and disables automatic desktop updates. Use
`CREWCUT_DEV_TAG` to select its runtime image. Personal remains on 4747/4748 by default. Do not select your personal
studio folder in a development profile: choose disposable test data only.

Both desktop profiles refuse inherited `.env` files. Their saved login comes only from their own app-data directory.
No personal data or credentials are copied to development. The browser-only development helper is an alternative,
not a second service to run simultaneously on ports 4757/4758.

Profile logic, Compose parameters and public callback/teleprompter ports have automated tests. A packaged parallel
launch on macOS and Windows has not been tested. These desktop changes need a new desktop package; updating the
running web app alone does not install them.

## Planned, parked and resumed work

`crewcut episode lifecycle <id> planned|parked|archived|active` organizes imported and new episodes. Planned,
parked and archived episodes stay visible but do not count as work or receive the home screen's footage import.
`active` explicitly resumes an imported episode for review without starting jobs or changing any step approval.
Historical evidence stays intact. A busy episode must finish or cancel its jobs before changing lifecycle.
This is not a cancellation command or a new permission to publish.
