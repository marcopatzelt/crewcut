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
