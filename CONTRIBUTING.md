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

Keep your personal studio outside the repository. For parallel development, use `bash host/development.sh start`:
it uses separate volumes and localhost ports 4757/4758, without mounting personal data or reading credential files.
See [private studios and updates](docs/private-studio.md) and the [migration gap register](docs/studio-import-gaps.md).

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

## Design checks in CI (the Taste gate)

Small changes go online at once; the design gate is information, not a barrier (owner's rule, 17 Nov 2026).

- **Landing page** (`.github/workflows/pages.yml`): every push to `main` that touches `site/`, the brand, the README
  pictures or the launch film builds the page and deploys it at once. Then it takes screenshots of the live page at
  1440 and 390 px (artifact `live-shots`): look at them.
- **App screenshots** (`.github/workflows/screens.yml`): the README images, brand PNGs and app screenshots are uploaded
  at once (artifact `screens`).
- **The Taste gate runs only for big changes**: more than about 300 changed lines in `site/` (or `web/`), a section
  added or removed, a design token changed (`site/assets/site.css` custom properties, `web/src/styles/tokens.css`), a
  file added or removed in `web/`, `[gate]` in a commit message, or a manual run with `run_gate`. The rule is in
  `tools/ci/gate_decide.sh`. `[no gate]` in a commit message skips the landing page's gate for that push.
- **It never blocks**: its findings go to the job summary and a separate artifact. Fix what is visibly wrong in one
  pass, write a waiver with a reason for a finding that does not apply (`site/.taste-skill/waivers.json`,
  `.taste-skill/waivers.json`), and move on. Agents: do not loop on gate findings.

## Commit messages

Short imperative subject in English ("Add the bars scene"), a body when the why is not obvious.

## Licence

By contributing you agree that your contribution is licensed under the MIT licence of this project.
