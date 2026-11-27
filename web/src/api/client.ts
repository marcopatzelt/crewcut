// The HTTP client for docs/api.md. Tests can put an in-memory backend in its place (setBackend); the app never does.
import { CHANNEL } from "./types";
import type {
  Activity,
  Card,
  ClaudeAccount,
  EngineLogin,
  Episode,
  EpisodeDetail,
  EpisodeInterview,
  EpisodeMedia,
  EpisodeMotion,
  FormatLibrary,
  Idea,
  Identity,
  ImportedFiles,
  JobLog,
  Length,
  Message,
  Money,
  MotionRatchet,
  Profile,
  PrompterLink,
  Scoreboard,
  ShelfRow,
  State,
  UploadResult,
} from "./types";

export class ApiError extends Error {
  status: number;
  /** True when no Crewcut API answers at this address (network error, 404, or not JSON). */
  unreachable: boolean;
  constructor(status: number, message: string, unreachable = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.unreachable = unreachable;
  }
}

export type EventKind = "activity" | "message" | "card" | "cost" | "episode" | "crew";
export type EventHandler = (kind: EventKind, data: unknown) => void;

/** An in-memory stand-in with the same calls, for the tests only. */
export interface Backend {
  request<T>(method: string, path: string, body?: unknown): Promise<T>;
  upload(episode: string, files: File[]): Promise<UploadResult[]>;
  fileUrl(episode: string, path: string): string;
  subscribe(handler: EventHandler): () => void;
}

let backend: Backend | null = null;

export function setBackend(b: Backend | null): void {
  backend = b;
}

export function usingBackend(): boolean {
  return backend !== null;
}

function detailOf(body: unknown): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.detail === "string") return b.detail;
    if (typeof b.error === "string") return b.error;
  }
  return "";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (backend) return backend.request<T>(method, path, body);
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Couldn't reach Crewcut. Check that the container runs, then try again.", true);
  }
  const type = res.headers.get("content-type") ?? "";
  const isJson = type.includes("json");
  if (!res.ok) {
    let detail = "";
    if (isJson) detail = detailOf(await res.json().catch(() => null));
    // Not Crewcut answering: a page that is not JSON, or a proxy in front saying the server behind it is not up.
    const unreachable = (res.status === 404 && !isJson) || ([502, 503, 504].includes(res.status) && !isJson);
    throw new ApiError(res.status, detail || `The server answered ${res.status}.`, unreachable);
  }
  if (res.status === 204) return undefined as T;
  if (!isJson) {
    throw new ApiError(res.status, "The answer was not from Crewcut.", true);
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;
const messagePath = (id: string) => id === CHANNEL ? "/api/channel/messages" : `/api/episodes/${enc(id)}/messages`;
const encPath = (p: string) => p.split("/").map(enc).join("/");

export const api = {
  state: () => request<State>("GET", "/api/state"),
  episode: (id: string) => request<EpisodeDetail>("GET", `/api/episodes/${enc(id)}`),
  importedFiles: (id: string, folder: string, offset: number) =>
    request<ImportedFiles>("GET", `/api/episodes/${enc(id)}/imported-files?folder=${enc(folder)}&offset=${offset}`),
  createEpisode: (text: string, opts: { length?: Length; show_format?: string | null } = {}) =>
    request<Episode>("POST", "/api/episodes", {
      text,
      ...(opts.length && opts.length !== "auto" ? { length: opts.length } : {}),
      ...(opts.show_format ? { show_format: opts.show_format } : {}),
    }),
  formats: () => request<FormatLibrary>("GET", "/api/formats"),
  ideas: () => request<Idea[]>("GET", "/api/ideas"),
  startIdea: (id: string) => request<{ idea: Idea; episode: Episode }>("POST", `/api/ideas/${enc(id)}/start`, {}),
  dismissIdea: (id: string) => request<Idea>("POST", `/api/ideas/${enc(id)}/dismiss`, {}),
  scoreboard: () => request<Scoreboard>("GET", "/api/scoreboard"),
  messages: (id: string, after?: number) =>
    request<Message[]>("GET", `${messagePath(id)}${after !== undefined ? `?after=${after}` : ""}`),
  say: (id: string, text: string) => request<Message>("POST", messagePath(id), { text }),
  cards: (episode: string, status?: string) =>
    episode === CHANNEL ? Promise.resolve<Card[]>([]) : request<Card[]>("GET", `/api/cards?episode=${enc(episode)}${status ? `&status=${enc(status)}` : ""}`),
  accept: (id: number, choice?: number) =>
    request<Card>("POST", `/api/cards/${id}/accept`, choice === undefined ? {} : { choice }),
  decline: (id: number, reason?: string) =>
    request<Card>("POST", `/api/cards/${id}/decline`, reason ? { reason } : {}),
  team: () => request<Identity[]>("GET", "/api/team"),
  jobs: (episode?: string) =>
    request<Activity[]>("GET", `/api/jobs${episode ? `?episode=${enc(episode)}` : ""}`),
  jobLog: (id: number) => request<JobLog>("GET", `/api/jobs/${id}/log`),
  profile: () => request<Profile>("GET", "/api/profile"),
  engineLogin: () => request<EngineLogin>("GET", "/api/engine/login"),
  useEngine: (name: "claude" | "codex") => request<EngineLogin>("POST", `/api/engine/${name}/use`, {}),
  claudeConnect: () => request<{ url: string }>("POST", "/api/engine/claude/connect", {}),
  claudeCode: (code: string) =>
    request<{ connected: boolean; account: ClaudeAccount }>("POST", "/api/engine/claude/code", { code }),
  claudeDisconnect: () => request<EngineLogin>("POST", "/api/engine/claude/disconnect", {}),
  codexConnect: () => request<EngineLogin["codex"]>("POST", "/api/engine/codex/connect", {}),
  money: () => request<Money>("GET", "/api/money"),
  prompter: (id: string) => request<PrompterLink>("GET", `/api/episodes/${enc(id)}/prompter`),
  fullAuto: (id: string) => request<{ mode: string; blocked?: string; complete?: boolean }>("GET", `/api/episodes/${enc(id)}/full-auto`),
  /** The interview bar: "skip" the interview, or "done" after answering in several messages. */
  interview: (id: string, action: "skip" | "done") =>
    request<EpisodeInterview | null>("POST", `/api/episodes/${enc(id)}/interview`, { action }),
  setFullAuto: (id: string, mode: string) => request<{ mode: string; blocked?: string; complete?: boolean }>("POST", `/api/episodes/${enc(id)}/full-auto`, { mode }),
  /** What the episode view shows first: thumbnails, the cut, 3D scenes, the rented GPU. */
  media: (id: string) => request<EpisodeMedia>("GET", `/api/episodes/${enc(id)}/media`),
  /** The GPU card's Stop: deletes the machines of that render now; the frames that came home stay. */
  stopGpu: (id: string, rental: number) =>
    request<{ stopped: number; rentals: number[]; cost_usd: number }>(
      "POST",
      `/api/episodes/${enc(id)}/gpu/${rental}/stop`,
    ),
  /** "Make a Short": a Short in clip mode from this episode; the Scout starts on the passages. */
  makeShort: (id: string) => request<{ episode: string; job: number }>("POST", `/api/episodes/${enc(id)}/shorts`),
  /** The motion of an episode: the plan with its three columns, the pieces on the film strip, the report's lines. */
  motion: (id: string) => request<EpisodeMotion>("GET", `/api/episodes/${enc(id)}/motion`),
  /** The shelf: the pack's templates first, then the app's, then the pieces made in episodes. */
  motionLibrary: () => request<{ templates: ShelfRow[] }>("GET", "/api/motion/library"),
  /** The bar, the lessons and the references. */
  motionRatchet: () => request<MotionRatchet>("GET", "/api/motion/ratchet"),
  /** "Not this one": strikes (or brings back) one row of an open motion plan card; the card shows the next version. */
  strike: (card: number, row: string, struck: boolean) =>
    request<Card>("POST", `/api/cards/${card}/strike`, { row, struck }),

  async upload(episode: string, files: File[]): Promise<UploadResult[]> {
    if (backend) return backend.upload(episode, files);
    const form = new FormData();
    for (const f of files) form.append("file", f, f.name);
    let res: Response;
    try {
      res = await fetch(`/api/episodes/${enc(episode)}/upload`, { method: "POST", body: form });
    } catch {
      throw new ApiError(0, "Couldn't reach Crewcut. Check that the container runs, then try again.", true);
    }
    if (!res.ok) {
      const detail = detailOf(await res.json().catch(() => null));
      throw new ApiError(res.status, detail || `The server answered ${res.status}.`);
    }
    return (await res.json()) as UploadResult[];
  },

  fileUrl(episode: string, path: string): string {
    if (path.startsWith("/api/")) return path;
    if (backend) return backend.fileUrl(episode, path);
    return `/api/files/${enc(episode)}/${encPath(path)}`;
  },
};

/**
 * Live updates. Calls onEvent for each server-sent event. On a broken stream it closes the stream,
 * waits (1 s, 2 s, 4 s … up to 30 s), calls onReconnect (the caller fetches the state again) and opens a new one.
 */
export function connectEvents(handlers: {
  onEvent: EventHandler;
  onReconnect: () => Promise<void>;
  onStatus: (s: "open" | "retrying") => void;
}): () => void {
  if (backend) return backend.subscribe(handlers.onEvent);
  if (typeof EventSource === "undefined") return () => undefined;

  let source: EventSource | null = null;
  let retries = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  // "crew" (one direct message between crew members) is read but not shown: a finished exchange arrives as a message.
  const kinds: EventKind[] = ["activity", "message", "card", "cost", "episode", "crew"];

  const open = () => {
    if (stopped) return;
    const es = new EventSource("/api/events");
    source = es;
    for (const kind of kinds) {
      es.addEventListener(kind, (e) => {
        try {
          handlers.onEvent(kind, JSON.parse((e as MessageEvent<string>).data));
        } catch {
          // A malformed event is skipped; the next state fetch corrects the screen.
        }
      });
    }
    es.onopen = () => {
      retries = 0;
      handlers.onStatus("open");
    };
    es.onerror = () => {
      es.close();
      if (stopped) return;
      handlers.onStatus("retrying");
      const delay = Math.min(30_000, 1000 * 2 ** retries);
      retries += 1;
      timer = setTimeout(() => {
        handlers
          .onReconnect()
          .catch(() => undefined)
          .finally(open);
      }, delay);
    };
  };

  open();
  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    source?.close();
  };
}
