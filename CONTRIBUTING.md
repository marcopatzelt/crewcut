# Contributing to Crewcut

Thank you for helping. Crewcut is small on purpose: one image, one studio folder, YouTube first.

## Before you start

- Read [docs/architecture.md](docs/architecture.md) (paths, commands, steps, the edit plan, the database) and, for any UI
  change, [DESIGN.md](DESIGN.md). Both are contracts: if you change a name there, change the code in the same pull request.
- Open an issue first for anything bigger than a bug fix, so we can agree on the shape before you spend time.

## Development setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/pytest -q
cd web && npm ci && npm run typecheck && npm run check && npm test
```

The heavy parts (Chromium renders, Blender, the Docker image on two architectures) are built and tested by GitHub
Actions (`.github/workflows/`). You do not need Blender or a GPU to contribute.

## Rules for pull requests

- **Skills hold know-how, the style pack holds taste.** A skill never hard-codes a colour, a font, a loudness or a channel
  rule; it reads them from the style pack through `crewcut.brand`. New taste values get a neutral default in
  `packs/neutral/` and a line in `docs/style-packs.md`.
- **No forms.** The UI shows work and takes one sentence or one yes (DESIGN.md, rules 1.2 and 3).
- **Money and publishing go through cards.** Never add a path that rents, pays or publishes without
  `approvals.require_spend` or an accepted publish card.
- **No secrets, no personal data, no third-party media** in commits: no tokens, no channel IDs, no recordings, no
  unlicensed music or fonts. CI runs gitleaks and a personal-data check on every push.
- **Knowledge sources** are credited by name and link with our own short summary. No transcripts, no images, no long
  quotes from them.
- **Honest status.** Mark what is not tested as "untested" or "planned" in code comments, docs and the README.
- Tests for new logic (`tests/`), `ruff check .` clean, plain English in code and docs, no emoji.

## Commit messages

Short imperative subject in English ("Add the bars scene"), a body when the why is not obvious.

## Licence

By contributing you agree that your contribution is licensed under the MIT licence of this project.
