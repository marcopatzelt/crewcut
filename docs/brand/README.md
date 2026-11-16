# Slate, the Crewcut brand

Slate is a clapperboard with a face. Its striped top bar is the "flat-top crew cut" in the name. Deep green board
`#0F6E5C`, mint stripes `#34C3A4`, white face. The mascot was made by the author with ChatGPT image generation and
redrawn by hand as simple SVG geometry; it is part of this MIT-licensed repository.

| File | What |
|---|---|
| `slate.svg`, `slate-dark.svg` | the logo mark, for light and for dark backgrounds |
| `slate-icon.svg` | the app icon: Slate on a mint tile, safe on light and dark |
| `slate-icon-small.svg` | the 16 and 32 px icon with fewer details (also `web/public/favicon.svg`) |
| `crewcut-lockup.svg`, `crewcut-lockup-dark.svg` | Slate next to the word "Crewcut" (Inter ExtraBold, as paths) |
| `crew/<id>.svg` | the eight crew avatars: Slate with the prop of its role |
| `states/*.svg` | idle (Zzz), working (motion lines), waiting ("?" sign), done (check), wave |
| `social-preview.svg`, `social-preview.png` | the GitHub social preview, 1280 x 640 |
| `icons/slate-icon-<size>.png` | 16 to 1024 px, rendered in CI |

## One source

Everything is built from `web/src/slate/art.ts`, the same code that draws Slate in the app:

```bash
uv run --with fonttools python tools/brand/text_paths.py     # only when a text of the brand files changes
node --experimental-strip-types tools/brand/build.mjs           # writes docs/brand/ and web/public/
```

CI checks that the committed files match the source (`build.mjs --check`) and renders the PNG sizes on GitHub's runner
(`tools/ci/brand_png.mjs`, artifact "screens").

## Social preview

GitHub has no API for the social preview image. To set it: the repository's **Settings → General → Social preview →
Edit → Upload an image**, and choose `docs/brand/social-preview.png`.
