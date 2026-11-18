# Computer media in Crewcut

The desktop app makes Videos, Pictures, Music, Downloads and Desktop available to
the crew as media sources. Connected cards and drives appear on the next request.
In Episodes, **Media folders** connects another folder through the computer's folder picker.
The selection stays in desktop settings, outside the studio and repository.

The crew can list directories and media filenames, then copy selected recordings,
audio or pictures into an episode. It cannot change or delete source files through
this feature. Symlinks cannot escape a source. Copies are checked with SHA-256;
interrupted or changed recordings fail without a completed inbox file.

From either Claude Code or Codex:

```sh
crewcut media sources
crewcut media list SOURCE_ID --path DCIM
crewcut media list SOURCE_ID --path DCIM --offset 200
crewcut media import EPISODE SOURCE_ID DCIM/clip.MP4
crewcut media status REQUEST_ID
crewcut ingest EPISODE /studio/inbox/EPISODE/RETURNED_FILENAME --json
```

List and import return a durable request ID. The CLI waits up to five seconds.
For `pending` or `running`, check status again. `done` includes the copied inbox
file, size and checksum; ingest registers it in originals and checks the recording.
No import starts solely because a card is connected. The crew needs the user's
requested episode and takes. No paid services or publishing run during copying.

This is a small native desktop service, not a full host-folder mount inside the
container. Requests contain source IDs and relative paths, never host commands.
The desktop must be open. Browser-only installs retain file upload and `/import`.
Standard folders use Electron's OS paths. Linux checks `/run/media/<user>` and
`/media/<user>`; macOS checks `/Volumes`; Windows checks non-home drives D–Z.
Other locations are available through the folder picker. Linux is tested on a
real card; macOS and Windows discovery still need device testing.

Requests live in `.crewcut/desktop-media`. Source labels and file metadata are
private studio data. A long copy currently reports `running`, without percentage
progress. If the desktop closes during a copy, submit the import again after
reopening it; source files remain intact.
