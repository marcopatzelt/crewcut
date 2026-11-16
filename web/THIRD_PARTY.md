# Third-party code and fonts in the web app

The built web app (`web/dist/`) bundles these packages. Versions are pinned in `package.json` and `package-lock.json`.

| Package | Version | Licence | What it is |
|---|---|---|---|
| `@fontsource/inter` | 5.3.0 | SIL Open Font License 1.1 | The Inter typeface (weights 400, 500, 600) |
| `react`, `react-dom` | 18.3.1 | MIT | UI library |
| `lucide-react` | 1.66.0 | ISC | Icons |

## Inter (font)

Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter).

Inter is licensed under the SIL Open Font License, Version 1.1. The full licence text ships with the package in
`node_modules/@fontsource/inter/LICENSE` and is available at https://openfontlicense.org. The font files are bundled
unchanged (as `.woff2` and `.woff` files under `dist/assets/`). The OFL allows bundling and redistribution with
software; it does not allow selling the fonts on their own.

## The system font on Apple devices

On Apple devices the app asks the browser for the font that is already installed (`system-ui`, the class `is-apple`
on `<html>`). No Apple font file is bundled, served or kept in the repository: Apple's font licence allows its fonts
only for mock-ups and forbids embedding them. `npm run check:fonts` fails on any such file. Icons stay `lucide-react`;
SF Symbols are not used.

The look takes no new packages: material, springs (CSS `linear()` curves from `scripts/springs.mjs`), the command
palette, tooltips and the keyboard shortcuts are written in this folder.

## Development only

`vite`, `@vitejs/plugin-react`, `typescript`, `vitest`, `jsdom`, `@testing-library/*` and `@types/*` are used to build
and test the app. They are not part of `dist/`.

## Ideas, not code

- [Taste skill](https://github.com/Leonxlnx/taste-skill) (MIT): the design check we run before a release. Not bundled.
