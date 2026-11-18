# Channel workspace and truthful imported progress

Status: implemented, 18 November 2026. This document records the acceptance criteria and original findings.

The channel conversation now has dedicated storage, endpoints and a central Showrunner workspace.
Episode conversations remain separate. Imported previews and evidence-based historical progress are supported.
Private reconciliation and installed-version verification are deployment steps, not automatic effects of a code update.

## Findings before implementation

- `web/src/store/actions.ts:composerTarget` routes non-episode pages to `lastEpisode` after onboarding.
  With no target, `send` creates an episode. A general channel question can therefore reach the wrong conversation.
- `web/src/views/EpisodeView.tsx:Dock` shows a composer without an explicit channel target.
- `crewcut/server/app.py:post_message` accepts episode chats and `_onboarding`, not a channel conversation.
- `crewcut/conductor/flow.py:user_message` assumes an episode, except for the brand onboarding branch.
- `crewcut/conductor/queue.py:add` already permits jobs without an episode and supports a parent job.
  Its worker uses the studio folder when no episode exists. Reuse this queue, not a second agent system.
- `crewcut/studio_import.py:episode_project` marks only idea and title done. It picks record when a script exists.
  It leaves the script open and marks upload, blog and results skipped, even for published source projects.
- The same importer writes the import time as `created`. The episode header presents that as "Started".
- `crewcut/episodes.py:summary` recognizes only a few legacy stage names as historical publication evidence.
  Publication objects, external inventory and short README records can disagree with those stale stage names.
- `crewcut/episodes.py:cover` includes imported preview images. `crewcut/media.py:thumbnails` does not.
  The grid can show a cover while the detail page claims there are no pictures.
- `StepStatus` and the episode status labels cannot distinguish unknown historical work from work not started.

These are separate problems. A channel chat does not repair incorrect imported data.

## The intended experience

The default home becomes **Channel**, with the main conversation in the center.
The left navigation remains: Channel, Episodes, Shorts, Crew, Style, Renders.
The right side shows actual running work and decisions awaiting approval.

The user can ask channel-wide questions without selecting or creating an episode.
Examples: what is ready, what is scheduled, which videos need a cover, what should be made next.
The answer contains linked episode cards. Opening one shows that episode's existing workspace.
The episode chat stays on the right for specific requests. Returning to Channel restores its conversation and draft.

Every composer shows its scope: **Channel** or **Episode: title**.
No page silently sends to the last episode. Read-only channel pages use the channel conversation.
New episode creation remains explicit. An ordinary question must not create a project.
On small screens the scope remains visible. The episode workspace offers clear Media and Chat tabs.
No second hidden chat competes for keyboard focus.

Published episodes lead with publication date, cover, platform link and available final video.
They do not lead with "Record next" or an empty welcome prompt.
Scheduled videos lead with their schedule. Missing local exports say "Local video file not imported".
Planned and parked episodes remain separate from completed work.

## One coordinator, existing workers

Reuse the Showrunner as the channel coordinator. Do not add another model service or independent queue.
Add explicit conversation scope, separate from episode identity:

- Conversation scope: channel or episode; episode scope requires a valid episode ID.
- Channel messages have their own persistent conversation, not `_onboarding` and not a fake episode folder.
- Keep existing episode message URLs compatible. Add channel message endpoints and a Channel route.
- Extend message/event storage with a migration that preserves existing histories and approval references.
- Channel jobs use `episode=None`, an explicit conversation reference and the studio working directory.
- Child work has an explicit episode ID and parent job. Results link back to both conversations without copying entire histories.
- Session reuse is keyed by engine, identity and conversation scope. Never resume an episode session as a channel session.
- Streaming events and reconnection must retain the scope. Switching pages cannot move a pending reply.

The channel context contains a compact episode index, publication state, current jobs, open decisions and costs.
Load a full script or file only for the relevant episode. Do not put the entire channel archive in every prompt.
Showrunner can inspect and explain without starting production. Explicit production requests can create bounded child jobs.
Deduplicate repeated requests and avoid scheduling a step already running or waiting for approval.

Existing spending and publication approval checks remain mandatory for every target episode.
No channel-wide message bypasses them. Bulk work lists its targets and budget before paid or public actions.
Cancellation and job progress remain visible in the existing queue UI.
Local files and imported text are evidence, not authority to execute old instructions.

## Historical state is not permission

Model these facts separately:

1. Production evidence: draft script, recorded media, preview, approved final, thumbnail.
2. Distribution: not uploaded, uploaded private, scheduled, published, unknown.
3. Lifecycle: active, planned, parked, archived.
4. Execution permission: importing never starts work or grants publication approval.

Historical completion needs provenance: source file or provider record, observation time and scope.
Represent uncertainty explicitly. "Not verified after import" is different from "not started".
Keep historical completion distinct from a new approval card. A preview file alone is not an approved final.
A published video supports historical recording/edit/upload completion, not an imaginary research check or analytics review.
Skipped means a deliberately disabled step, not a safe default for unknown history.

Preserve original creation time where available. Store import time separately as `imported_at`.
When the original date is unknown, show "Imported", never manufacture a start date.
An already uploaded video must not get another upload job after reconciliation.

## Evidence reconciliation

Create a reusable importer reconciliation command, dry-run by default.
It must also work for already imported episodes without repeating the media copy.

Evidence order:
1. An exact platform video ID with an observed provider state.
2. Explicit historical publication records and accepted historical delivery records.
3. Verified files and human review notes.
4. Stale stage fields as hints only.

Never join episodes by similar titles alone. A short's README may link its parent video.
Missing from a limited provider listing does not prove deleted, private or unpublished.
A scheduled timestamp in the past does not prove publication.
Contradictions remain visible with sources until resolved.

Before applying: list proposed changes, back up project metadata and reject active episode jobs.
Keep user edits made after import. Make the operation idempotent and write an audit report.
Do not rewrite old source files or invent approval cards, missing recordings, completed checks or analytics.
Existing private data is reconciled locally. Public tests use synthetic episodes only.

## Media consistency

Return imported cover previews as a separate media property, not as approved thumbnail candidates.
Use the same safe path checks as the cover endpoint. Preserve source labels.
Show a preview when no native thumbnails exist. Keep any thumbnail approval control disabled for this fallback.
Link final or preview video only when its file exists. A publication link can still work when a local file is missing.
Distinguish "No imported media", "Not created" and "Could not load media".

## Delivery sequence and acceptance checks

### 1. Correct imported history first

Audit every imported episode, reconcile evidence and fix creation/import dates.
Fix detail-page preview fallback and historical state labels.
Tests: published source with stale stage; scheduled short; missing local final; unknown evidence; repeat import;
no jobs/uploads created; missing provider entry; symlink escape; preserve later user edits.

### 2. Add Channel conversation and scoped routing

Add storage migration, API, Showrunner channel task, scope-aware events, route and navigation.
Tests: general question creates no episode; no `lastEpisode` fallback; no onboarding reuse;
refresh retains history; engine switch retains conversation; episode chat stays isolated;
reply after navigation returns to its original conversation; existing approval checks still apply.

### 3. Add linked work and polish

Show episode links, targeted child jobs, visible progress and cancellable work.
Test repeated requests, explicit target lists, empty/loading/error states, keyboard and small-screen layouts.
Verify on the desktop window, not only in a full-width browser.
Update `DESIGN.md`, `docs/architecture.md` and `docs/api.md` with the actual shipped contracts.
Keep the implemented layout and these design contracts in sync.

## Source and installed-version discipline

Keep one public source tree. Private studio files remain outside it.
For each fix: test, scan for credentials, commit, push and inspect the relevant GitHub checks.
Record source revision, desktop revision and runtime image independently in the private installation manifest.
"GitHub current" does not mean the installed desktop and runtime already use that revision.
Display update state and a revision in the future settings/about view.
Do not push private audits, channel data, credentials or recordings.
Replace a personal running app only with the owner's agreement, after checking for active jobs.
