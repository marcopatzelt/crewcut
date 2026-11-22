# The crew

Crewcut makes a video with eight crew members. Each one is a small file here: who it is, what it may do, and a short
soul, the way it works. The soul rides the system prompt of every run, so it stays short; the long knowledge lives in
the skills it loads (`skills/<name>/SKILL.md`).

| Mark | Name | Role | Skills | Steps | May spend | May publish |
|---|---|---|---|---|---|---|
| SR | Showrunner | Runs the episode through the ten steps and gives each step to the right crew member. | episode | all | no | no |
| SC | Scout | Finds the next idea in data, writes the title and thumbnail text, and runs the tests a video needs. | idea, title | idea, title, proof (optional) | no | no |
| WR | Writer | Interviews the user before the first draft, then writes the script in their own words, from the approved title and the facts it gathers. | script | script | no | no |
| ED | Editor | Ingests the recording and builds the video: speaker cut, 2D and 3D inserts, motion graphics, sound and assembly. | edit, 3d-scene, motion | record, edit | yes: rented GPUs | no |
| CR | Critic | Checks every version before the user sees it, and is never the one who built it. | cut-check, motion | script (quiet claim check), edit, thumbnail | no | no |
| DE | Designer | Makes the thumbnail and its test variants, and the look of new motion graphics. | thumbnail, motion | thumbnail | yes: the paid image API | no |
| PU | Publisher | Uploads the finished episode and reads its results after 48 hours. | upload | upload, results | no | yes |
| BR | Brand | Sets up the user's style pack from their links and keeps it up to date. | onboarding | (first start) | no | no |

Spending and publishing always go through a card as well: `spend` for money, `publish` for every upload.

## File format

```markdown
---
id: scout
name: Scout
mark: SC               # two letters, used where a picture does not fit (logs, the terminal)
avatar: magnifier      # the prop Slate holds in the app: headset, magnifier, pencil, scissors, clipboard, brush, plane, swatches
role: "Finds the next idea in data, writes the title and thumbnail text, and runs the tests a video needs."
model: plan            # plan = strong model (plans, checks), work = cheaper model (does the bulk)
skills: [idea, title]
steps: [idea, title, proof]
may_spend: false
may_publish: false
sources:
  - {name: "Vexian (Grant Owen's podcast)", url: "https://www.youtube.com/watch?v=41HMFGbENj4", used_for: "growth stages, titles"}
---

The soul: how I work, in the first person, at most about 1,500 characters.
```

`crewcut.team` reads these files. `sources` lists the people whose know-how the identity's skills distil: name, link
and what was taken. They have no connection to Crewcut and do not endorse it. A source can also be Crewcut's own
work, such as the launch film the motion method comes from; its name says so.

## Three rules for every identity

1. **The Critic is never the builder.** The one who checks a version is never the one who made it.
2. **Rights live in the identity.** Only identities with `may_spend: true` spend money, only `may_publish: true`
   publishes. Both still need the user's card each time.
3. **A new rule goes to the skill or to `brand/rules/`, never into the soul.** The soul stays short and changes rarely.
