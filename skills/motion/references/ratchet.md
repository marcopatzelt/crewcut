# The quality ratchet: the bar only goes up

Each video is compared with the best one before it. Each video gets at least one targeted upgrade. Lessons are written
after each video and read before the next. Pieces that worked join the library. Retention data is used where it
exists, carefully. Nothing here moves without evidence, and the bar never moves without the user's yes.

## 1. The files (in the user's studio, per channel)

| File | What | Who writes | Who reads |
|---|---|---|---|
| `brand/baseline.json`, block `motion` | the best video so far for motion: episode id, its motion report, 3 to 6 named strengths with frames, measured values (motion moments, share of caused transitions, custom pieces, hue spread, retention around motion when known) | the Critic proposes, the user confirms on a card (`--kind baseline`) | the director before planning, the Critic when reviewing |
| `episodes/<id>/review/motion-report-vNNN.md` and `.json` | this video against the bar: better, behind, whether each chosen upgrade landed, per piece one sentence on what the reference still does better, proposals | the Critic | everyone; the Showrunner puts 3 lines of it on the preview card |
| `brand/rules/motion.md` | the lessons: one dated line each, with an id, the rule, the evidence and its source | the Critic after each video; the Showrunner adds the user's notes from any card | the director **before every motion pass** |
| `brand/references/motion/index.json` and files | references: reels and videos the user sends, links the Scout finds, each with what to learn from it | the Showrunner files what the user sends; the Scout adds a few per video with a reason | the director and the Designer |
| `brand/templates/motion/library.json` | the shelf, with per piece: where used, how it reviewed, a retention note | the Editor (promotion), the Critic (notes) | the director |

### A lesson line

```
- 2026-11-17-3 | Opening numbers land heavy: 3D or a rolled meter, never flat type that fades in | 003 at 0:04, review/motion-v002/m1/sheet.jpg | review
- 2026-11-24-1 | "The words should come from behind the shoulder, not from the edge" | 004 at 1:12 | user, verbatim
```

Id = date and a running number. The rule is one sentence. The evidence names the episode, the time and a frame. The
source is `review`, `user` (the user's own words, verbatim) or `retention`.

### A reference entry

```json
{"id": "ref-012", "source": "https://…", "who": "the channel or person", "added_by": "user",
 "learn": "the number lands heavy, with a short camera hit", "timing": "number complete 2 frames before the word",
 "tags": ["number", "type"], "file": "ref-012.mp4"}
```

Clips stay in the studio: used for timing and look only, never rendered into an output, never uploaded, never sent to
a rented machine.

## 2. The loop per video

1. **Before.** The director reads the lessons, the last report, the baseline and new references (`director.md`).
2. **Plan.** Column (c) names the upgrade(s) and where each comes from (a lesson id, a reference id, a baseline gap or
   a retention finding).
3. **After the build** (on top of the per-piece bundle, `review.md`), the Critic checks the video as a whole:
   - each chosen upgrade: landed or not, with evidence (time, frame);
   - against the baseline: at least **one named thing better**, and nothing the baseline did right is now worse (the
     measured values and the lessons are the checklist). If nothing is better, the version goes back to the Editor
     once, with the gap named. If the second try is still not better, the Showrunner says so plainly on the preview
     card instead of hiding it;
   - honest gaps to every reference used.
4. **After the user has seen the video.** `crewcut motion report <episode>` writes the skeleton of
   `review/motion-report-vNNN.md`; the Critic fills it (sections: better, behind, upgrades landed, proposals),
   appends 1 to 5 lessons (the report step fails without at least one), proposes library candidates (pieces that
   passed and fit a second video: `crewcut motion promote`, card `--kind template`) and, when this video is better
   overall, a new baseline (card `--kind baseline`). The first approved video becomes the bar.
5. **After publishing, when data exists.** `crewcut youtube retention <episode>` reads the audience retention curve
   (YouTube Analytics, read-only permission `yt-analytics.readonly`) and maps it onto the motion moments: the
   retention change over each moment and the 5 s after it, against the video's own slope around it. The numbers go
   into the report and the library notes ("number_roll: held viewers in 3 of 4 uses").

## 3. Retention: a hint, not proof

- One video is a small sample, and a moment's content matters more than its form.
- A retention finding becomes a lesson **only when the same pattern shows in at least 3 videos**. Before that it is
  listed as "watch" in the report, with the videos it was seen in.
- Shorts often have no usable per-second curve through the API. Where data is missing, the report says "no retention
  data" and nothing else changes.

## 4. What the Critic enforces

- **"A video that is not better than the bar in at least one named way goes back."** Name the way, with time and frame.
- Every chosen upgrade is checked: landed or not.
- Every big moment gets one sentence on what the reference still does better. Never empty.
- No lesson, baseline move or library entry without evidence (episode, time, frame).
- The baseline never moves silently and never moves down: only on the user's yes on a `baseline` card.

## 5. Keeping the lessons useful

Lessons are rules with evidence, not a diary. Above 40 lines the Critic merges duplicates and proposes the merge as a
card. A lesson the user contradicts is removed, with a note. Lessons that hold for everyone (an engine pitfall, "a
symmetric splash reads as a sun icon") may be proposed for this skill's `lessons.md` through a normal pull request by
the maintainer, never automatically.

## 6. For the director, in one screen

- Before planning: which lessons apply to this video? Cite their ids in column (c).
- What did the baseline do best? Do not fall below it there.
- Which reference shows the move you want? Measure its timing at 60 fps before you build.
- One upgrade at least, chosen on purpose, small is fine: a caused exit instead of a hard cut counts.
