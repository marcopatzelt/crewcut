<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/slate-dark.svg">
  <img alt="Slate, the Crewcut mascot: a clapperboard with a face" src="docs/brand/slate.svg" width="112">
</picture>

# Crewcut

### Your Claude Code subscription, now a YouTube crew.

**Seven AI agents take your video from idea to upload. You record and say yes.<br>
Open source, one Docker container, on your own computer.**

[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/marcopatzelt/crewcut/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/marcopatzelt/crewcut/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/status-v0.1%20pre--release-orange?style=flat-square)

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/crewcut-dark.png">
  <img alt="Crewcut: your episodes on the left; in the middle the chat with the crew and one card that waits for your yes; on the right the crew at work and what it cost" src="docs/readme/crewcut-light.png" width="100%">
</picture>

</div>

**Crewcut is for people who make YouTube videos alone and appear in them.** You bring the idea and the recording. The
crew does the rest: it finds the topic in data, writes title and script, cuts your takes, builds 2D and 3D graphics in
your style, checks every version, makes the thumbnail and uploads through the YouTube API. It runs on the Claude Code
subscription you already pay for, so the crew needs no API keys.

You see who works on what, live. Every decision is one card with one button: no forms, no settings dialogs. Nothing is
published, rented or paid for without your yes.

> **Status: v0.1, pre-release.** Everything in this README is built and unit-tested, and the image is built and
> smoke-tested in CI for amd64 and arm64, with real 2D, 3D and assembly renders. A full episode with real footage has
> **not** run yet; that is the next step. What does not exist yet is marked *planned*. The pictures show demo data.

<img alt="A card asks whether to render nine 3D scenes on this machine or on a rented GPU; the choice switches, one press, the card folds away and the Editor starts in the crew column" src="docs/readme/crewcut-demo.webp" width="100%">

<p align="center"><sub>One card, one choice, one press. Demo data, rendered in CI from the current app.</sub></p>

## Quick start

You need Docker and a Claude subscription with Claude Code.

```bash
git clone https://github.com/marcopatzelt/crewcut.git && cd crewcut
claude setup-token     # once, on any computer with a browser: prints your token
./start.sh             # asks for the token once (hidden), writes .env, runs docker compose up
```

Open **http://localhost:4747**, paste your links (website, channel), and say your first idea:

> Next video: I ran five local AI models on a $900 laptop. Which one is worth it?

The Scout comes back with a topic card. Details, Windows and GPUs: [docs/getting-started.md](docs/getting-started.md).

## How it works

Ten steps. The crew works between them; you decide at each card.

```mermaid
flowchart TB
    subgraph before["Before you record"]
        direction LR
        s1["1 · Idea<br/>Scout"] --> s2["2 · Title<br/>Scout"] --> s3["3 · Proof<br/>Scout"] --> s4["4 · Script<br/>Writer"]
    end
    subgraph after["After you record"]
        direction LR
        s6["6 · Edit<br/>Editor, checked by the Critic"] --> s7["7 · Thumbnail<br/>Designer"] --> s8["8 · Blog<br/>planned"] --> s9["9 · Upload<br/>Publisher"] --> s10["10 · Results<br/>planned"]
    end
    s5(["5 · Record<br/>you, with the teleprompter"])
    s4 --> s5 --> s6
    classDef you fill:#0f7b5f,color:#ffffff,stroke:#0f7b5f
    classDef planned stroke-dasharray: 4 4,color:#888888
    class s5 you
    class s8,s10 planned
```

| Step | What the crew does | What you decide |
|---|---|---|
| 1 Idea | The Scout looks at what works in your niche and ranks topics, title and thumbnail first | the topic |
| 2 Title | Writes title and thumbnail text before a word of script exists | the title |
| 3 Proof | Runs the test the title promises and collects the numbers that go into the video | what goes in |
| 4 Script | The Writer writes in your voice, from your style pack | the script |
| 5 Record | Puts the script on your phone as a teleprompter (QR code, with a remote) | you record |
| 6 Edit | The Editor transcribes, cuts to the last full take of each sentence, builds 2D and 3D, mixes the sound; the Critic checks every version against your best video before you see it | the preview |
| 7 Thumbnail | The Designer makes the thumbnail and test variants | the thumbnail |
| 8 Blog | *planned* | |
| 9 Upload | The Publisher uploads through the API: video, thumbnail, captions, schedule, YouTube's altered-or-synthetic-content answer | publish, every time |
| 10 Results | *planned*: the 48-hour check | |

Every correction is one sentence, typed or spoken ("keep the part where I laugh", "no captions"). A correction that should
last becomes a proposed rule with the date and your words; one yes adds it to your style pack.

## Why it is different

These are rules in the code, not settings a prompt can talk around.

- **You film yourself.** Crewcut makes no AI presenter and no AI voice. The video is your recording.
- **You approve exactly what you saw.** A card stores the checksum of the file you looked at. Any change is a new version
  and needs a new yes.
- **Nothing is published or paid for without your card.** Only the Publisher may upload, only the Editor may rent, and
  both still need your card. A monthly cap stops all spending (default $20).
- **The builder never checks its own work.** The Critic checks every cut before you see it.
- **Your recordings stay on your computer.** Only scene code and fonts go to a rented GPU, never your footage (unless you
  approve it on a card), never your keys.
- **Your taste is yours.** Skills hold the know-how; your style pack holds the taste. Updates of the app never touch it.
- **The newest Claude Code, with a way back.** A new Claude Code release is live at the next start, after a smoke test.
  If it fails twice, Crewcut goes back to the last good version and tells you. Every Claude Code flag passes through.

## Meet the crew

<p align="center">
  <img src="docs/brand/crew/showrunner.svg" width="64" alt="Showrunner">
  <img src="docs/brand/crew/scout.svg" width="64" alt="Scout">
  <img src="docs/brand/crew/writer.svg" width="64" alt="Writer">
  <img src="docs/brand/crew/editor.svg" width="64" alt="Editor">
  <img src="docs/brand/crew/critic.svg" width="64" alt="Critic">
  <img src="docs/brand/crew/designer.svg" width="64" alt="Designer">
  <img src="docs/brand/crew/publisher.svg" width="64" alt="Publisher">
  <img src="docs/brand/crew/brand.svg" width="64" alt="Brand">
</p>

Every crew member is **Slate**, the Crewcut clapperboard, with the tool of its role. In the app Slate also shows the
state: asleep while it waits its turn, the bar ticking while it works, a small "?" sign when it needs you, the bar shut
with a check when it is done.

| | Crew member | What it does | May |
|---|---|---|---|
| <img src="docs/brand/crew/showrunner.svg" width="56" alt=""> | **Showrunner** | Runs the episode through the ten steps and answers you in the chat. Shows you nothing unchecked | |
| <img src="docs/brand/crew/scout.svg" width="56" alt=""> | **Scout** | Finds the topic in data, writes title and thumbnail text, runs the proof | |
| <img src="docs/brand/crew/writer.svg" width="56" alt=""> | **Writer** | Writes the script in your voice | |
| <img src="docs/brand/crew/editor.svg" width="56" alt=""> | **Editor** | Ingests your recordings, cuts the speaker, builds 2D and 3D, sound and assembly | rent a GPU, with your card |
| <img src="docs/brand/crew/critic.svg" width="56" alt=""> | **Critic** | Checks every version against your best video; never the one who built it | |
| <img src="docs/brand/crew/designer.svg" width="56" alt=""> | **Designer** | Thumbnail and test variants | |
| <img src="docs/brand/crew/publisher.svg" width="56" alt=""> | **Publisher** | Upload package and upload | publish, with your card |
| <img src="docs/brand/crew/brand.svg" width="56" alt=""> | **Brand** | Onboarding: builds your style pack from your links and names the source of every value | |

Each crew member is a real Claude Code agent (`crewcut:editor`, …) with a short identity in [`team/`](team/README.md) and
the skills of its step in [`skills/`](skills/). Crewcut loads itself into Claude Code as a plugin, so your own
`.claude/` settings, skills and MCP servers keep working.

## Your style, from your links

Crewcut starts with a calm neutral style: Inter, black and white, one accent, quiet cards and counters, captions as
keywords. On the first start you paste your links. The Brand crew member reads them: logo, colours and fonts from your
site's CSS, tone from your texts, patterns from your recent videos. It writes your style pack to `brand/` with the
source of every value, renders a 10-second sample in your style and shows you one profile card.

```
brand/
  brand.json        colours, fonts, logo, shape, motion, 3D stage
  edit-style.json   pace, captions, music, loudness, speaker share
  channel.json      niche, audience, language, tone, topics to avoid
  thumbnail.json    layouts, face, max words, reference photo
  voice.md          how you speak
  rules/<step>.md   learned rules, with date and your words
```

Paid fonts are never downloaded from other sites; Brand picks a similar free font and says so. [`examples/striq/`](examples/striq/)
is a real, dated style pack from the author's channel (rules and values only). See [docs/style-packs.md](docs/style-packs.md).

## Fast with a rented GPU, free without one

Everything runs on your computer. 2D graphics, cutting and sound need no GPU. 3D is the slow part: on a laptop CPU, a
frame of the author's 3D style took about 144 seconds, so a three-second 3D insert takes about three hours. A rented
RTX 4090 renders the same frame in about 20 to 70 seconds, at about $0.35 to $0.50 per hour.

Before a heavy job the Editor estimates both ways and, only when renting saves a lot, asks once:

> 9 scenes: about 3 h on this machine, or about 12 min for about $0.60 on a rented GPU. **[Rent a GPU]** · Local is fine too.

Choose this machine and it does not ask again in that episode. Every rental has a budget, a monthly cap, a watchdog with
a deadline on the machine, a local guard that deletes forgotten machines, and an entry in the cost book with proof that
nothing is left running.

**Referral disclosure:** Crewcut suggests Vast.ai through the author's referral link. The author earns 3% of your Vast
spend as credit; it costs you nothing extra. Change or remove it in `config/compute.toml`. If you already have a Vast
key, Crewcut does not show the link. Details: [docs/compute.md](docs/compute.md).

## How Crewcut compares

Other open-source video agents are good at other jobs. From each project's README on 16 November 2026:

| | Starts from | The picture | Runs on |
|---|---|---|---|
| **Crewcut** | your idea and **your recording** | your takes, cut, with 2D and 3D graphics in your style | your Claude Code subscription (Codex in beta) |
| [youtube-automation-agent](https://github.com/darkzOGx/youtube-automation-agent) | topics it researches for your channel | generated narration and visuals; a local slideshow by default, AI video providers optional | an API key for a text provider (Gemini, OpenAI, OpenRouter, DeepSeek and others) |
| [OpenFilm](https://github.com/openfilm/openfilm) | a prompt to your coding agent | films written as web pages, with a local editor to change anything | Codex, Claude Code or any coding agent; your own keys for generated media |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | a topic or keyword | HD short videos from an automated workflow | API keys for model providers |

Pick Crewcut when you stand in front of the camera yourself and want everything around the recording done. Corrections
to this table are welcome.

## Two engines

| Engine | Status | Login |
|---|---|---|
| **Claude Code** | default | `claude setup-token` once; the token stays in the container's environment |
| **Codex** | beta, not yet run on a real episode | say "use Codex": a sign-in link and a one-time code appear in the chat |

Both run on your own subscription. Switch by saying it ("use Codex", "back to Claude"). Crewcut never pins the engine:
each start brings the newest release, with a smoke test and a way back. Details: [docs/engine.md](docs/engine.md).

## Built on the playbooks of

The skills distil public know-how from these creators into our own short rules. The crew names the method when it
applies one ("Scout: niche check after Vexian's growth stages").

| Source | What the crew learned | Used by |
|---|---|---|
| **Vexian**, in Grant Owen's podcast ["The Crazy Genius Who Solved The Youtube Algorithm"](https://www.youtube.com/watch?v=41HMFGbENj4) | finding a niche and topics, growing in stages, titles and thumbnails | Scout, Writer, Designer, Publisher |
| **MrBeast**'s production handbook ([public since 2024](https://simonwillison.net/2024/Sep/15/how-to-succeed-in-mrbeast-production/)) | the first minute; title and thumbnail before the shoot | Scout, Writer, Showrunner |
| **Alex Hormozi**'s editing and caption style, by his editor Ryan Magin ([channel](https://www.youtube.com/@AlexHormozi)) | fast cutting, word captions | Editor, Critic |
| **[fern](https://www.youtube.com/@fern-tv)** (YouTube channel) | inspiration for the 3D clay look | Editor, Designer |
| **[Nate Herk](https://www.youtube.com/@nateherk)** | a title for everyone, the business inside the video; Shorts as proof | Scout |
| Reel storytelling of [Farza](https://www.youtube.com/@farzatv), [Chris Raroque](https://www.youtube.com/@raroque), [Roy Lee](https://www.youtube.com/@im_roy_lee), [Riley Brown](https://www.youtube.com/@rileybrownai), [Varun Mayya](https://www.youtube.com/@VarunMayya), [Codie Sanchez](https://www.youtube.com/@CodieSanchezCT) | first person, the turn, uneven numbers | Writer |

Crewcut is not affiliated with or endorsed by any of these creators. The skills contain our own summaries, not their
content.

## Under the hood

```mermaid
flowchart LR
    you([You]) -- "one sentence, one yes" --> ui["Web UI<br/>localhost:4747"]
    phone([Phone]) -- QR code --> tp["Teleprompter<br/>:4748"]
    ui <--> cond["Conductor<br/>10 steps, job queue,<br/>cards, cost book"]
    cond --> crew["The crew<br/>Claude Code agents,<br/>your subscription"]
    crew --> skills["skills/<br/>know-how"]
    crew --> pack["brand/<br/>your taste"]
    crew --> tools["Tools<br/>ffmpeg, Chromium 2D,<br/>Blender 3D, whisper"]
    tools -. "optional, with your yes" .-> gpu[("Rented GPU<br/>same image,<br/>no login data")]
    crew --> yt["YouTube Data API"]
    cond <--> studio[("Studio folder<br/>episodes/, brand/")]
```

- **The conductor** holds the order of the steps and wakes the right crew member. It costs no tokens.
- **Each crew member** is a run of your Claude Code with its identity, the skill of its step and the state of the
  episode. It reports what it does in the crew column and asks for decisions only with cards.
- **Heavy work** (renders, transcription, assembly) runs one job at a time, on your machine or, with your yes, on a
  rented GPU from the same image.
- **Configuration** is optional: defaults live in `config/*.toml`, your changes in `studio/config/`, secrets only in
  `.env`. You can also just say it ("use the highest effort for the Critic").

More: [docs/architecture.md](docs/architecture.md), [docs/api.md](docs/api.md), [DESIGN.md](DESIGN.md).

## FAQ

**Does the AI film me or speak for me?** No. You record. Crewcut prepares script and teleprompter before, and does the
rest after.

**What does it cost?** Your Claude plan (or ChatGPT plan for Codex). Rented GPU time and paid image APIs only if you
choose them; the money row in the app shows every cent, and there is a monthly cap.

**Do I need a GPU or a Mac?** No. Any computer with Docker works: Linux, Windows, macOS on Apple chips. A GPU (your own
NVIDIA card or a rented one) only makes 3D and transcription faster. Docker on macOS cannot use the Apple GPU, so 3D runs
on the CPU or a rented GPU there. A test on a real Mac is still to come.

**Is my data uploaded anywhere?** No account, no Crewcut server, no telemetry. Your studio folder stays on your computer.
The crew uses your Claude login; uploads go to your YouTube channel only after your yes.

**Can I use my own Claude Code setup?** Yes. Crewcut is a Claude Code plugin. Your `.claude/` settings, skills, agents
and MCP servers keep working, and any Claude Code flag can be passed through.

**Can the crew members talk to each other?** Built, and off until it is measured: the Critic can send its findings
straight to the Editor, with hard limits. See [docs/crew-talk.md](docs/crew-talk.md).

## Roadmap

| Stage | Content | Status |
|---|---|---|
| 0, foundation | studio extracted from the author's own setup, taste moved into style packs, Docker image for amd64 and arm64, CI | done |
| 1, v0.1 | one command, ten steps, cards, teleprompter, speaker cut, 2D, 3D local and rented, checks, thumbnail, API upload, learned rules, onboarding, live crew column | built; first full episode next |
| 2, whole chain | Shorts, music on rented GPUs, analytics and the 48-hour check, A/B variants, approval from the phone, style measured from your own videos | *planned* |
| 3, for everyone | shareable style packs, your own 3D stage and models, more GPU providers, Codex out of beta | *planned* |
| 4, breadth | blog, Instagram output, a small Mac app that starts Docker for you | *planned* |

## Documentation

[Getting started](docs/getting-started.md) ·
[Architecture](docs/architecture.md) ·
[Engines](docs/engine.md) ·
[Style packs](docs/style-packs.md) ·
[Recording and cut](docs/recording.md) ·
[Rendering](docs/rendering.md) ·
[Compute](docs/compute.md) ·
[YouTube](docs/youtube.md) ·
[Web UI](docs/ui.md) ·
[Crew talk](docs/crew-talk.md) ·
[HTTP API](docs/api.md) ·
[First real episode](docs/first-real-episode.md) ·
[Integration tests](docs/integration-test.md)

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), [DESIGN.md](DESIGN.md) for UI work and
[SECURITY.md](SECURITY.md) for security problems. Please follow the [code of conduct](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE), copyright Marco Patzelt. The mascot Slate was made by the author with ChatGPT image generation and
redrawn by hand as SVG ([`docs/brand/`](docs/brand/)); it is part of the MIT-licensed repository. Third-party tools keep their own licences: ffmpeg (LGPL/GPL build from Debian),
Blender (GPL, called as a program, not linked), Chromium (BSD), Inter (SIL Open Font License), Claude Code and Codex
(installed from their official packages at first start, not shipped).
