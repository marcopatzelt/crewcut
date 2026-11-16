---
name: onboarding
description: "First start of Crewcut: the user pastes links (website, YouTube channel, social), nothing else. The Brand identity reads them, derives logo, colours and fonts from the site's CSS, tone from its texts, niche, language and audience from the channel's videos and titles, writes the style pack brand/ with a source for every value, renders a 10-second preview and asks with one profile card. Corrections in one sentence become the first rules. Use when: \"paste your links\", \"set up my brand\", \"onboarding\", \"my style\", \"use my website's colours\", \"read my channel\", \"profile is wrong\", \"logo smaller\". Not for one episode's work."
---

# Onboarding

The Brand identity turns a few pasted links into the user's style pack. The user types nothing but links and, at most,
one sentence. **No form, ever:** what the agent can find out, it finds out; what only the user knows, the user says in
one sentence.

All messages of this step go to the pseudo-episode `_onboarding`:
`crewcut say --episode _onboarding "…"`, `crewcut doing --episode _onboarding "Reading your website" --progress 0.2`.

## 1. Start

- The user pasted links in the composer ("Paste your links"). Sort them: website, YouTube channel, other social pages.
- `crewcut brand init` creates `brand/` in the studio from the neutral pack, if it does not exist yet. Work only there.
  Never change `packs/`, `skills/` or `templates/` of the app: updates replace them.
- `crewcut onboard <link> … --json` collects the raw facts with their source: colours, custom properties and fonts from
  the site's CSS, logo candidates, words from the pages, the YouTube channel and its recent videos. It saves them to
  `brand/fetched.json`. The facts are not decisions: you decide what goes into the pack, and you read a page yourself
  when a fact is missing or looks wrong.

## 2. Website

- **Logo:** an SVG or image in the header or the home link; else the site icon (`<link rel="icon">`, Apple touch icon);
  the social preview image (`og:image`) only as a last resort, it is often a banner. Save it as `brand/logo.svg` (or
  `.png`) and set `brand.json` `logo.file`.
- **Colours:** from the CSS. First custom properties with names like primary, brand, accent; then the colours of
  buttons, links and headings; ink and paper from the body text and background. Ignore colours that only appear in
  images, ads or cookie banners. Write `colors.ink`, `colors.paper`, `colors.accent` (and more if clear) as `#RRGGBB`.
- **Fonts:** the `font-family` of headings and body text and the `@font-face` sources. See section 4 for licences.
- **Tone:** from the headline, the about text and a few pages: plain or playful, formal or casual, who it speaks to.
  Write `channel.json` `tone` in a few words and, if the texts show it, words to use and to avoid in `voice.md`.

## 3. Channel

- The recent videos are in `brand/fetched.json`. For the top videos and the median:
  `python3 skills/idea/scripts/idea.py channel <channel link> --recent 10 --top 10 --json` (YouTube Data API, needs
  `YOUTUBE_API_KEY`).
- **Titles as patterns:** length, where the name stands, hooks the user's best titles share, question or statement,
  numbers, capitals. Write the limits to `channel.json` `title` and the click words that recur in the top titles to
  `voice.md` under `## Title hooks` (format: `- label: word, word`).
- **Thumbnails as patterns:** face or no face and where, how many words, which colours. Write them to `thumbnail.json`.
- **Derive** niche, audience, language and country (from the video language and the titles), and neighbouring channels
  if the channel features some. Write them to `channel.json`.
- The user's own videos and pages come first. Other creators' videos only when the user pasted their links.

## 4. Fonts and licences

- Download only free fonts: fonts from Google Fonts or Fontsource, or fonts whose licence is the SIL Open Font License
  or Apache 2.0. Save them to `brand/fonts/` with their licence file and list them in `brand.json` `fonts.<role>.files`.
- A paid or unclear font (Adobe Fonts, a commercial foundry, no licence found) is never fetched from the user's site.
  Pick a free font of the same kind (geometric or humanist sans, serif, mono; similar width and weight) and say so:
  `crewcut say --episode _onboarding "Your site uses <font>, which is paid. I use <free font>, which looks similar."`
  The profile row names the replacement as well.

## 5. Write the style pack

- Every value you set gets a source in that file's `sources` map, with the date:
  `"colors.accent": "from your website, 16 Nov 2026"`, `"language": "from your channel, 16 Nov 2026"`,
  `"captions": "you said so, 16 Nov 2026"`. Values you did not find keep the neutral default ("Crewcut default").
- Where tokens are not enough, copy the scene templates you need into `brand/templates/` and adapt the copies. Never
  edit the app's templates.
- `crewcut brand check` must show no problems.

## 6. Preview and the one card

1. `crewcut brand preview --out brand/preview.mp4`: a 10-second sample in the new style.
2. One card: `crewcut card propose --episode _onboarding --step onboarding --kind profile --title "Your profile"
   --file brand/preview.mp4 --body "<the style in one sentence>"`, then `crewcut card wait <id>`.
3. The profile view shows logo, colours, font, the style in five sentences, niche and channel, each row with its source.
   It is read-only; a change is a sentence to the agent.

## 7. Corrections become the first rules

The user answers in one sentence ("no captions", "logo smaller", "the blue is wrong"):

1. Change the value in `brand/`, with the source "you said so, <date>".
2. Propose the rule: `crewcut rule propose --step <step> --rule "<the rule in one sentence>" --source "<the user's
   words, short>"`. The user accepts it with one yes.
3. Render the preview again and post a new profile card.

## 8. The engine, said once

The crew runs on Claude Code by default, or on Codex (beta); both use the user's own subscription. The first message of
onboarding names the engine. If the user says "use Codex" (or "use Claude"), run `crewcut engine use codex` (or
`claude`). When it reports a missing login, run `crewcut engine login codex --episode _onboarding`: the sign-in link and
the one-time code appear in the chat by themselves (device-code login must be on in the user's ChatGPT security
settings). Never ask the user to type a key into the chat.

## 9. No website, no channel

The neutral style stays. Post the profile card with the neutral preview and the body "Say in one sentence what your
channel is about." The answer fills niche, audience and language (source: "you said so").

## Honest limits

- The agent can be wrong: a logo from an ad, a colour from a banner, a font it may not load. That is why every row has a
  source and there is one preview.
- A sample video can be measured (pace, colours, shares), not rebuilt one to one. Onboarding gives a clean start, not a
  finished house style.
- 3D is the most work per brand. Colours and fonts go through tokens; own models and an own stage are planned per user.

## Planned

- Measuring one to three of the user's own videos: cuts per minute, speaker share, captions, kind of graphics, music
  level, into `edit-style.json` and `brand/references/`.
- The user's way of speaking from the transcripts of their own videos (`crewcut transcribe`), into `voice.md`.
- Untested: the whole flow has not run against a real website and channel yet.
