// Shapes from docs/api.md. Fields marked "optional extra" are read when present and never required.

export type StepStatus = "open" | "working" | "waiting" | "done" | "skipped" | "unknown";

export interface Step {
  id: string;
  n: number;
  label: string;
  status: StepStatus;
  note?: string | null;
  evidence?: unknown;
}

export interface Identity {
  id: string;
  name: string;
  role: string;
  mark: string;
  /** The prop Slate holds for this crew member (team/<id>.md `avatar`), e.g. "scissors". */
  avatar?: string;
  skills: string[];
  may_spend: boolean;
  may_publish: boolean;
  /** GET /api/team only: the short "how I work" text. */
  soul?: string;
  /** GET /api/team only. A source is a link or a short object with a name and a link. */
  sources?: Array<Source | string>;
}

export interface Source {
  name: string;
  url?: string;
  /** What the skills take from this source, in our own words. */
  what?: string;
}

export interface Episode {
  imported_at?: string | null;
  history_conflicts?: Array<{
    source?: string;
    stage?: string;
    visibility?: string;
    note?: string;
    other?: { source?: string; distribution?: string };
  }>;
  history?: {
    distribution: "published" | "scheduled" | "uploaded" | "unknown";
    url?: string | null;
    published_at?: string | null;
    scheduled_at?: string | null;
    checked_at?: string | null;
    source?: string | null;
  };
  id: string;
  historical_status?: "published" | "scheduled" | "uploaded" | "parked" | "paused" | "archived";
  lifecycle?: "active" | "planned" | "parked" | "archived";
  title: string;
  step: string;
  steps: Step[];
  updated: string;
  open_cards: number;
  /** "short" for a Short (portrait, fewer steps); absent or "episode" for a long video */
  kind?: "episode" | "short";
  mode?: "clip" | "original";
  /** a clip: the episode it comes from */
  source_episode?: string | null;
  /** URL of the newest thumbnail image, the episode's cover in the grid */
  cover?: string | null;
  /** the first open card, with small preview images (e.g. the thumbnail variants), for the "Needs you" cards */
  needs?: { card: number; kind: string; title: string; images: string[] } | null;
  /** length of the newest cut or final, in seconds */
  seconds?: number | null;
  /** the interview before the first script draft; "waiting" means the episode needs the creator's answers */
  interview?: EpisodeInterview | null;
  /** what the user asked for at New episode: long, short or auto (the Scout decides) */
  length?: Length | null;
  /** the show format the episode is built from, with the Scout's reason once brief/FORMAT-v001.md exists */
  show_format?: EpisodeFormat | null;
}

export type Length = "long" | "short" | "auto";

export interface EpisodeFormat {
  id: string;
  name: string;
  length?: "long" | "short" | null;
  topic_type?: string | null;
  reason?: string | null;
  runner_up?: string | null;
  file?: string | null;
}

/** One show format of the library (GET /api/formats, docs/formats.md). */
export interface ShowFormat {
  id: string;
  name: string;
  length: "long" | "short";
  when: string;
  topic_types: string[];
  kinds?: Array<{ id: string; name: string; when: string }>;
  cadence?: string | null;
  strong?: string | null;
  source: "neutral" | "studio";
}

export interface FormatLibrary {
  formats: ShowFormat[];
  problems: string[];
  enabled: boolean;
}

/** An idea card from the scout or saved links (GET /api/ideas). */
export interface Idea {
  id: string;
  source: string;
  url?: string | null;
  title: string;
  summary?: string | null;
  signals?: Record<string, unknown>;
  topic_type?: string | null;
  suggested_format?: string | null;
  reason?: string | null;
  /** "rule": the loader's keyword guess; "exporter": named by the source */
  suggestion?: "rule" | "exporter" | null;
  status: "open" | "started" | "dismissed";
  episode?: string | null;
  created?: string | null;
}

export interface FormatScore {
  format: string;
  name: string;
  length?: "long" | "short" | null;
  episodes: number;
  measured: number;
  median_views: number | null;
  median_avg_view_pct: number | null;
  subs_per_1000: number | null;
  retention_drop_per_min: number | null;
  ctr: number | null;
  verdict: "more" | "watch" | "thin";
  verdict_text: string;
}

export interface Scoreboard {
  channel: { median_views: number | null; median_avg_view_pct: number | null; subs_per_1000: number | null; episodes: number };
  formats: FormatScore[];
}

export interface EpisodeInterview {
  status: "asking" | "waiting" | "done" | "skipped";
  /** "Interview: waiting for your answers" */
  label: string;
  answers: number;
  questions: number;
  file?: string | null;
}

/** GET /api/episodes/{id}/media: what the episode view shows first (thumbnails, the cut, 3D scenes, the GPU). */
export interface EpisodeMedia {
  cover_preview?: string | null;
  imported?: boolean;
  thumbnails: MediaThumb[];
  cut: MediaCut | null;
  scenes: MediaScenes | null;
  gpu: MediaGpu | null;
}

export interface MediaThumb {
  id: string; // "A", "B", "C"
  label: string; // "Face right"
  note?: string | null; // "Title left, four sites"
  url: string;
  recommended?: boolean;
  picked?: boolean;
  /** the open thumbnail card these variants belong to */
  card?: number | null;
}

export interface MediaCut {
  version: string; // "v2"
  seconds: number;
  shots: number;
  frames: { t: number; url: string }[];
  /** 0..1, evenly spaced over the cut */
  peaks: number[];
  markers: { t: number; level: "error" | "warning" | "note"; text: string }[];
  /** style facts shown as chips: "Keywords only", "8 cuts a minute", "-14 LUFS" */
  facts?: string[];
  pending?: boolean;
}

export interface MediaScenes {
  title: string; // "Intro, Oberkassel at golden hour, 4K"
  done: number;
  total: number;
  items: {
    id: string;
    name: string;
    status: "done" | "rendering" | "queued";
    progress: number | null;
    seconds: number | null;
    url: string | null;
  }[];
}

export interface MediaGpu {
  name: string; // "RTX 4090"
  started: string;
  minutes_left: number | null;
  so_far_usd: number;
  cap_usd: number | null;
  progress: number | null;
  delete_note: string;
  /** dollars per hour of all machines of the rental, and the hard cap per GPU and hour (config/compute.toml) */
  price_per_hour?: number | null;
  cap_per_gpu_hour?: number | null;
  session: number;
}

export interface FileEntry {
  path: string;
  size: number;
  kind: string;
}

export interface EpisodeDetail extends Episode {
  project: {
    id?: string;
    title?: string;
    created?: string;
    format?: string;
    fps?: number;
    next_action?: string;
    [key: string]: unknown;
  };
  files: FileEntry[];
}

export interface ImportedFiles {
  folder: string;
  total: number;
  entries: { path: string; name: string; directory: boolean; size?: number }[];
}

export type JobStatus = "queued" | "running" | "waiting" | "done" | "failed" | "cancelled";

export interface Activity {
  job: number;
  episode: string | null;
  identity: string;
  step: string;
  doing: string;
  progress: number | null;
  status: JobStatus;
  started: string | null;
  seconds: number;
  cost_usd: number;
  equiv_usd: number | null;
  /** Optional extra: when the job ended. */
  ended?: string | null;
  /** Optional: the engine that runs the job and what it reported about itself. */
  engine?: string | null;
  model?: string | null;
  effort?: string | null;
  engine_version?: string | null;
  /** Optional: the newest picture this job made (a render frame, a thumbnail draft), shown live in "Working now". */
  preview?: string | null;
}

export interface Money {
  today_usd: number;
  episode_usd: Record<string, number>;
  month_usd: number;
  cap_month_usd: number;
}

export interface AppInfo {
  version: string;
  engine: string;
  engine_ok: boolean;
  gpu_local: boolean;
  onboarded: boolean;
}

/** GET /api/engine/login: who is connected, and a Codex device sign-in in progress. */
export interface EngineLogin {
  claude: { installed: boolean; connected: boolean; source: "stored" | "environment" | null; signing_in: boolean };
  codex: {
    installed: boolean;
    connected: boolean;
    status?: "starting" | "installing" | "waiting" | "connected" | "failed";
    url?: string;
    code?: string | null;
    text?: string;
  };
  chosen: string;
}

/** What Claude Code says about the connected account (each field optional). */
export interface ClaudeAccount {
  email?: string;
  orgName?: string;
  subscriptionType?: string;
  authMethod?: string;
}

export interface State {
  app: AppInfo;
  team: Identity[];
  episodes: Episode[];
  activity: Activity[];
  money: Money;
}

export type CardKind =
  | "topic"
  | "title"
  | "proof"
  | "script"
  | "preview"
  | "final"
  | "thumbnail"
  | "publish"
  | "spend"
  | "rule"
  | "profile"
  | "mix"
  | "other"
  | "motion-plan"
  | "style-frame"
  | "template"
  | "baseline";

export type CardStatus = "open" | "accepted" | "declined" | "expired";

export interface Referral {
  url: string;
  note: string;
}

/** The compute estimate inside a spend card (GET /api/compute/estimate shape). */
export interface Estimate {
  local_seconds?: number;
  local_measured?: boolean;
  local_source?: string;
  rented_seconds?: number;
  rented_usd?: number;
  rented_usd_worst?: number;
  gpus?: number;
  /** Optional extra: the GPU model, e.g. "RTX 4090". */
  gpu_name?: string;
  sentence?: string;
  referral?: Referral | null;
  /** honest extra cost: boot, setup and the wait before an idle machine is deleted */
  idle_note?: string;
  idle_risk_usd?: number;
  price_cap_per_gpu_hour?: number;
}

/** What the UI reads from card.data. Every field is optional. */
export interface CardData extends Estimate {
  // spend: the estimate either nested (server) or flat
  estimate?: Estimate;
  amount_usd?: number;
  budget_usd?: number;
  cap_usd?: number | null;
  // rule
  rule?: string;
  source?: string;
  // profile
  profile?: Profile;
  // publish
  schedule?: string | null;
  // script and title cards: the Humanizer pass
  humanizer?: HumanizerNote;
  // any card
  facts?: Fact[];
  [key: string]: unknown;
}

export interface HumanizerNote {
  version?: string | null;
  repo?: string | null;
  mode?: "embedded" | "plain";
  voice?: string[];
  why?: string;
  count?: number;
  changes?: { before: string; after: string }[];
  /** set when the pass did not run, with the reason */
  skipped?: string;
}

export interface Fact {
  label: string;
  value: string;
}

export interface Card {
  id: number;
  episode: string | null;
  step: string;
  kind: CardKind;
  identity: string | null;
  title: string;
  body: string | null;
  options: string[] | null;
  file: string | null;
  preview: string | null;
  sha256: string | null;
  status: CardStatus;
  created: string;
  /** spend cards */
  amount_usd?: number | null;
  data?: CardData | null;
  /** decided cards */
  choice?: number | null;
  decided_at?: string | null;
}

export interface Message {
  id: number;
  at: string;
  author: string; // "user" or an identity id
  text: string;
  /** A card id, or the card itself. */
  card: number | Card | null;
  /** Short line under an identity's message: the method it applies (DESIGN.md rule 10). */
  cite?: string | null;
  /** Optional extra: the episode, present on live events. */
  episode?: string | null;
  /** Optional extra: the step the message belongs to. */
  step?: string | null;
  /** Optional extra: a file to preview under the message (video or image, path inside the episode). */
  preview?: string | null;
  /** Optional extra: a small table of numbers under the message. */
  facts?: Fact[] | null;
  /** Optional: a finished exchange between two crew members (docs/crew-talk.md), shown as one collapsed line. */
  exchange?: Exchange | null;
  /** The running crew members this message reached at their next step, and when (conductor/deliver.py). */
  delivered?: Delivery[] | null;
}

export interface Delivery {
  identity: string;
  job: number;
  at: string;
}

/** One direct message between two crew members (docs/crew-talk.md). */
export interface CrewMessage {
  id: number;
  sender: string;
  recipient: string;
  kind: string;
  about: string;
  text: string;
  at?: string | null;
  route?: string | null;
  status?: string | null;
}

export interface Exchange {
  topic: string;
  result?: string | null;
  messages: CrewMessage[];
}

export interface ProfileRow {
  label: string;
  value: string;
  kind?: string;
  source?: string;
}

export interface ProfileRule {
  step: string;
  date: string;
  rule: string;
  source: string;
}

export interface Profile {
  source: "neutral" | "brand";
  rows: ProfileRow[];
  preview: string | null;
  rules: ProfileRule[];
}

export interface JobLog {
  lines: string[];
}

export interface PrompterLink {
  url: string;
  qr_svg: string;
}

export interface UploadResult {
  path: string;
  size: number;
}

/** One speaking block: a paragraph of the spoken text (or a heading, which has no number). */
export interface PrompterBlock {
  text: string;
  points: string[];
  heading?: boolean;
  /** The number on the screens, 1 for the first spoken block. null for a heading. */
  n?: number | null;
  /** Several blank lines or a heading start a new section (1, 2, …). */
  section?: number;
  /** The block's length on the shared timeline: its characters plus a breath. */
  weight?: number;
  /** Cue sheets only: a fixed line (said word for word) or a bullet (said freely). */
  kind?: "fixed" | "bullet";
  /** Cue sheets only. A fixed line's role (hook, punch, ask, bridge, line1, …) or a bullet's tag ("" if none). */
  role?: string;
  /** Cue sheets only: the page (part) the block is on: "opening", "unit 1", …, "payoff", "close". */
  page?: string;
  /** Cue sheets only: the unit's number, null outside the units. */
  unit?: number | null;
  /** Cue sheets only: what is on screen (a picture cue, not spoken). */
  picture?: string | null;
  /** Cue sheets only: a bullet's leading question, said as written. */
  question?: string | null;
  /** Cue sheets only: a bullet's cue word groups. */
  groups?: string[];
  /** Cue sheets only: hook, punch and the opening's first line, shown in the full text size. */
  big?: boolean;
}

/** One page of a cue sheet: a part of the sheet (the opening, a unit, the payoff, the close). */
export interface PrompterPage {
  /** The key of the take count: "opening", "unit 1", …, "payoff", "close". */
  page: string;
  /** The part's heading as written, without its notes ("Unit 1"). */
  label: string;
  /** The index of the page's first block. */
  first: number;
  /** The unit is built to be cut as a Short too. */
  short: boolean;
}

export interface PrompterScript {
  title: string;
  note?: string | null;
  mode: "full" | "points";
  /** "cuesheet": fixed lines and bullets in pages. "script" (or missing): paragraphs. */
  format?: "script" | "cuesheet";
  /** Cue sheets only: the pages in order. */
  pages?: PrompterPage[];
  blocks: PrompterBlock[];
  /** Characters per second at speed 1.0. */
  cps?: number;
  /** Changes when the shown script file changes. */
  version?: string;
}

export interface PrompterControl {
  guide?: number;
  playing: boolean;
  speed: number;
  /** The old position as a share of the whole text, kept for pages opened before the speaking blocks. */
  position: number;
  mirror: boolean;
  size: number;
  /** The shared timeline: the anchor (block index and offset 0..1 in it) at server time `at` (ms). */
  block?: number;
  offset?: number;
  at?: number;
  /** Raised by the server on every write; screens apply only newer states. */
  seq?: number;
  /** The screen that wrote this state. */
  by?: string;
  /** Raised on every jump, so every screen marks the block it jumped to. */
  cue?: number;
  /** Cue sheets: takes started per page (a command that lands at the start of a page counts one). */
  takes?: Record<string, number>;
  /** Server time of the answer (ms) and how long the server waited for a change (ms). */
  now?: number;
  waited?: number;
  version?: string;
}

/** The pseudo-episode that holds the onboarding chat. It never appears in state.episodes. */
export const ONBOARDING = "_onboarding";
export const CHANNEL = "_channel";

// ---------- motion graphics (docs/api.md "Motion cards" and "Motion") ----------

/** A loop and its still. Either may be null (a template without samples). */
export interface MotionMedia {
  loop: string | null;
  poster: string | null;
}

/** One beat of a motion plan: what the viewer must understand or feel, and the picture that does it. */
export interface MotionBeat {
  /** the id to strike: "beat:N" */
  row: string;
  beat: number;
  time: string; // "0:06"
  purpose: string | null;
  picture: string | null;
  struck: boolean;
  piece?: string | null;
  params?: Record<string, unknown>;
  length_s?: number | null;
  cost_usd?: number;
  /** column (a) only: a loop of the shelf piece */
  media?: MotionMedia | null;
}

/** Column (b): a piece built new for this video. */
export interface MotionNew {
  row: string; // "new:handoff"
  id: string;
  beat: number | null;
  brief: string | null;
  why_new: string | null;
  kind: "full" | "overlay" | string;
  plates: number;
  effort: string | null; // "S", "M", "L"
  cost_usd: number;
  cap_usd: number | null;
  struck: boolean;
  beats: MotionBeat[];
}

export type MotionSourceKind = "lesson" | "reference" | "baseline" | "retention";

/** Column (c): what makes this video clearly better than the last one. */
export interface MotionUpgrade {
  row: string; // "upgrade:u1"
  id: string;
  upgrade: string;
  source: { kind: MotionSourceKind | string; ref: string | null } | null;
  effort: string | null;
  cost_usd: number;
  chosen: boolean;
  struck: boolean;
  beats: MotionBeat[];
}

export interface MotionColumns {
  a: MotionBeat[];
  b: MotionNew[];
  c: MotionUpgrade[];
}

/** card.data.motion_plan of a motion-plan card. */
export interface MotionPlanData {
  version: number;
  file: string;
  md?: string;
  json_sha256?: string;
  columns: MotionColumns;
  /** the beats left to the speaker (most beats) */
  quiet: MotionBeat[];
  density: string | null;
  budget: string | null;
  estimate_usd: number | null;
  cap_usd: number | null;
  /** the episode that is the bar */
  bar: string | null;
  short: boolean;
}

/** One format of a style-frame card: our frame next to the reference (or the bar's frame). */
export interface StyleFrame {
  format: string; // "landscape", "portrait", "stage"
  ours: string;
  ours_url: string;
  ref: string | null;
  ref_url: string | null;
  /** "reference", "the bar", or the sentence for no reference */
  ref_label: string;
  /** a frame of the launch film: the craft bar every full-frame insert is compared with */
  launch?: string | null;
  launch_url?: string | null;
  launch_shows?: string | null;
  hue?: { dominant_share: number; ok: boolean; coloured_share?: number; accent_area_limit?: number; sparse_accent?: boolean } | null;
}

export interface StyleFrameData {
  insert: string;
  round: number;
  frames: StyleFrame[];
  /** further inserts of the plan that reuse the same piece; the yes covers them too */
  covers: string[];
}

/** card.data.template of a template card ("Keep it in your library?"). */
export interface MotionTemplate {
  name: string;
  title: string;
  version: number;
  kind: string;
  formats: string[];
  params: Record<string, unknown>;
  samples: Record<string, string>;
  poster: string | null;
  made_from: { episode: string; insert: string } | null;
  sha256?: string;
  /** the version this one replaces, if any */
  replaces: number | null;
}

export interface Strength {
  name: string;
  time: number | null;
  /** a picture of it, a path inside that episode or an /api/ URL */
  frame: string | null;
}

/** One side of a baseline card: the bar now, or the video that would become it. */
export interface BaselineSide {
  episode: string;
  report?: string;
  strengths: Strength[];
  measured?: Record<string, number | null>;
  better?: { what: string; time: number | null; against: string | null; frame: string | null }[];
}

export interface BaselineData {
  old: BaselineSide | null;
  new: BaselineSide;
}

/** GET /api/episodes/{id}/motion: the plan with its columns, the pieces on the film strip, the report. */
export interface EpisodeMotion {
  plan: MotionPlanView | null;
  pieces: MotionPiece[];
  report: MotionReport | null;
  retention: MotionRetention | null;
}

export interface MotionPlanView {
  file: string;
  md_url: string | null;
  version: number;
  card: { id: number; status: CardStatus } | null;
  approved: boolean;
  columns: MotionColumns;
  quiet: MotionBeat[];
  density: string | null;
  budget: string | null;
  estimate_usd: number | null;
  cap_usd: number | null;
  bar: string | null;
  short: boolean;
}

export type MotionState = "planned" | "style frame" | "building" | "in review" | "done";

/** A word anchor: the time sits on a spoken word, with an offset in seconds. */
export interface WordAnchor {
  word: string;
  offset?: number;
}

export interface MotionPiece {
  id: string;
  kind: "library" | "custom";
  scene: string | null;
  source: string | null;
  beat: number | null;
  column: "a" | "b" | "c" | null;
  state: MotionState;
  /** custom pieces: the first line of the brief */
  brief: string | null;
  loop: string | null;
  poster: string | null;
  start: number | WordAnchor | null;
  end: number | WordAnchor | null;
  transparent: boolean;
}

export interface MotionReport {
  better: string | null;
  behind: string | null;
  next: string | null;
  verdict: string | null;
  file: string;
  url: string | null;
}

export interface MotionRetention {
  fetched: string | null;
  summary: { moments: number; held: number; dropped: number; held_share: number | null } | null;
  unproven: boolean;
}

/** One row of the shelf (GET /api/motion/library). */
export interface ShelfRow {
  name: string;
  origin: "app" | "pack" | "episode";
  title: string;
  description: string;
  kind: string;
  formats: string[];
  version: number;
  versions?: number[];
  params: Record<string, unknown>;
  path?: string;
  samples: { landscape?: string; portrait?: string; stage?: string; poster?: string };
  made_from?: { episode: string; insert: string } | null;
  /** null until the template card's yes */
  approved?: { date?: string; by?: string; card?: number } | null;
  needs_plates?: boolean;
  notes?: { date?: string; text: string; source?: string }[];
  /** app rows: the pack has its own copy */
  overridden?: boolean;
  /** episode rows */
  episode?: string;
  insert?: string;
  promoted_as?: string | null;
  header_ok?: boolean;
  /** pack and app rows: the videos whose newest edit plan uses it */
  uses?: { episode: string; insert: string | null; version: number | null }[];
}

export interface MotionLesson {
  id: string;
  date: string;
  rule: string;
  evidence?: string;
  source?: string;
  line?: string;
}

/** GET /api/motion/ratchet: the bar, the lessons and the references. */
export interface MotionRatchet {
  bar: { episode: string; strengths?: Strength[]; report?: string; measured?: Record<string, number | null> } | null;
  lessons: MotionLesson[];
  merge_needed: boolean;
  references: { id: string; link?: string | null; file?: string | null; by?: string; reason?: string }[];
}
