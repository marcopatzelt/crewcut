// Demo data, shaped exactly like docs/api.md. Test data only: made-up chats, jobs and money; the pictures are the
// web-sized, text-free (or English) stills listed in media.json. Every title, card, chat line and crew message is
// English. Times are relative to the moment the page loads, so "12 min ago" stays true in every screenshot.
import type {
  Activity,
  Card,
  Episode,
  EpisodeDetail,
  EpisodeMedia,
  EpisodeMotion,
  Identity,
  Message,
  MotionRatchet,
  Profile,
  PrompterLink,
  PrompterScript,
  ShelfRow,
  State,
  Step,
  StepStatus,
} from "../api/types";
import { makeMotionDemo } from "./motion";
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

/** The steps of a Short: only those its mode has, numbered from 1. */
export function shortSteps(ids: string[], statuses: StepStatus[]): Step[] {
  return ids.map((id, i) => ({
    id,
    n: i + 1,
    label: STEP_LABELS.find(([sid]) => sid === id)?.[1] ?? id,
    status: statuses[i] ?? "open",
  }));
}

// ---------- the pictures (media.json, written by tools/demo/build_media.py) ----------

interface ManifestThumb {
  id: string;
  label: string;
  url: string;
  url_large?: string;
}
interface ManifestEpisode {
  key: string;
  title_en: string;
  kind?: string;
  cover: string;
  cover_large?: string;
  thumbs?: ManifestThumb[];
  frames?: { t: number; url: string }[];
  scenes?: { id: string; name: string; url: string; url_large?: string }[];
}
interface Manifest {
  channel?: { name: string; avatar?: string };
  episodes: ManifestEpisode[];
  shorts: { key: string; title_en: string; cover: string; from: string }[];
}

// Read without a hard import, so the app still builds and tests run when the manifest is missing.
const found = import.meta.glob<Manifest>("./media.json", { eager: true, import: "default" });
const MANIFEST: Manifest = found["./media.json"] ?? { episodes: [], shorts: [] };

function ep(key: string): ManifestEpisode | undefined {
  return MANIFEST.episodes.find((e) => e.key === key);
}

// ---------- the data ----------

export interface DemoData {
  /** The card and the waiting row the scripted sequence adds, then the render it starts after the yes. */
  playCard: Card | null;
  playWaiting: Activity | null;
  playRender: Activity | null;
  /** The media of the main episode once the rented GPU runs (the scripted sequence switches to it). */
  playMedia: EpisodeMedia | null;
  state: State;
  details: Record<string, EpisodeDetail>;
  messages: Record<string, Message[]>;
  cards: Card[];
  team: Identity[];
  logs: Record<number, string[]>;
  profile: Profile;
  prompter: PrompterLink;
  script: PrompterScript;
  media: Record<string, EpisodeMedia>;
  /** GET /api/episodes/{id}/motion, the shelf and the bar (src/demo/motion.ts) */
  motion: Record<string, EpisodeMotion>;
  shelf: ShelfRow[];
  ratchet: MotionRatchet;
}

/** What a job's engine reported about itself (docs/api.md). Made-up demo values. */
function ran(model: string, effort: string | null) {
  return { engine: "claude", model, effort, engine_version: "2.1.325" };
}

/** A calm, made-up waveform: a speaker's envelope with pauses, the same in every screenshot. */
function peaks(n: number, seed = 7): number[] {
  let s = seed;
  const r = () => (s = (s * 16807) % 2147483647) / 2147483647;
  return Array.from({ length: n }, (_, i) => {
    const env = 0.35 + 0.65 * Math.abs(Math.sin(i / 9)) * (0.6 + 0.4 * r());
    const pause = i > 64 && i < 70 ? 0.15 : 1; // the pause at 1:12 the Critic notes
    return Math.round(Math.max(0.06, env * r() * pause) * 100) / 100;
  });
}

const TEAM: Identity[] = [
  {
    id: "showrunner",
    name: "Showrunner",
    role: "Runs the episode through the ten steps and talks with you.",
    mark: "SR",
    avatar: "headset",
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
    avatar: "magnifier",
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
    avatar: "pencil",
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
    avatar: "scissors",
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
    avatar: "clipboard",
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
    avatar: "brush",
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
    avatar: "plane",
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
    avatar: "swatches",
    skills: ["onboarding", "style-pack"],
    may_spend: false,
    may_publish: false,
    soul: "I take colours, type and pace from what you already made, and I name the source of every value.",
    sources: [],
  },
];

/** Paths inside an episode folder that demo messages and cards show, mapped to pictures in public/. */
export const DEMO_FILES: Record<string, string> = {};

/**
 * The demo data. `play` is the start of the scripted sequence (?demo=1&play=1): the rented GPU is not there yet; the
 * timeline in backend.ts adds the card, the yes and the render, using `playCard`, `playWaiting`, `playRender` and
 * `playMedia`.
 */
export function makeDemo(now = Date.now(), opts: { play?: boolean } = {}): DemoData {
  const ago = (seconds: number) => new Date(now - seconds * 1000).toISOString();
  const MIN = 60;
  const H = 3600;
  const D = 86400;
  const pic = (e: ManifestEpisode | undefined, large = false) => (e ? (large ? e.cover_large ?? e.cover : e.cover) : null);

  const m012 = ep("012");
  const m015 = ep("015");
  // Large variants for the episode view; the small ones where a picture is drawn small (cards, the rail, a phone).
  // Only A and B: variant C spells its title differently ("Design-Skills"), so the demo leaves it out.
  const thumbs012 = (m012?.thumbs ?? [])
    .filter((t) => t.id === "A" || t.id === "B")
    .map((t) => ({ ...t, small: t.url, url: t.url_large ?? t.url }));
  const scenes = m012?.scenes ?? m015?.scenes ?? [];
  const sceneUrl = (i: number) => (i === 0 ? scenes[0]?.url_large ?? scenes[0]?.url : scenes[i]?.url) ?? null;

  // Paths the demo chat names, as the real server would (inside the episode), mapped to the pictures.
  for (const t of thumbs012) DEMO_FILES[`graphics/thumbnail/v1/${t.id}.jpg`] = t.url;
  if (scenes[4]) DEMO_FILES["render/inserts/s5/0412.jpg"] = scenes[4].url;
  if (m015) DEMO_FILES["render/probe/opening.jpg"] = m015.cover_large ?? m015.cover;
  // The style pack's 10-second preview: a still from the newest cut stands in for the video in the demo.
  const still = m012?.frames?.[4]?.url;
  if (still) DEMO_FILES["brand/preview-v001.mp4"] = still;

  // ----- episodes -----
  const e012: Episode = {
    id: "012-website-100-times",
    title: m012?.title_en ?? "Claude improves a website 100 times",
    step: "thumbnail",
    steps: steps(["done", "done", "done", "done", "done", "done", "waiting", "open", "open", "open"]),
    updated: ago(6 * MIN),
    open_cards: 1,
    cover: pic(m012, true),
    seconds: 274,
    needs: {
      card: 31,
      kind: "thumbnail",
      title: "Pick a thumbnail",
      images: thumbs012.slice(0, 2).map((t) => t.small),
    },
  };
  const e015: Episode = {
    id: "015-thinking-levels-commercial",
    title: m015?.title_en ?? "Thinking levels commercial",
    step: "edit",
    steps: steps(["done", "done", "done", "done", "skipped", "waiting", "open", "skipped", "open", "open"]),
    updated: ago(12 * MIN),
    open_cards: 2,
    cover: pic(m015, true),
    seconds: 25,
    needs: {
      card: 51,
      kind: "preview",
      title: "Pick the opening shot",
      images: [0, 2, 4].map((i) => scenes[i]?.url).filter((u): u is string => Boolean(u)),
    },
  };
  const long = (key: string, id: string, fallback: string, statuses: StepStatus[], step: string, updated: number, seconds: number | null): Episode => {
    const m = ep(key);
    return { id, title: m?.title_en ?? fallback, step, steps: steps(statuses), updated: ago(updated), open_cards: 0, cover: pic(m), seconds };
  };
  const PUBLISHED: StepStatus[] = ["done", "done", "done", "done", "done", "done", "done", "done", "done", "done"];
  const e014 = long(
    "014",
    "014-local-ai-privately",
    "Use local AI privately: what really stays with you",
    ["done", "done", "done", "done", "done", "working", "open", "open", "open", "open"],
    "edit",
    25 * MIN,
    null,
  );
  const e013 = long("013", "013-one-prompt-full-game", "One prompt, a full game", PUBLISHED, "results", 2 * D, 213);
  const e011 = long("011", "011-local-ai-ten-cents", "Local AI is enough for $0.10", PUBLISHED, "results", 7 * D, 262);
  const e010 = long("010", "010-any-software-19-minutes", "Claude operates any software in 19 minutes", PUBLISHED, "results", 9 * D, 217);
  const e008 = long("008", "008-graphify-measured", "Graphify, measured: −20%, not −99%", PUBLISHED, "results", 21 * D, 245);
  const longs = [e013, e011, e010, e008];

  const SHORT_STEPS = ["idea", "title", "edit", "thumbnail", "upload", "results"];
  const shortId = (key: string, title: string) =>
    `${key.toLowerCase()}-${title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 28)
      .replace(/-$/, "")}`;
  const sourceOf = (key: string) => [e012, e015, e014, ...longs].find((x) => x.id.startsWith(`${key}-`))?.id ?? null;
  const shorts: Episode[] = MANIFEST.shorts.map((s, i) => ({
    id: shortId(s.key, s.title_en),
    title: s.title_en,
    step: i === 0 ? "edit" : "results",
    steps: shortSteps(SHORT_STEPS, i === 0 ? ["done", "done", "working", "open", "open", "open"] : ["done", "done", "done", "done", "done", "done"]),
    updated: ago(i === 0 ? 50 * MIN : (i + 1) * 20 * H),
    open_cards: 0,
    cover: s.cover,
    kind: "short" as const,
    mode: "clip" as const,
    source_episode: sourceOf(s.from),
    seconds: 38 + ((i * 7) % 20),
  }));

  const episodes = [e012, e015, e014, ...longs, ...shorts];

  // ----- jobs -----
  const renderJob: Activity = {
    job: 41,
    ...ran("sonnet", "medium"),
    episode: e012.id,
    identity: "editor",
    step: "edit",
    doing: "3D scene 5 of 5 on a rented GPU",
    progress: 0.62,
    status: "running",
    started: ago(255),
    seconds: 255,
    cost_usd: 0.31,
    equiv_usd: null,
    preview: sceneUrl(4),
  };
  const activity: Activity[] = [
    renderJob,
    {
      job: 42,
      ...ran("sonnet", "low"),
      episode: e012.id,
      identity: "designer",
      step: "thumbnail",
      doing: "Checks A and B at phone size",
      progress: 0.4,
      status: "running",
      started: ago(68),
      seconds: 68,
      cost_usd: 0,
      equiv_usd: 0.06,
      preview: thumbs012[0]?.small ?? null,
    },
    {
      job: 43,
      ...ran("sonnet", "medium"),
      episode: e014.id,
      identity: "editor",
      step: "edit",
      doing: "Speaker cut v1, 41 min of takes",
      progress: 0.35,
      status: "running",
      started: ago(520),
      seconds: 520,
      cost_usd: 0,
      equiv_usd: 0.22,
      preview: null,
    },
    {
      job: 40,
      ...ran("opus", "high"),
      episode: e012.id,
      identity: "critic",
      step: "thumbnail",
      doing: "Waits for your thumbnail pick",
      progress: null,
      status: "waiting",
      started: ago(40),
      seconds: 40,
      cost_usd: 0,
      equiv_usd: 0.02,
    },
    {
      job: 39,
      ...ran("sonnet", "medium"),
      episode: e012.id,
      identity: "critic",
      step: "edit",
      doing: "Cut check v5",
      progress: 1,
      status: "done",
      started: ago(12 * MIN + 210),
      seconds: 210,
      cost_usd: 0,
      equiv_usd: 0.19,
      ended: ago(12 * MIN),
    },
    {
      job: 38,
      ...ran("haiku", null),
      episode: e012.id,
      identity: "editor",
      step: "edit",
      doing: "Rendered 3D scenes 1 to 4",
      progress: 1,
      status: "done",
      started: ago(50 * MIN),
      seconds: 1880,
      cost_usd: 0,
      equiv_usd: null,
      ended: ago(19 * MIN),
    },
  ];

  const state: State = {
    app: { version: "0.1.0", engine: "claude", engine_ok: true, gpu_local: false, onboarded: true },
    team: TEAM.map(({ soul: _soul, sources: _sources, ...rest }) => rest),
    episodes,
    activity,
    money: {
      today_usd: 0.31,
      episode_usd: { [e012.id]: 0.92, [e015.id]: 0.61, [e014.id]: 0 },
      month_usd: 4.1,
      cap_month_usd: 20,
    },
  };

  const details: Record<string, EpisodeDetail> = {};
  for (const e of episodes) {
    details[e.id] = {
      ...e,
      project: {
        id: e.id,
        title: e.title,
        created: ago(e.kind === "short" ? 2 * D : 6 * D),
        format: e.kind === "short" ? "portrait" : "landscape",
        fps: 25,
      },
      files: [],
    };
  }

  // ----- cards -----
  const spend: Card = {
    id: 22,
    episode: e012.id,
    step: "edit",
    kind: "spend",
    identity: "editor",
    title: "Render 3D scene 5 on a rented GPU?",
    body: "Scene 5 is the long one: 840 frames. Both ways give the same picture; the rented one is faster, this machine is free.",
    options: null,
    file: "edit/plan-v005.json",
    preview: null, // scene 5 is among the media of the episode
    sha256: "a81e55f0d913",
    status: "accepted",
    created: ago(52 * MIN),
    decided_at: ago(50 * MIN),
    choice: null,
    data: {
      for: "render-3d",
      frames: 840,
      amount_usd: 0.6,
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
      },
      referral: {
        url: "https://cloud.vast.ai/?ref_id=demo",
        note: "Referral link: the author of Crewcut earns 3% of your Vast spend as credit. It costs you nothing extra.",
      },
    },
  };
  const thumbCard: Card = {
    id: 31,
    episode: e012.id,
    step: "thumbnail",
    kind: "thumbnail",
    identity: "designer",
    title: "Pick a thumbnail",
    body: "Recommendation: B. The face stays readable at phone size.",
    options: thumbs012.length ? thumbs012.map((t) => `${t.id} · ${t.label}`) : ["A", "B"],
    file: "graphics/thumbnail/v1/B.jpg",
    preview: null, // the variants are large in the episode's Thumbnail panel
    sha256: "5d0c9a77e2b1",
    status: "open",
    created: ago(6 * MIN),
    choice: 1,
  };
  const openingCard: Card = {
    id: 51,
    episode: e015.id,
    step: "edit",
    kind: "preview",
    identity: "editor",
    title: "Pick the opening shot",
    body: "Three openings from the 3D round. The Rhine front reads best in the first second.",
    options: ["Rhine front", "Bridge view", "Evening street"],
    file: "edit/plan-v003.json",
    preview: m015 ? "render/probe/opening.jpg" : null,
    sha256: "0b7e4c19a2f6",
    status: "open",
    created: ago(40 * MIN),
  };
  const titleCard: Card = {
    id: 12,
    episode: e012.id,
    step: "title",
    kind: "title",
    identity: "scout",
    title: "Pick a title",
    body: "Recommendation: option 1. It names the method and the number.",
    options: ["Claude improves a website 100 times", "100 rounds of design feedback", "What 100 rounds do to a website"],
    file: "brief/TITLE-v002.md",
    preview: null,
    sha256: "9c1d4e0b7a2f",
    status: "accepted",
    created: ago(5 * D),
    choice: 0,
    decided_at: ago(5 * D - 20 * MIN),
  };
  // Motion graphics: the commercial's plan has its yes and its style frame is open; 013 shows the finished loop
  // (src/demo/motion.ts).
  const motionDemo = makeMotionDemo({ e015: e015.id, e013: e013.id, e011: e011.id }, ago);
  Object.assign(DEMO_FILES, motionDemo.files);
  const cards: Card[] = [titleCard, spend, thumbCard, openingCard, ...motionDemo.cards];

  // ----- chats -----
  const messages: Record<string, Message[]> = {
    [e012.id]: [
      {
        id: 300,
        at: ago(5 * D + 10 * MIN),
        author: "scout",
        step: "title",
        text: "Three titles below. The first one did best against the last 40 videos in your niche.",
        card: null,
        cite: "Title check after Vexian's growth stages",
      },
      {
        id: 301,
        at: ago(1 * D),
        author: "writer",
        step: "script",
        text: "Script v3 is on your phone. Scan the code on the teleprompter page when you are ready to record.",
        card: null,
      },
      {
        id: 302,
        at: ago(2 * H),
        author: "editor",
        step: "edit",
        text: "Cut v5 is ready: 4:34, 48 shots. The intro gets five 3D scenes of the Rhine front.",
        card: null,
        cite: "Pace and captions follow your style pack: keywords only, 8 cuts per minute.",
      },
      {
        id: 303,
        at: ago(12 * MIN),
        author: "critic",
        step: "edit",
        text: "Cut v5 holds up against your best video. Two notes: a long pause at 1:12, and the site at 2:36 needs a second longer.",
        card: null,
        facts: [
          { label: "Length", value: "4:34" },
          { label: "Speaker on screen", value: "58 %" },
          { label: "Loudness", value: "−14.1 LUFS" },
        ],
      },
      { id: 304, at: ago(10 * MIN), author: "user", text: "Keep the pause, it is where I laugh. Fix 2:36.", card: null },
      {
        id: 305,
        at: ago(9 * MIN),
        author: "showrunner",
        step: "edit",
        text: "Critic and Editor · fix about review/cut-check-v005.json · 2 messages",
        card: null,
        exchange: {
          topic: "critic-editor-review/cut-check.json",
          result: "The site at 2:36 holds one second longer. The pause at 1:12 stays.",
          messages: [
            {
              id: 1,
              sender: "critic",
              recipient: "editor",
              kind: "fix",
              about: "review/cut-check-v005.json",
              text: "The site at 2:36 needs one more second. Keep the pause at 1:12, the creator wants it.",
              route: "live",
              status: "delivered",
            },
            {
              id: 2,
              sender: "editor",
              recipient: "critic",
              kind: "fix",
              about: "review/cut-check-v005.json",
              text: "Done: 2:36 holds one second longer. The check is clean.",
              route: "live",
              status: "delivered",
            },
          ],
        },
      },
      {
        id: 306,
        at: ago(6 * MIN),
        author: "designer",
        step: "thumbnail",
        text: "Two thumbnails from your style pack. I would take B: the face stays readable at phone size.",
        card: 31,
      },
      {
        id: 307,
        at: ago(1 * MIN),
        author: "editor",
        step: "edit",
        text: "Four of five 3D scenes are back from the rented GPU. The last one needs about 3 minutes, then I delete the machine.",
        card: null,
      },
    ],
    [e015.id]: [
      {
        id: 400,
        at: ago(2 * H),
        author: "editor",
        step: "edit",
        text: "Round 3 of the 3D frames is in: 4K, the Rhine front at golden hour. Twelve spots, three of them work as the opening.",
        card: null,
      },
      { id: 401, at: ago(40 * MIN), author: "editor", step: "edit", text: "Pick the opening shot", card: 51 },
    ],
    [e014.id]: [
      {
        id: 410,
        at: ago(30 * MIN),
        author: "editor",
        step: "record",
        text: "Three clips are in, 41 minutes in total. Sound checked to the last second of each file.",
        card: null,
      },
      {
        id: 411,
        at: ago(25 * MIN),
        author: "editor",
        step: "edit",
        text: "Speaker cut v1 is running. I keep the last full take of every sentence.",
        card: null,
      },
    ],
    _onboarding: [],
  };
  for (const [id, list] of Object.entries(motionDemo.messages)) messages[id] = [...(messages[id] ?? []), ...list];
  for (const e of [...longs, ...shorts]) {
    messages[e.id] = [
      ...(messages[e.id] ?? []),
      {
        id: 500 + episodes.indexOf(e),
        at: e.updated,
        author: e.kind === "short" && e.step !== "results" ? "editor" : "publisher",
        step: e.step,
        text:
          e.kind === "short" && e.step !== "results"
            ? "Cutting the clip from the 4K original, 9:16 around your face."
            : "Published. The results after 48 hours are below the video on YouTube; I read them for the next episode.",
        card: null,
      },
    ];
  }

  // ----- the media of the episode view -----
  const mediaThumbs = thumbs012.map((t) => ({
    id: t.id,
    label: t.label,
    note: t.id === "A" ? "Title left, four sites" : "Title over the face, one site",
    url: t.url,
    recommended: t.id === "B",
    picked: false,
    card: 31,
  }));
  const frames = m012?.frames ?? [];
  const sceneItems = scenes.map((s, i) => ({
    id: s.id,
    name: s.name,
    status: (i < 4 ? "done" : "rendering") as "done" | "rendering",
    progress: i < 4 ? 1 : 0.62,
    seconds: [4, 3, 3, 4, 5][i] ?? 3,
    url: sceneUrl(i),
  }));
  const media: Record<string, EpisodeMedia> = {
    [e012.id]: {
      thumbnails: mediaThumbs,
      cut: frames.length
        ? {
            version: "v5",
            seconds: 274,
            shots: 48,
            frames,
            peaks: peaks(240),
            markers: [
              { t: 72, level: "note", text: "A long pause before the result. You said keep it." },
              { t: 141, level: "warning", text: "The site needs one second longer." },
            ],
            facts: ["Keywords only", "8 cuts a minute", "-14 LUFS"],
          }
        : null,
      scenes: sceneItems.length
        ? { title: "Intro, the Rhine front at golden hour, 4K", done: 4, total: sceneItems.length, items: sceneItems }
        : null,
      gpu: {
        name: "RTX 4090",
        started: ago(17 * MIN),
        minutes_left: 3,
        so_far_usd: 0.31,
        cap_usd: 1.5,
        progress: 0.78,
        delete_note: "Deleted when done, frames come home",
        session: 7,
        price_per_hour: 0.45,
        cap_per_gpu_hour: 0.6,
      },
    },
    [e015.id]: {
      thumbnails: [],
      cut: scenes.length
        ? {
            version: "v1",
            seconds: 25,
            shots: scenes.length,
            frames: Array.from({ length: 10 }, (_, i) => ({ t: 25 * (0.05 + 0.1 * i), url: scenes[Math.min(scenes.length - 1, Math.floor(i / 2))]?.url ?? "" })),
            peaks: peaks(240, 11),
            markers: [],
            facts: ["Keywords only", "-14 LUFS"],
          }
        : null,
      scenes: scenes.length
        ? {
            title: "Round 3, 4K",
            done: scenes.length,
            total: scenes.length,
            items: scenes.map((s, i) => ({ id: s.id, name: s.name, status: "done" as const, progress: 1, seconds: 3, url: sceneUrl(i) })),
          }
        : null,
      gpu: null,
    },
  };

  const logs: Record<number, string[]> = {
    41: [
      "Rented 1 × RTX 4090, cap $1.50.",
      "Scenes 1 to 4 are home: 3,360 frames.",
      "Rendering scene 5 of 5: Evening street, 840 frames.",
      "Frame 521 of 840.",
    ],
    42: ["Read brand/thumbnail.json: at most three words, face on the right.", "Variants A and B done.", "Checking both at phone size."],
    43: ["Read 3 clips, 41 min.", "Kept the last full take of every sentence.", "Building speaker cut v1."],
    40: ["Waits for card 31: the thumbnail pick."],
    39: ["Measured cut v5 against your best video.", "Speaker share 58 %, loudness −14.1 LUFS.", "Two notes: 1:12 and 2:36."],
    38: ["Rendered scenes 1 to 4 on the rented GPU.", "Frames copied home and checked."],
  };

  const profile: Profile = {
    ...(profileJson as Profile),
    rows: [
      ...(MANIFEST.channel ? [{ label: "Channel", value: MANIFEST.channel.name, kind: "text", source: "from your channel" }] : []),
      ...(MANIFEST.channel?.avatar
        ? [{ label: "Channel picture", value: MANIFEST.channel.avatar, kind: "image", source: "from your channel" }]
        : []),
      ...(profileJson as Profile).rows,
    ],
  };

  const prompter: PrompterLink = { url: "http://crewcut.local:4748/p/demo-token", qr_svg: DEMO_QR_SVG };

  const script: PrompterScript = {
    title: e012.title,
    mode: "full",
    blocks: [
      {
        text: "I asked Claude to improve one website a hundred times. Same prompt, every round: make it better.",
        points: ["One website, 100 rounds", "Same prompt every time"],
      },
      {
        text: "Round ten looked great. Round fifty looked like every other website on the internet.",
        points: ["Round 10: great", "Round 50: like every other site"],
      },
      {
        text: "Then I gave it a design skill, and the next fifty rounds went somewhere else.",
        points: ["Then: a design skill", "The last 50 rounds changed"],
      },
      {
        text: "Here are the four sites side by side, and the one rule that made the difference.",
        points: ["Four sites side by side", "The one rule"],
      },
    ],
  };

  let playCard: Card | null = null;
  let playWaiting: Activity | null = null;
  let playRender: Activity | null = null;
  let playMedia: EpisodeMedia | null = null;
  if (opts.play) {
    // The sequence starts before the Editor asks: scenes 1 to 4 rendered here, scene 5 waits, no machine rented yet.
    // Fifty minutes here against twelve rented: the honest first choice is this machine (rule 12). The user picks the
    // rented GPU anyway, to have the cut today.
    cards.splice(cards.indexOf(spend), 1);
    playCard = {
      ...spend,
      status: "open",
      decided_at: null,
      data: { ...spend.data, estimate: { ...(spend.data?.estimate ?? {}), local_seconds: 3000 } },
    };
    playWaiting = {
      job: 44,
      ...ran("opus", "high"),
      episode: e012.id,
      identity: "editor",
      step: "edit",
      doing: "Waiting for your yes on the GPU",
      progress: null,
      status: "waiting",
      started: null,
      seconds: 0,
      cost_usd: 0,
      equiv_usd: 0.02,
    };
    playRender = { ...renderJob, doing: "3D scene 5 of 5 on a rented GPU", progress: 0.03, started: null, seconds: 0, cost_usd: 0 };
    state.activity = activity.filter((a) => a.job !== renderJob.job);
    state.money = { ...state.money, today_usd: 0, month_usd: 3.79, episode_usd: { ...state.money.episode_usd, [e012.id]: 0.61 } };
    messages[e012.id] = (messages[e012.id] ?? []).filter((m) => m.id !== 307);
    const m = media[e012.id];
    if (m) {
      playMedia = {
        ...m,
        scenes: m.scenes
          ? { ...m.scenes, items: m.scenes.items.map((s, i) => (i === 4 ? { ...s, status: "rendering" as const, progress: 0.03 } : s)) }
          : null,
        gpu: m.gpu ? { ...m.gpu, started: new Date(now).toISOString(), minutes_left: 12, so_far_usd: 0, progress: 0.03 } : null,
      };
      media[e012.id] = {
        ...m,
        scenes: m.scenes
          ? { ...m.scenes, items: m.scenes.items.map((s, i) => (i === 4 ? { ...s, status: "queued" as const, progress: null, url: null } : s)) }
          : null,
        gpu: null,
      };
    }
    logs[44] = ["Asked for a yes on card 22: render scene 5 on a rented GPU."];
  }

  return {
    playCard,
    playWaiting,
    playRender,
    playMedia,
    state,
    details,
    messages,
    cards,
    team: TEAM,
    logs,
    profile,
    prompter,
    script,
    media,
    motion: motionDemo.motion,
    shelf: motionDemo.shelf,
    ratchet: motionDemo.ratchet,
  };
}
