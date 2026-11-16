// Demo data, shaped exactly like docs/api.md. Test data only: made-up episodes, no real accounts or messages.
// Times are relative to the moment the page loads, so "40 min ago" stays true in every screenshot.
import type {
  Activity,
  Card,
  EpisodeDetail,
  Identity,
  Message,
  Profile,
  PrompterLink,
  PrompterScript,
  State,
  Step,
  StepStatus,
} from "../api/types";
import profileJson from "./profile.json";
import { DEMO_QR_SVG } from "./qr";

export const STEP_LABELS: Array<[string, string]> = [
  ["idea", "Idea"],
  ["title", "Title"],
  ["proof", "Proof"],
  ["script", "Script"],
  ["record", "Record"],
  ["edit", "Edit"],
  ["thumbnail", "Thumbnail"],
  ["blog", "Blog"],
  ["upload", "Upload"],
  ["results", "Results"],
];

export function steps(statuses: StepStatus[]): Step[] {
  return STEP_LABELS.map(([id, label], i) => ({ id, n: i + 1, label, status: statuses[i] ?? "open" }));
}

export interface DemoData {
  /** The card and the waiting row the scripted sequence adds, then the row it starts after the yes. */
  playCard: Card | null;
  playWaiting: Activity | null;
  playRender: Activity | null;
  state: State;
  details: Record<string, EpisodeDetail>;
  messages: Record<string, Message[]>;
  cards: Card[];
  team: Identity[];
  logs: Record<number, string[]>;
  profile: Profile;
  prompter: PrompterLink;
  script: PrompterScript;
}

/** What a job's engine reported about itself (docs/api.md). Made-up demo values. */
function ran(model: string, effort: string | null) {
  return { engine: "claude", model, effort, engine_version: "2.1.325" };
}

/**
 * The demo data. `play` is the start of the scripted sequence (?demo=1&play=1): the GPU card and the Showrunner's
 * waiting row are not there yet; the timeline in backend.ts adds them, using `playCard` and `playWaiting`.
 */
export function makeDemo(now = Date.now(), opts: { play?: boolean } = {}): DemoData {
  const ago = (seconds: number) => new Date(now - seconds * 1000).toISOString();
  const MIN = 60;
  const H = 3600;
  const D = 86400;

  const team: Identity[] = [
    {
      id: "showrunner",
      name: "Showrunner",
      role: "Runs the episode through the ten steps and talks with you.",
      mark: "SR",
      skills: ["episode"],
      may_spend: false,
      may_publish: false,
      soul: "I keep the episode moving. I ask you only when a step needs your yes, and I ask in one sentence.",
      sources: [],
    },
    {
      id: "scout",
      name: "Scout",
      role: "Finds the topic, the title and the proof.",
      mark: "SC",
      skills: ["video-idea", "video-title", "proof"],
      may_spend: false,
      may_publish: false,
      soul: "I look at what your audience already watches, then bring three topics and the numbers behind them.",
      sources: [
        {
          name: "Vexian, in a podcast with Grant Owen",
          url: "https://www.youtube.com/watch?v=41HMFGbENj4",
          what: "Niche and topics, growth in stages, titles",
        },
        { name: "MrBeast production handbook (public since 2024)", what: "The first minute; title and thumbnail before the shoot" },
      ],
    },
    {
      id: "writer",
      name: "Writer",
      role: "Writes the script in your voice.",
      mark: "WR",
      skills: ["video-script"],
      may_spend: false,
      may_publish: false,
      soul: "I write short sentences you can say in one breath, and I keep the words from your voice file.",
      sources: [],
    },
    {
      id: "editor",
      name: "Editor",
      role: "Ingests the recordings, cuts them and builds the graphics.",
      mark: "ED",
      skills: ["ingest", "speaker-cut", "render-2d", "render-3d"],
      may_spend: true,
      may_publish: false,
      soul: "I keep the last full take of every sentence and check the sound to the last second of each file.",
      sources: [{ name: "Alex Hormozi", what: "Fast cuts and word captions, after the style of his editor" }],
    },
    {
      id: "critic",
      name: "Critic",
      role: "Checks every cut against your best video.",
      mark: "CR",
      skills: ["cut-check"],
      may_spend: false,
      may_publish: false,
      soul: "I measure before I judge: speaker share, loudness, pauses and cut words.",
      sources: [],
    },
    {
      id: "designer",
      name: "Designer",
      role: "Makes the thumbnail.",
      mark: "DE",
      skills: ["thumbnail"],
      may_spend: false,
      may_publish: false,
      soul: "I make three variants and put each next to your best thumbnail.",
      sources: [],
    },
    {
      id: "publisher",
      name: "Publisher",
      role: "Uploads, schedules and reads the results.",
      mark: "PU",
      skills: ["youtube-upload"],
      may_spend: false,
      may_publish: true,
      soul: "I never publish without your yes on the exact file.",
      sources: [],
    },
    {
      id: "brand",
      name: "Brand",
      role: "Reads your links and builds your style pack.",
      mark: "BR",
      skills: ["onboarding", "style-pack"],
      may_spend: false,
      may_publish: false,
      soul: "I take colours, type and pace from what you already made, and I name the source of every value.",
      sources: [],
    },
  ];

  const ep3 = {
    id: "003-local-llms",
    title: "I ran five local AI models on a $900 laptop",
    step: "edit",
    steps: steps(["done", "done", "done", "done", "done", "waiting", "open", "skipped", "open", "open"]),
    updated: ago(6 * MIN),
    open_cards: 1,
  };
  const ep4 = {
    id: "004-subscription-website",
    title: "Does a $20 subscription build a whole website?",
    step: "script",
    steps: steps(["done", "done", "done", "working", "open", "open", "open", "skipped", "open", "open"]),
    updated: ago(3 * H),
    open_cards: 0,
  };
  const ep2 = {
    id: "002-agent-memory",
    title: "Why my agents stopped forgetting things",
    step: "results",
    steps: steps(["done", "done", "done", "done", "done", "done", "done", "skipped", "done", "done"]),
    updated: ago(2 * D),
    open_cards: 0,
  };

  const activity: Activity[] = [
    {
      job: 12,
      ...ran("sonnet", "medium"),
      episode: ep3.id,
      identity: "editor",
      step: "edit",
      doing: "Rendering 2D scene 6 of 14",
      progress: 0.42,
      status: "running",
      started: ago(252),
      seconds: 252,
      cost_usd: 0,
      equiv_usd: 0.41,
    },
    {
      job: 13,
      ...ran("sonnet", "low"),
      episode: ep3.id,
      identity: "designer",
      step: "thumbnail",
      doing: "Thumbnail prompt, variant 2 of 3",
      progress: 0.6,
      status: "running",
      started: ago(65),
      seconds: 65,
      cost_usd: 0,
      equiv_usd: 0.08,
    },
    {
      job: 11,
      ...ran("opus", "high"),
      episode: ep3.id,
      identity: "showrunner",
      step: "edit",
      doing: "Waiting for your yes on the GPU",
      progress: null,
      status: "waiting",
      started: ago(40),
      seconds: 40,
      cost_usd: 0,
      equiv_usd: 0.02,
    },
    {
      job: 10,
      ...ran("sonnet", "medium"),
      episode: ep3.id,
      identity: "critic",
      step: "edit",
      doing: "Cut check v1",
      progress: 1,
      status: "done",
      started: ago(6 * MIN + 228),
      seconds: 228,
      cost_usd: 0,
      equiv_usd: 0.19,
      ended: ago(6 * MIN),
    },
    {
      job: 9,
      ...ran("sonnet", "medium"),
      episode: ep3.id,
      identity: "editor",
      step: "edit",
      doing: "Speaker cut v1",
      progress: 1,
      status: "done",
      started: ago(12 * MIN + 680),
      seconds: 680,
      cost_usd: 0,
      equiv_usd: 0.33,
      ended: ago(12 * MIN),
    },
    {
      job: 8,
      ...ran("haiku", null),
      episode: ep3.id,
      identity: "editor",
      step: "record",
      doing: "Transcription, 41 min",
      progress: 1,
      status: "done",
      started: ago(25 * MIN + 542),
      seconds: 542,
      cost_usd: 0,
      equiv_usd: null,
      ended: ago(25 * MIN),
    },
  ];

  const state: State = {
    app: { version: "0.1.0", engine: "claude", engine_ok: true, gpu_local: false, onboarded: true },
    team: team.map(({ soul: _soul, sources: _sources, ...rest }) => rest),
    episodes: [ep3, ep4, ep2],
    activity,
    money: {
      today_usd: 0,
      episode_usd: { [ep3.id]: 0.62, [ep4.id]: 0, [ep2.id]: 3.16 },
      month_usd: 3.78,
      cap_month_usd: 20,
    },
  };

  const details: Record<string, EpisodeDetail> = {
    [ep3.id]: {
      ...ep3,
      project: {
        id: ep3.id,
        title: ep3.title,
        created: ago(3 * D + 2 * H),
        format: "landscape",
        fps: 25,
        step: "edit",
        next_action: "Render the graphics",
      },
      files: [
        { path: "export/003-local-llms-v001-preview.mp4", size: 182_400_000, kind: "video" },
        { path: "brief/SCRIPT-v003.md", size: 4_210, kind: "text" },
      ],
    },
    [ep4.id]: {
      ...ep4,
      project: { id: ep4.id, title: ep4.title, created: ago(1 * D + 5 * H), format: "landscape", fps: 25 },
      files: [],
    },
    [ep2.id]: {
      ...ep2,
      project: { id: ep2.id, title: ep2.title, created: ago(9 * D), format: "landscape", fps: 25 },
      files: [],
    },
  };

  const cards: Card[] = [
    {
      id: 3,
      episode: ep3.id,
      step: "title",
      kind: "title",
      identity: "scout",
      title: "Pick a title",
      body: "Recommendation: option 1. It names the result and the price.",
      options: [
        "I ran five local AI models on a $900 laptop",
        "Local AI on a cheap laptop: what really works",
        "Five local models, one laptop, no cloud",
      ],
      file: "brief/TITLE-v002.md",
      preview: null,
      sha256: "9c1d4e0b7a2f",
      status: "accepted",
      created: ago(3 * D),
      choice: 0,
      decided_at: ago(3 * D - 20 * MIN),
    },
    {
      id: 7,
      episode: ep3.id,
      step: "script",
      kind: "script",
      identity: "writer",
      title: "Approve the script",
      body: "612 words, about 4 minutes spoken.",
      options: null,
      file: "brief/SCRIPT-v003.md",
      preview: null,
      sha256: "3f2a9b71c0de",
      status: "accepted",
      created: ago(1 * D + 3 * H),
      decided_at: ago(1 * D + 2 * H),
    },
    {
      id: 9,
      episode: ep3.id,
      step: "edit",
      kind: "spend",
      identity: "editor",
      title: "Render the 9 3D scenes on a rented GPU?",
      body: "Both ways give the same picture. The rented one is faster; this machine is free.",
      options: null,
      file: "edit/plan-v001.json",
      preview: null,
      sha256: "a81e55f0d913",
      status: "open",
      created: ago(39 * MIN),
      data: {
        for: "render-3d",
        plan: "plan-v001.json",
        step: "edit",
        frames: 840,
        amount_usd: 0.6,
        budget_usd: 1.5,
        cap_usd: 1.5,
        estimate: {
          local_seconds: 11_400,
          local_measured: true,
          local_source: "CPU only, measured on scene 1",
          rented_seconds: 720,
          rented_usd: 0.6,
          rented_usd_worst: 1.5,
          gpus: 1,
          gpu_name: "RTX 4090",
          sentence: "840 frames: about 3 h 10 min here, or about 12 min on 1 rented GPU for about $0.60.",
        },
        referral: {
          url: "https://cloud.vast.ai/?ref_id=demo",
          note: "Referral link: the author of Crewcut earns 3% of your Vast spend as credit. It costs you nothing extra.",
        },
      },
    },
    {
      id: 5,
      episode: ep4.id,
      step: "title",
      kind: "title",
      identity: "scout",
      title: "Pick a title",
      body: "Recommendation: option 1.",
      options: ["Does a $20 subscription build a whole website?", "One subscription, one website, one weekend"],
      file: "brief/TITLE-v001.md",
      preview: null,
      sha256: "77b2c8e1f004",
      status: "accepted",
      created: ago(1 * D),
      choice: 0,
      decided_at: ago(23 * H),
    },
  ];

  const messages: Record<string, Message[]> = {
    [ep3.id]: [
      {
        id: 120,
        at: ago(3 * D + 10 * MIN),
        author: "scout",
        step: "title",
        text: "Three titles below. The first one did best against the last 40 videos in your niche.",
        card: null,
        cite: "Title check after Vexian's growth stages",
      },
      {
        id: 140,
        at: ago(2 * H),
        author: "editor",
        step: "record",
        text: "Three clips are in, 41 minutes in total. Sound checked to the last second of each file. I used the last full take of every sentence; two restarts are gone.",
        card: null,
      },
      {
        id: 141,
        at: ago(70 * MIN),
        author: "user",
        text: "Keep the part where I laugh about the fan noise.",
        card: null,
      },
      {
        id: 142,
        at: ago(40 * MIN),
        author: "showrunner",
        step: "edit",
        text: "Kept, it is at 1:12. Speaker cut v1 is done: 9:12 down to 4:05. The Editor is now building the graphics. Nine of them are 3D scenes, so I asked about the GPU below.",
        card: null,
        cite: "Pace and captions follow your style pack: keywords only, 8 cuts per minute.",
      },
      {
        id: 143,
        at: ago(6 * MIN),
        author: "critic",
        step: "edit",
        text: "Cut v1 against your best video: speaker share 58 %, loudness −14.1 LUFS, no word cut in half. One weak spot at 2:31, a long pause before the result. I would trim 0.8 s there.",
        card: null,
        preview: "review/frame-231.png",
        facts: [
          { label: "Length", value: "4:05" },
          { label: "Speaker on screen", value: "58 %" },
          { label: "Loudness", value: "−14.1 LUFS" },
          { label: "Check", value: "0 errors, 1 note" },
        ],
      },
      {
        id: 144,
        at: ago(4 * MIN),
        author: "showrunner",
        step: "edit",
        text: "Critic and Editor · fix about review/cut-check-v001.json · 2 messages",
        card: null,
        exchange: {
          topic: "critic-editor-review/cut-check.json",
          result: "Trimmed 0.8 s at 2:31. Cut v1 is now 4:04; the check is clean.",
          messages: [
            {
              id: 1,
              sender: "critic",
              recipient: "editor",
              kind: "fix",
              about: "review/cut-check-v001.json",
              text: "One note in cut v1: a long pause before the result at 2:31. Trim 0.8 s there; the rest is clean.",
              route: "live",
              status: "delivered",
            },
            {
              id: 2,
              sender: "editor",
              recipient: "critic",
              kind: "fix",
              about: "review/cut-check-v001.json",
              text: "Trimmed 0.8 s at 2:31. Cut v1 is now 4:04; the check is clean.",
              route: "live",
              status: "delivered",
            },
          ],
        },
      },
    ],
    [ep4.id]: [
      {
        id: 150,
        at: ago(23 * H),
        author: "showrunner",
        step: "script",
        text: "Title is set. The Writer starts the script tomorrow morning.",
        card: null,
      },
      {
        id: 151,
        at: ago(3 * H),
        author: "writer",
        step: "script",
        text: "Version 1 of the script is in progress. I start with the hosting bill, because that is the result.",
        card: null,
        cite: "Opening after your rule: result first, then how",
      },
    ],
    [ep2.id]: [
      {
        id: 90,
        at: ago(2 * D),
        author: "publisher",
        step: "results",
        text: "Results after 48 hours. The title held: click rate is above your average, and most viewers stayed past the first minute.",
        card: null,
        facts: [
          { label: "Views", value: "2,140" },
          { label: "Click rate", value: "6.8 %" },
          { label: "Average view", value: "3:12 of 5:40" },
        ],
      },
    ],
    _onboarding: [],
  };

  const logs: Record<number, string[]> = {
    12: [
      "Read edit/plan-v001.json: 14 2D scenes, 9 3D scenes, 4:05 long.",
      "Style pack: brand/ (accent, fonts and pace loaded).",
      "Rendered 2D scene 1 of 14: counter, 4.2 s.",
      "Rendered 2D scene 2 of 14: keyword, 1.8 s.",
      "Rendered 2D scene 3 of 14: keyword, 1.9 s.",
      "Rendered 2D scene 4 of 14: compare, 6.1 s.",
      "Rendered 2D scene 5 of 14: counter, 4.0 s.",
      "Rendering 2D scene 6 of 14: chart.",
      "API equivalent so far: $0.41 (on your subscription).",
    ],
    11: ["Asked for a yes on card 9: render the 3D scenes on a rented GPU.", "Waiting."],
    13: ["Read brand/thumbnail.json: at most three words, face on the left.", "Variant 1 of 3 done.", "Writing variant 2 of 3."],
    10: ["Measured cut v1 against your best video.", "Speaker share 58 %, loudness −14.1 LUFS.", "One note: long pause at 2:31."],
    9: ["Built the speaker cut from 41 min of takes.", "9:12 down to 4:05.", "Kept 1:12, the laugh about the fan noise."],
    8: ["Transcribed 3 clips, 41 min, model small.", "Done."],
  };

  const profile = profileJson as Profile;

  const prompter: PrompterLink = { url: "http://crewcut.local:4748/p/demo-token", qr_svg: DEMO_QR_SVG };

  const script: PrompterScript = {
    title: ep3.title,
    mode: "full",
    blocks: [
      {
        text: "I ran five local AI models on a laptop that cost nine hundred dollars. No cloud, no subscription, just the fan.",
        points: ["Five models, $900 laptop", "No cloud, only the fan"],
      },
      {
        text: "The fastest one answered at forty-one tokens per second. That is faster than I read.",
        points: ["Fastest: 41 tokens per second", "Faster than I read"],
      },
      {
        text: "The slowest one was the smartest. It took a full minute for one answer, and the answer was right.",
        points: ["Slowest was the smartest", "One minute, right answer"],
      },
      {
        text: "So which one do you keep? It depends on one question: do you wait, or do you check?",
        points: ["Which one to keep", "Wait or check"],
      },
      {
        text: "Here is how I set them up, step by step, so you can try it tonight.",
        points: ["Setup, step by step"],
      },
    ],
  };

  let playCard: Card | null = null;
  let playWaiting: Activity | null = null;
  let playRender: Activity | null = null;
  if (opts.play) {
    // The sequence starts before the Editor asks: the edit step is working, no card is open yet.
    const card = cards.find((c) => c.id === 9);
    playWaiting = activity.find((a) => a.job === 11) ?? null;
    if (card) {
      cards.splice(cards.indexOf(card), 1);
      // Fifty minutes here against twelve rented: the honest first choice is this machine (rule 12). The user picks
      // the rented GPU anyway, to have the cut today.
      const est = { ...(card.data?.estimate ?? {}), local_seconds: 3000, sentence: undefined };
      playCard = { ...card, data: { ...card.data, estimate: est } };
    }
    state.activity = activity.filter((a) => a.job !== 11);
    ep3.open_cards = 0;
    ep3.steps = steps(["done", "done", "done", "done", "done", "working", "open", "skipped", "open", "open"]);
    details[ep3.id] = { ...details[ep3.id]!, ...ep3 };
    playRender = {
      job: 14,
      episode: ep3.id,
      identity: "editor",
      ...ran("sonnet", "medium"),
      step: "edit",
      doing: "Rendering 3D scene 1 of 9 · rented GPU",
      progress: 0.03,
      status: "running",
      started: null,
      seconds: 0,
      cost_usd: 0,
      equiv_usd: null,
    };
    logs[14] = ["Rented 1 × RTX 4090, cap $1.50.", "Rendering 3D scene 1 of 9."];
  }

  return { playCard, playWaiting, playRender, state, details, messages, cards, team, logs, profile, prompter, script };
}

/** Demo preview files: paths inside an episode, mapped to images in public/demo/. */
export const DEMO_FILES: Record<string, string> = {
  "review/frame-231.png": "demo/frame-231.svg",
  "brand/preview-v001.mp4": "demo/preview.svg",
  "export/003-local-llms-v001-preview.mp4": "demo/frame-231.svg",
};
