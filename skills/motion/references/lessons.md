# Lessons: bad and good, with our own frames

Each lesson cost a review round on the launch film. Every picture is cut from our own review strips and sheets (the
time stamp in each cell is the film's time). Top row: before. Bottom
row: after. Open the picture when the line alone does not make it clear.

| # | Seen | Fix | Picture |
|---|---|---|---|
| 1 | The logo read flat: a 2.5D slab that stands still | Blender: extrusion 0.2, bevel 0.05, a visible turn of about ±18°, a light sweep across the hold | `lessons/01-logo-flat-vs-3d.jpg` |
| 2 | The break was sparse and slow: a ring of thin triangles (the Shatter effect) | authored flake paths: bristles grow for 20 frames, release in 5, one swirl frame with long motion-blur arcs; chunky chips, the cloud spreads 2.4 times | `lessons/02-shatter-vs-authored-flakes.jpg` |
| 3 | An empty dark disc stayed after the break | the disc becomes the iris into the next world within 0.1 s: open fast and linear, never a slow porthole | `lessons/03-empty-disc-vs-iris.jpg` |
| 4 | Neon lime grass, the horizon in the middle, white blobs for flowers; the search bar small and faint | a photoreal meadow (low camera, dark roots, translucent blades, petal flowers, an HDRI sky); the bar at 45 to 50 % of the width, a crisp white field, 38 to 42 px text, an icon and a glyph, a slow approach | `lessons/04-meadow-and-search-bar.jpg` |
| 5 | A symmetric splash read as a sun icon | uneven core blobs, two long throws to one side, short strokes, secondary splats, droplets of many sizes | `lessons/05-symmetric-vs-uneven-splash.jpg` |
| 6 | A tiny lone icon in an empty frame at the start | a dock of five icons at 35 to 40 % of the width, with hover reactions before the click | `lessons/06-lone-icon-vs-dock.jpg` |
| 7 | The pixel squares were invisible outside the disc | darker squares, or outlined squares on a fixed grid, readable on every ground | `lessons/07-pixel-squares.jpg` |
| 8 | Everything in the brand green | the brand is an accent: a pastel gradient, warm 3D renders, pastel cards; the hue check passes | `lessons/08-one-hue-vs-content-colour.jpg` |
| 9 | (rule 1) a transition that is only a cut | a click on the search glyph grows a circle in the next scene's ground colour; the next picture is caused | `lessons/09-caused-transition.jpg` |
| 10 | (rule 2) a hold that stands still | the hold is a push: the bar grows from 100 to over 300 % while the text is typed | `lessons/10-camera-never-stops.jpg` |
| 11 | The typed words were far too small to read | 150 px while typing; on impact they shrink to 60 % and move above the big word (no frame kept) | — |

## What the lessons have in common

- **The first version was always too small, too flat or too still.** Start bigger, heavier and moving.
- **An effect that "does it" in one call (Shatter, a stock splash, a plain gradient sky) looked cheap.** Authored
  paths and real 3D looked made.
- **Every fix was found by putting our frame next to a better one at the same moment.** The comparison is the method.

## Adding a lesson here

A lesson that holds for every channel (an engine trap, a look that always fails) can be added to this file by a
pull request from the maintainer, with a picture cut from Crewcut's own renders (each at most 150 KB, the folder at most
3 MB). A channel's own lessons go to its `brand/rules/motion.md` (`ratchet.md`).
