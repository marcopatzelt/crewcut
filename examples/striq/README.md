# Example style pack: STRIQ

This is the style pack of the channel run by the author of Crewcut (STRIQ, a German channel that tests Claude and AI
agents on real work). It is here as proof that the system learns: every value and every rule carries the date and the
source of the correction it came from.

It is an example, not a template. Your own style pack is `brand/` in your studio folder; the Brand identity builds it
from your links on the first start (`skills/onboarding/`).

What is in it:

| File | What |
|---|---|
| `brand.json` | accent colour, font family name, 3D stage (no font files, no logo) |
| `edit-style.json` | format, frame rate, length, captions, music and loudness, mix limits |
| `channel.json` | language, niche, audience, topics to avoid, closing line, limits for ideas, titles, scripts and uploads |
| `thumbnail.json` | layouts, face, words on the image, colours, number of test variants |
| `rules/<step>.md` | learned rules, one per line: date, rule, source |

What is not in it, on purpose: no logo, no photos, no fonts, no voice profile, no channel id, no episode material, no
values taken from other creators.

Try the checks against it:

```bash
python3 skills/title/scripts/title_check.py "Claude: 10x schneller" --pack examples/striq
python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --pack examples/striq
```
