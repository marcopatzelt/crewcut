// The HTTP client for docs/api.md. In demo mode every call goes to the in-memory demo backend instead.
import type {
  Activity,
  Card,
  Episode,
  EpisodeDetail,
  EpisodeMedia,
  Identity,
  JobLog,
  Message,
  Money,
  Profile,
  PrompterLink,
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

/** The demo backend implements the same calls without a server. */
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
    const unreachable = res.status === 404 && !isJson;
    throw new ApiError(res.status, detail || `The server answered ${res.status}.`, unreachable);
  }
  if (res.status === 204) return undefined as T;
  if (!isJson) {
    throw new ApiError(res.status, "The answer was not from Crewcut.", true);
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;
const encPath = (p: string) => p.split("/").map(enc).join("/");

export const api = {
  state: () => request<State>("GET", "/api/state"),
  episode: (id: string) => request<EpisodeDetail>("GET", `/api/episodes/${enc(id)}`),
  createEpisode: (text: string) => request<Episode>("POST", "/api/episodes", { text }),
  messages: (id: string, after?: number) =>
    request<Message[]>("GET", `/api/episodes/${enc(id)}/messages${after ? `?after=${after}` : ""}`),
  say: (id: string, text: string) => request<Message>("POST", `/api/episodes/${enc(id)}/messages`, { text }),
  cards: (episode: string, status?: string) =>
    request<Card[]>("GET", `/api/cards?episode=${enc(episode)}${status ? `&status=${enc(status)}` : ""}`),
  accept: (id: number, choice?: number) =>
    request<Card>("POST", `/api/cards/${id}/accept`, choice === undefined ? {} : { choice }),
  decline: (id: number, reason?: string) =>
    request<Card>("POST", `/api/cards/${id}/decline`, reason ? { reason } : {}),
  team: () => request<Identity[]>("GET", "/api/team"),
  jobs: (episode?: string) =>
    request<Activity[]>("GET", `/api/jobs${episode ? `?episode=${enc(episode)}` : ""}`),
  jobLog: (id: number) => request<JobLog>("GET", `/api/jobs/${id}/log`),
  profile: () => request<Profile>("GET", "/api/profile"),
  money: () => request<Money>("GET", "/api/money"),
  prompter: (id: string) => request<PrompterLink>("GET", `/api/episodes/${enc(id)}/prompter`),
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
