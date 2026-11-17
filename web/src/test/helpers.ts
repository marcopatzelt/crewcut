// Test helpers: a fake fetch that answers docs/api.md routes, and small builders for API shapes.
import { vi } from "vitest";
import type { Activity, Card, Episode, Message, State, StepStatus } from "../api/types";
import { setBackend } from "../api/client";
import { steps } from "../../../tests/web-sample/fixtures";
import { stopLiveUpdates } from "../store/actions";
import { resetUi } from "../store/store";

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

type Answer = unknown | ((call: Call) => unknown);
export type Routes = Record<string, Answer>;

export class Reply {
  constructor(
    public status: number,
    public body: unknown,
    /** Not JSON: the body is sent as it is (a proxy's error page, a page that is not Crewcut). */
    public type = "application/json",
  ) {}
}

/** Pending forever: for loading states. */
export const NEVER = Symbol("never");

/**
 * Installs a fetch that answers "METHOD /path" keys (query string ignored unless the key has one).
 * Returns the list of calls.
 */
export function mockApi(routes: Routes): Call[] {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    let body: unknown = undefined;
    if (typeof init?.body === "string") body = JSON.parse(init.body);
    else if (init?.body) body = init.body;
    const call = { method, path: url.pathname + url.search, body };
    calls.push(call);
    const key = [`${method} ${url.pathname}${url.search}`, `${method} ${url.pathname}`].find((k) => k in routes);
    if (!key) {
      return new Response(JSON.stringify({ detail: `No route for ${method} ${url.pathname}` }), {
        status: 404,
        headers: { "content-type": "application/json" },
      });
    }
    const answer = routes[key];
    const value = typeof answer === "function" ? (answer as (c: Call) => unknown)(call) : answer;
    if (value === NEVER) return new Promise<Response>(() => undefined);
    if (value instanceof Error) throw value;
    const reply = value instanceof Reply ? value : new Reply(200, value);
    const json = reply.type.includes("json");
    return new Response(json ? JSON.stringify(reply.body) : String(reply.body), {
      status: reply.status,
      headers: { "content-type": reply.type },
    });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

/** Opens the app on one episode, as a link to #/e/<id> does (the start view is the Episodes home). */
export function openAt(id: string): void {
  window.history.replaceState(null, "", `/#/e/${encodeURIComponent(id)}`);
}

export function resetApp(): void {
  stopLiveUpdates();
  setBackend(null);
  resetUi();
  window.history.replaceState(null, "", "/");
}

export function episode(over: Partial<Episode> = {}): Episode {
  const statuses: StepStatus[] = ["done", "done", "done", "working", "open", "open", "open", "skipped", "open", "open"];
  return {
    id: "001-test",
    title: "A test episode",
    step: "script",
    steps: steps(statuses),
    updated: new Date().toISOString(),
    open_cards: 0,
    ...over,
  };
}

export function state(over: Partial<State> = {}): State {
  return {
    app: { version: "0.1.0", engine: "claude", engine_ok: true, gpu_local: false, onboarded: true },
    team: [
      { id: "showrunner", name: "Showrunner", role: "Runs the episode.", mark: "SR", skills: [], may_spend: false, may_publish: false },
      { id: "scout", name: "Scout", role: "Finds titles.", mark: "SC", skills: [], may_spend: false, may_publish: false },
      { id: "editor", name: "Editor", role: "Cuts.", mark: "ED", skills: [], may_spend: true, may_publish: false },
    ],
    episodes: [],
    activity: [],
    money: { today_usd: 0, episode_usd: {}, month_usd: 0, cap_month_usd: 20 },
    ...over,
  };
}

export function message(over: Partial<Message> = {}): Message {
  return { id: 1, at: new Date().toISOString(), author: "showrunner", text: "Hello.", card: null, ...over };
}

export function card(over: Partial<Card> = {}): Card {
  return {
    id: 4,
    episode: "001-test",
    step: "title",
    kind: "title",
    identity: "scout",
    title: "Pick a title",
    body: "Recommendation: option 1.",
    options: ["First title", "Second title", "Third title"],
    file: "brief/TITLE-v001.md",
    preview: null,
    sha256: "abcdef0123456789",
    status: "open",
    created: new Date().toISOString(),
    ...over,
  };
}

export function job(n: number, over: Partial<Activity> = {}): Activity {
  return {
    job: n,
    episode: "001-test",
    identity: "editor",
    step: "edit",
    doing: `Rendering scene ${n}`,
    progress: 0.5,
    status: "running",
    started: new Date().toISOString(),
    seconds: 60,
    cost_usd: 0,
    equiv_usd: null,
    ...over,
  };
}

/** The usual routes for one episode with messages and cards. */
export function episodeRoutes(ep: Episode, messages: Message[], cards: Card[]): Routes {
  return {
    [`GET /api/episodes/${ep.id}`]: { ...ep, project: { created: new Date().toISOString(), format: "landscape" }, files: [] },
    [`GET /api/episodes/${ep.id}/messages`]: messages,
    "GET /api/cards": cards,
  };
}
