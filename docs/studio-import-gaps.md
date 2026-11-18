# Legacy studio migration: gap register

Scope: file-backed video-studio projects compared with Crewcut's importer, desktop, episode schema, media API,
style packs and documented workflow. This is not a claim of full feature parity or a complete security audit.
Personal examples, paths, scripts, recordings and account details belong only in the private studio.

Priority: P0 protects personal data; P1 makes imported work usable; P2 completes workflow parity.
State: implemented means tested locally, not published or installed as a new application release.

| ID | Priority / state | Gap and impact | Next step and acceptance check |
|---|---|---|---|
| 01 | P0 / implemented | Development previously shared the default project name and could touch the personal runtime. | Separate Compose project, volumes and ports; config test proves no personal bind mounts or inherited credential file. |
| 02 | P0 / local setup | Development desktop builds follow a mutable runtime tag. | Pin the personal runtime and disable automatic desktop updates; next normal launch must retain the recorded image ID. |
| 03 | P0 / open | No first-class Personal/Development desktop profiles. Local launchers are not a portable product feature. | Separate app data, locks, credentials, names and runtime selection on Linux, macOS and Windows. |
| 04 | P0 / open | Upgrade and rollback are not coordinated with database migrations. | Backup, compatibility check, explicit upgrade, restore test with synthetic data. |
| 05 | P0 / open | Filename exclusions are not a content-based secret scan. Existing example packs contain author-specific preferences. | Audit tracked files and history separately before publication; never publish imported fixtures or screenshots. |
| 06 | P0 / implemented | Ordinary episode import starts the next step. Bulk migration must not do that. | Separate offline importer starts no database jobs and disables upload; regression test verifies no database is created. |
| 07 | P0 / partial | Source material can change during copying. Copies on one disk are not disaster recovery. | Copy checks source size/mtime and records hashes. Add a second-device backup and a verified restore. |
| 08 | P1 / implemented | Multiple episodes, TXT recording scripts and older directory layouts are not covered by the ordinary importer. | Bulk copy preserves IDs, selects explicit/recording scripts, and records per-file manifests. |
| 09 | P1 / partial | Historical finished/published/parked states differ from Crewcut's step states. | Explicit historical published/parked/paused/archived states now affect display and exclude footage targets, without granting approvals. Native lifecycle and explicit resume remain open. |
| 10 | P1 / partial | Imported files under legacy/ were not available in the episode view. | Added script downloads and a paginated, read-only folder browser, with traversal/link tests. Full-content search remains open. |
| 11 | P1 / partial | Video selection by filename/mtime can pick the wrong preview. | Prefer explicit delivery references; let users choose among versions, with duration, approval and missing-file indicators. |
| 12 | P1 / open | Old plans refer to absolute paths, other episodes and older rendering tools. | Relocate references and validate each supported plan format. Never execute archived plans automatically. |
| 13 | P1 / open | Original media is preserved but lacks native ingestion records and recording/take associations. | Register imported media and checksums without starting transcription; show missing external originals. |
| 14 | P1 / open | Short source relationships and exact trim selections are not migrated to the native Short schema. | Preserve historical plans, map source episodes and time ranges, verify the source preview. |
| 15 | P1 / open | Ideas in shooting plans may have no episode directory. | Create explicit planned entries, preserving dependencies and distinguishing partial scripts from complete scripts. |
| 16 | P1 / partial | Channel/style data can be copied, but onboarding normally rebuilds it from links. | Add a supported import-existing-profile flow with a review screen; keep known preferences private. |
| 17 | P1 / open | Historical benchmark videos do not match the motion baseline schema. | Convert benchmark paths, strengths, frames and approval provenance; validate with the native baseline mechanism. |
| 18 | P1 / open | Historical skill instructions are not automatically current Crewcut instructions. | Preserve as reference; map rules to steps and resolve conflicts before activating them. |
| 19 | P1 / open | Thumbnail reference photos and accepted style examples require explicit mapping. | Store them in the private style pack; test a thumbnail draft without publishing. |
| 20 | P1 / open | Bulk import has no integrated progress/retry/undo screen. | Add a dry-run summary, exclusions, interrupted-copy recovery and non-destructive undo. Current reruns skip completed episodes. |
| 21 | P1 / open | There is no incremental synchronization with the old studio. | After verification, designate Crewcut as the sole writing location. Add explicit conflict-aware imports if needed. |
| 22 | P2 / unverified | Recording to finished video has not been proven with the imported personal footage. | One complete opt-in episode: ingest, transcript, take selection, edit, audio, graphics, review and export. |
| 23 | P2 / unverified | Legacy editing checks may exceed or differ from Crewcut checks. | Map every old rule to a test; include missing words, repeated starts, pauses, flash frames and full-track audio. |
| 24 | P2 / unverified | Old portrait/landscape graphics and advanced 3D scenes are not automatically native templates. | Convert representative scenes and compare rendered output in both formats. |
| 25 | P2 / unverified | Music generation, cue placement and mix preferences have not been migrated as an executable workflow. | Generalize episode-specific scripts and confirm ducking, peaks and final listening review. |
| 26 | P2 / open | External publication packages, captions and thumbnails can live outside the old studio. | Inventory external references and copy only user-authorized assets; do not access credentials. |
| 27 | P2 / partial | YouTube code exists, but desktop connection and account setup are not proven for this migration. | User performs sign-in; test a read-only channel check first. No uploads during import. |
| 28 | P2 / partial scope | Blog is excluded from this migration implementation pending clarification of the owner's dictation. Long-video results remain planned. | Do not infer results parity from Shorts helpers. No blog implementation in this work. |
| 29 | P2 / open | Historical analytics, comments and A/B decisions are not normalized to current data structures. | Add provenance-preserving import and read-only display before making new decisions from them. |
| 30 | P2 / unverified | Historical cost records do not have reliable mappings to current jobs. | Keep as historical evidence; never add them to current bills without a reviewed mapping. |
| 31 | P2 / open | Personal feedback and product bug reports lack a dedicated privacy-safe handoff. | Keep personal notes in the studio; reproduce issues with synthetic data, then fix and test public code once. |

No release, upload or paid generation is part of migration. A copied file is not a tested conversion, approval or
permission to publish. Track private project-specific omissions in the studio, not in this public register.

## Follow-up audit evidence

- Editing checks are not absent: `skills/cut-check/scripts/cut_check.py` and `style_check.py` already cover word rests,
  doubled words, take changes, speaker flashes, empty/still graphics, colour measurement, music rights, output freshness,
  loudness and shown-file checks. Tests live in `tests/skills/test_cut_check.py`, `test_style_check.py` and `tests/cut/`.
  This establishes code coverage, not equivalence on a user's real recordings or a completed listening review.
- Music assembly is generalized in `crewcut/render/music.py`; an episode-specific legacy generation script is still
  historical evidence, not a tested portable generator. No paid generation or listening approval was performed.
- YouTube upload, captions, thumbnails and retention have implementation paths. `skills/upload/SKILL.md` still marks
  long-video analytics, playlist insertion and live package verification as planned. Do not claim these are finished.
- The local Python, web and desktop suites passed during this follow-up. A synthetic browser smoke test opened the
  script list and an imported subfolder. This was not a test of the installed personal desktop app or real publication.
- A redacted Git-history secret scan inspected 162 commits without findings. This does not certify working files,
  external data, downloaded credentials, example-pack licensing or the next release.
- The installed personal runtime has not been replaced. No new program version has been pushed as part of this follow-up.
