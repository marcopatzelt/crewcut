# The motion pass: the director's method

The motion director is a responsibility, not a crew member: the Editor leads it (purpose, timing, build), the
Designer joins for the look. The pass runs once per video after the speaker cut and its words exist, and again in
short form for each Short. Its output is one motion plan with three columns and one card.

## 1. Read, in this order

1. **The promise.** The idea, the approved title and thumbnail text (`brief/TITLE-vNNN.md`), the script
   (`brief/SCRIPT-vNNN.md`) with the Writer's marks below its `---` line, the proof (`brief/PROOF-vNNN.md`). What must
   this video deliver, and which numbers are proven?
2. **What is really said, and when.** The speaker cut and its words (`work/words-vNNN.json`). Plan times come from
   these words, never from the script.
3. **The channel's lessons.** `brand/rules/motion.md` (one dated lesson per line, each with an id) and the last
   video's `review/motion-report-vNNN.md`: what was behind, what to fix next.
4. **The bar.** `brand/baseline.json`, block `motion` (the best video so far, its named strengths, its measured
   values) and `brand/references/motion/index.json` (reels and videos with a reason each: what to learn from it).
5. **Only now the shelf:** `crewcut motion library` (app templates, the pack's own, earlier custom pieces, each with
   a sample loop, where it was used and how it reviewed).

Reading the shelf first makes the video look like the shelf. Reading the lessons first makes it better than the last.

## 2. Per beat: three questions

A beat is one statement of the script, usually 1 to 3 sentences.

1. **What must the viewer understand or feel here?** One line. "Believe the price." "See the hand-off." "Feel that
   it worked." If the speaker's face and voice already do it: nothing. **Most beats get nothing.** The speaker is the
   video; motion supports him or her.
2. **What picture does that in 2 seconds?** Describe a thing that happens: "the price rolls like a meter and lands
   on thirty", "four jobs leave the laptop, a GPU lights up, frames come back". Not "a `number_roll`".
3. **Which column?**
   - (a) the shelf has a piece that shows exactly this picture (params only);
   - (b) nothing on the shelf shows it: build it new for this video;
   - (c) a stronger version would lift the whole video (also: a better use of what exists, such as timing,
     transitions or colour).

The Writer's marks (`[[motion: number | "30 cents per million tokens"]]`, at most 5) are wishes. Take them as
candidates; drop them when the face carries the beat.

## 3. The plan file

`crewcut motion plan <episode>` writes the skeleton from the words and the marks, lists the shelf with loops, and
validates the finished file. Output: `edit/motion-plan-vNNN.md` (people) and `.json` (tools), next free number.

```
# Motion plan v001: 003-local-llms          bar: 002-… (baseline), last video: 5 motion moments, 1 custom

## Beats
| # | Time | The viewer must … | Picture | Column | Piece | Length | Cost |
| 1 | 0:07 | believe the number | the price rolls and lands on "thirty" | a | number_roll {value: 30, unit: cents} | 4.0 s | 0 |
| 4 | 1:12 | see the hand-off | 4 jobs leave the laptop, a GPU lights up, frames return | b | custom "gpu-handoff", 1 plate | 5.5 s | ~$0.30, cap $1 |
| 6 | 2:40 | feel the result | — speaker, punch-in | – | – | – | – |

## (a) What we have that fits
## (b) What we build new for this video        (per piece: a 3-line brief and why no shelf piece does it)
## (c) What would make this video clearly better than the last one
| Upgrade | Why (lesson, reference, baseline gap, retention) | Effort | Cost | Chosen |
## Budget and density
```

Rules the validation enforces:

- Every row has purpose ("the viewer must …"), picture and column.
- Column (c) holds 2 to 4 candidates, each with a source (a lesson id from `brand/rules/motion.md`, a reference id, a
  named gap to the baseline, or a retention finding), and **at least one is chosen**. A plan without a chosen upgrade
  fails with one sentence. When lessons exist and none is cited, the validation warns.
- Effort is S, M or L (rounds of work). Cost is money for rented GPUs, with a cap. No time estimates.
- The density and budget line is computed, not typed: full-frame moments against the pack's limit, all motion against
  the per-minute limit, heroes, GPU money against the cap ($2 long-form, $0.50 Short by default).
- Column (b) is the default when the idea needs a picture the shelf does not have. Never fill it to look busy.

## 4. The card and after

- `crewcut card propose --episode $CREWCUT_EPISODE --step edit --kind motion-plan --title "Motion plan v001" --file
  edit/motion-plan-v001.md`: the three columns as media (a loop of each shelf piece, the brief line of each new piece,
  each upgrade with its reason), density and budget in one line. The user may strike single rows; that writes a new
  plan version.
- Column (a) may be built while the card is open. Columns (b) and (c) wait for the yes. GPU money still gets its own
  `spend` card at the moment of renting, with the plan's number as the cap.
- After the yes, `edit/make_plan.py` turns each row into a `"kind": "motion"` entry with `"beat"` and `"column"`. Then
  `crewcut render plan` (it refuses motion entries without a row in an approved plan).
- New pieces go through the stages in `SKILL.md` (brief, design, style frame, build, review, iterate, final, keep).

## 5. A worked example

Video: "I ran my edit on a rented GPU for 40 cents" (6:10, long form). Lessons file has 7 lines; the last report
said "3 hard cuts out of full-frame pieces; the opening number was flat type"; the baseline is video 002.

| # | Time | Spoken | The viewer must … | Picture (before any template name) | Column |
|---|---|---|---|---|---|
| 1 | 0:04 | "Forty cents. That is what the whole render cost." | believe the price | the number rolls like a meter and lands heavy on "40", one line "per video" | c: heavy 3D number instead of flat type (lesson 2026-11-17-3) |
| 2 | 0:21 | "My laptop needed two hours for this." | feel the pain | nothing: the face says it, a punch-in | – |
| 3 | 0:58 | "Crewcut asks me first, with the price on a card." | see the card | the real card from the app, slides in beside the speaker, the price highlighted | a: recording on a card (2D `clip-card`) |
| 4 | 1:12 | "Four jobs leave, one GPU does them, frames come back." | see the hand-off | four job tiles leave a laptop outline, one GPU block lights up, frames fly back and stack | b: custom "gpu-handoff", one small plate |
| 5 | 2:05 | "Three steps: estimate, rent, destroy." | follow the order | the three words roll, the box lands on each as it is said | a: `word_reel` |
| 6 | 2:40 | "And it looked better than before." | feel the result | nothing: the result plays full screen as a recording | – |
| 7 | 5:50 | "No machine left running." | trust the end | the ledger line "0 machines" lands beside the speaker | a: `keyword_pop` |

Column (c), candidates:

| Upgrade | Why | Effort | Cost | Chosen |
|---|---|---|---|---|
| Every exit from a full-frame piece is caused by a motion | last report: 3 hard cuts; lesson 2026-11-17-1 | S | 0 | yes |
| Opening number as a heavy 3D word instead of flat type | lesson 2026-11-17-3; reference ref-012 "number lands heavy" | M | ~$0.25 | yes |
| The GPU price table as a custom comparison instead of a screenshot | the baseline does tables better | M | 0 | no (next video) |

Density: full frame 3 of at most 5; all motion 5 in 6:10 (at most 12); heroes 1; GPU about $0.55 of the $2 cap.
Two beats (2 and 6) are deliberately left to the speaker. The pictures were written down before any template name.

## 6. Shorts

The same pass, shorter: 3 to 5 motion moments in total, at most 2 full frame, at most 1 hero (better: reuse the long
video's). Start from the Short's own script, not from the long video's plan. Column (c) still needs one chosen
upgrade. Cap $0.50.
