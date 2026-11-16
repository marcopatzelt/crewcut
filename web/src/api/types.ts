// Shapes from docs/api.md. Fields marked "optional extra" are read when present and never required.

export type StepStatus = "open" | "working" | "waiting" | "done" | "skipped";

export interface Step {
  id: string;
  n: number;
  label: string;
  status: StepStatus;
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
  id: string;
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
  | "other";

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

export interface PrompterScript {
  title: string;
  mode: "full" | "points";
  blocks: Array<{ text: string; points: string[] }>;
}

export interface PrompterControl {
  playing: boolean;
  speed: number;
  position: number;
  mirror: boolean;
  size: number;
}

/** The pseudo-episode that holds the onboarding chat. It never appears in state.episodes. */
export const ONBOARDING = "_onboarding";
