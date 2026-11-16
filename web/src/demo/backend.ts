// An in-memory stand-in for the Crewcut server, used with ?demo=1 or when no API answers.
// It answers the calls from docs/api.md with the fixtures and never runs anything.
import { ApiError, type Backend, type EventHandler, type EventKind } from "../api/client";
import type { Card, Episode, Message, UploadResult } from "../api/types";
import { DEMO_FILES, makeDemo, steps } from "./fixtures";

const REPLY =
  "This is the demo. Nothing runs here, so nobody picks this up. Start Crewcut with Docker to work on a real episode.";

export function createDemoBackend(opts: { latency?: number } = {}): Backend {
  const latency = opts.latency ?? 60;
  const data = makeDemo();
  const handlers = new Set<EventHandler>();
  let nextMessage = 1000;
  let nextEpisode = 5;

  const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
  const wait = () => new Promise((r) => setTimeout(r, latency));
  const emit = (kind: EventKind, payload: unknown) => {
    for (const h of handlers) h(kind, clone(payload));
  };

  const addMessage = (episode: string, author: string, text: string, step?: string): Message => {
    const m: Message = { id: (nextMessage += 1), at: new Date().toISOString(), author, text, card: null, episode };
    if (step) m.step = step;
    (data.messages[episode] ??= []).push(m);
    return m;
  };

  const reply = (episode: string) => {
    setTimeout(() => emit("message", addMessage(episode, "showrunner", REPLY)), 700);
  };

  const notFound = (path: string) => new ApiError(404, `Nothing at ${path} in the demo.`);

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    await wait();
    const url = new URL(path, "http://demo.invalid");
    const parts = url.pathname.split("/").filter(Boolean).map(decodeURIComponent); // ["api", ...]
    const q = url.searchParams;
    const [, a, b, c] = parts;
    const out = (v: unknown) => clone(v) as T;

    if (method === "GET" && a === "state") return out(data.state);
    if (method === "GET" && a === "team") return out(data.team);
    if (method === "GET" && a === "profile") return out(data.profile);
    if (method === "GET" && a === "money") return out({ ...data.state.money, rows: [] });

    if (a === "episodes") {
      if (method === "POST" && !b) {
        const text = String((body as { text?: string } | undefined)?.text ?? "").trim();
        const n = String((nextEpisode += 1)).padStart(3, "0");
        const slug =
          text
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-|-$/g, "")
            .slice(0, 32) || "new";
        const ep: Episode = {
          id: `${n}-${slug}`,
          title: text.length > 90 ? `${text.slice(0, 89)}…` : text || "New episode",
          step: "idea",
          steps: steps(["working", "open", "open", "open", "open", "open", "open", "open", "open", "open"]),
          updated: new Date().toISOString(),
          open_cards: 0,
        };
        data.state.episodes.unshift(ep);
        data.details[ep.id] = { ...ep, project: { id: ep.id, title: ep.title, created: ep.updated, format: "landscape" }, files: [] };
        data.messages[ep.id] = [];
        addMessage(ep.id, "user", text);
        reply(ep.id);
        return out(ep);
      }
      if (!b) throw notFound(path);
      if (method === "GET" && !c) {
        const d = data.details[b];
        if (!d) throw notFound(path);
        return out(d);
      }
      if (c === "messages") {
        if (method === "GET") {
          const after = Number(q.get("after") ?? 0);
          return out((data.messages[b] ?? []).filter((m) => m.id > after));
        }
        if (method === "POST") {
          const text = String((body as { text?: string } | undefined)?.text ?? "");
          const m = addMessage(b, "user", text);
          reply(b);
          return out(m);
        }
      }
      if (method === "GET" && c === "prompter") return out(data.prompter);
    }

    if (a === "cards") {
      if (method === "GET" && !b) {
        const ep = q.get("episode");
        const status = q.get("status");
        return out(data.cards.filter((x) => (!ep || x.episode === ep) && (!status || x.status === status)));
      }
      const card = data.cards.find((x) => x.id === Number(b));
      if (!card) throw notFound(path);
      if (method === "POST" && (c === "accept" || c === "decline")) {
        card.status = c === "accept" ? "accepted" : "declined";
        card.decided_at = new Date().toISOString();
        const choice = (body as { choice?: number } | undefined)?.choice;
        if (typeof choice === "number") card.choice = choice;
        const ep = data.state.episodes.find((e) => e.id === card.episode);
        if (ep) ep.open_cards = Math.max(0, ep.open_cards - 1);
        if (card.episode) reply(card.episode);
        setTimeout(() => emit("card", card), 0);
        return out(card as Card);
      }
    }

    if (a === "jobs") {
      if (method === "GET" && !b) {
        const ep = q.get("episode");
        const status = q.get("status");
        return out(data.state.activity.filter((j) => (!ep || j.episode === ep) && (!status || j.status === status)));
      }
      if (method === "GET" && c === "log") {
        const lines = data.logs[Number(b)];
        if (!lines) throw notFound(path);
        return out({ lines });
      }
    }

    throw notFound(path);
  }

  return {
    request,
    async upload(episode: string, files: File[]): Promise<UploadResult[]> {
      await new Promise((r) => setTimeout(r, 400 + latency));
      const res = files.map((f) => ({ path: `inbox/${f.name}`, size: f.size }));
      const text = `Got ${files.length === 1 ? "1 file" : `${files.length} files`}. In the demo nothing is ingested.`;
      emit("message", addMessage(episode, "editor", text));
      return res;
    },
    fileUrl(_episode: string, path: string): string {
      const base = import.meta.env.BASE_URL ?? "/";
      return `${base}${DEMO_FILES[path] ?? "demo/missing.svg"}`;
    },
    subscribe(handler: EventHandler) {
      handlers.add(handler);
      return () => handlers.delete(handler);
    },
  };
}
