# Full auto after recording

Each episode has an explicit **Full auto** choice above its production steps:

- Finish the video, thumbnails and upload package, then stop before uploading.
- Finish and upload privately, without a publication date.
- Finish and publish publicly or at the date in the reviewed upload package.

The default is off. Turning it on does not cancel or replace an existing job.
The worker waits for recordings, then handles edit, title, thumbnail and upload steps.
Disabled production steps are enabled for this run. Earlier research and script
decisions stay outside this mode. Unrelated old script-rule cards do not block production. Turning it off revokes pending automatic
reviews and upload authority; running production work is not killed.

The Critic reviews the usual motion plans, style frames, mixes, previews, final
cuts and thumbnails. An assigned review job submits a checksum-bound JSON report
with named checks, pass/revise verdict and reason. The normal card validation and
next-step transitions still run. A publish review additionally requires a valid
package and a video matching an accepted final cut. Private mode rejects public
visibility and publication dates. Upload checks the current delegation again.

New paid work is not silently approved. A spend request stays visible; Full auto never
declines it automatically or silently lowers render quality. Previously approved budgets retain their usual checks. Authentication failures,
missing source material and repeated quality failures may still need attention.
Three failed reviews or repeated incomplete jobs stop the loop with a visible
reason. This is delegation to a reviewing agent, not proof that every creative
choice will be good. All decisions and report checksums remain in the episode.

## Parallel insert design

Each approved style frame starts a fresh Designer session in `motion/<insert>/`.
Two jobs for the same insert cannot run together. Different inserts can run in
parallel, within the default limit of five agents. Heavy rendering retains its
separate single-job lane. Existing user limits override the default.

The Designer writes its insert sources, renders and handoff. The Critic reviews
each insert. The lead Editor owns the shared edit plan and final assembly.
No worker resumes another insert's conversation. Existing running jobs are not
migrated or restarted when this capability is installed.

## Thumbnails and A/B testing

The Codex path uses the connected Codex image tool. Crewcut also retrieves new
generated-image artifacts when Codex cannot copy them out of its image folder.
A real generation and recovery was verified in the Linux container. Other Codex
versions or accounts may expose different tools; failures are reported.

Full auto prepares thumbnail variants and has the Critic select one. This does
not start a YouTube A/B test. YouTube currently starts those tests in desktop
Studio, and excludes private videos and Shorts. See
[YouTube's A/B testing requirements](https://support.google.com/youtube/answer/16391400).
The paid image API remains a separate, budget-controlled route.
