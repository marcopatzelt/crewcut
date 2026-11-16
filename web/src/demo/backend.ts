// An in-memory stand-in for the Crewcut server, used with ?demo=1 or when no API answers.
// It answers the calls from docs/api.md with the fixtures and never runs anything.
import { ApiError, type Backend, type EventHandler, type EventKind } from "../api/client";
import type { Activity, Card, Episode, EpisodeMedia, Message, UploadResult } from "../api/types";
import { DEMO_FILES, makeDemo, steps } from "./fixtures";

const REPLY =
  "This is the demo. Nothing runs here, so nobody picks this up. Start Crewcut with Docker to work on a real episode.";

declare global {
  interface Window {
    /** Set by the scripted demo (?demo=1&play=1) when its sequence has ended, for the README recording. */
    __crewcutPlayDone?: boolean;
  }
}

export function createDemoBackend(opts: { latency?: number; play?: boolean } = {}): Backend {
  const latency = opts.latency ?? 60;
  const data = makeDemo(Date.now(), { play: opts.play });
  const handlers = new Set<EventHandler>();
  const playing = Boolean(opts.play);
  let nextMessage = 1000;
  let nextEpisode = 15;

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
    if (playing) return; // the scripted sequence shows the screen, not the demo notice
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
      if (method === "GET" && c === "media") {
        if (!data.details[b]) throw notFound(path);
        const none: EpisodeMedia = { thumbnails: [], cut: null, scenes: null, gpu: null };
        return out(data.media[b] ?? none);
      }
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
        if (ep) {
          ep.open_cards = Math.max(0, ep.open_cards - 1);
          if (ep.needs?.card === card.id) ep.needs = null;
        }
        // A picked thumbnail is the one in use from now on.
        const media = card.episode ? data.media[card.episode] : undefined;
        if (media && card.kind === "thumbnail" && c === "accept") {
          const at = typeof choice === "number" ? choice : 0;
          media.thumbnails = media.thumbnails.map((t, i) => ({ ...t, picked: i === at }));
        }
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

  // ---------- the scripted sequence for the README animation (?demo=1&play=1) ----------
  // Starts 600 ms after the page has loaded and the screen listens, in the episode view of 012: the GPU card springs
  // into the crew chat with "On this machine" chosen, the choice moves to the rented GPU, the button is pressed, the
  // card folds to one line, a new row slides into the working tiles and the rented GPU appears among the media. It
  // drives the real buttons, so the screen does what it does for a person. Then it stays still and sets
  // window.__crewcutPlayDone.
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  const stamp = (a: Activity, patch: Partial<Activity>): Activity => {
    const i = data.state.activity.findIndex((x) => x.job === a.job);
    const next = { ...a, ...patch };
    if (i < 0) data.state.activity.unshift(next);
    else data.state.activity[i] = next;
    return next;
  };
  const inPage = (selector: string) =>
    typeof document === "undefined" ? null : document.querySelector<HTMLElement>(selector);

  async function play() {
    const card = data.playCard;
    if (!card) return;
    const ep = data.state.episodes.find((e) => e.id === card.episode);
    // 1. The Editor asks: the card appears in the crew chat, the Editor's row waits for the yes.
    const shown = { ...card, created: new Date().toISOString() };
    data.cards.push(shown);
    if (ep) {
      ep.open_cards += 1;
      emit("episode", { ...ep, open_cards: ep.open_cards - 1 }); // the card event adds the count
    }
    emit("card", shown);
    if (data.playWaiting) emit("activity", stamp(data.playWaiting, { seconds: 0, started: new Date().toISOString() }));
    await sleep(1400);
    // 2. The choice moves from "On this machine" to the rented GPU; the button text follows.
    inPage(`[data-open-card="${card.id}"] [data-way="rented"]`)?.click();
    await sleep(1300);
    // 3. The button is pressed, then released: the yes goes out and the card folds to one line.
    const button = inPage(`[data-open-card="${card.id}"] [data-accept]`);
    button?.setAttribute("data-pressed", "true");
    await sleep(220);
    button?.removeAttribute("data-pressed");
    if (button) button.click();
    else {
      shown.status = "accepted";
      shown.decided_at = new Date().toISOString();
      if (ep) ep.open_cards = Math.max(0, ep.open_cards - 1);
      emit("card", shown);
    }
    await sleep(250);
    if (data.playWaiting) {
      emit("activity", stamp(data.playWaiting, {
          status: "done",
          doing: "Asked for your yes on the GPU",
          seconds: 4,
          ended: new Date().toISOString(),
        }));
    }
    await sleep(450);
    // 4. The rented GPU starts: a new row slides into the crew chat, the GPU card and the render tiles appear.
    if (card.episode && data.playMedia) data.media[card.episode] = data.playMedia;
    if (data.playRender) emit("activity", stamp(data.playRender, { started: new Date().toISOString() }));
    await sleep(2700);
    if (typeof window !== "undefined") window.__crewcutPlayDone = true;
  }

  let loaded = typeof document === "undefined" || document.readyState === "complete";
  let listening = false;
  let started = false;
  const maybePlay = () => {
    if (!playing || started || !loaded || !listening) return;
    started = true;
    setTimeout(() => void play(), 600);
  };
  if (playing && !loaded) {
    window.addEventListener(
      "load",
      () => {
        loaded = true;
        maybePlay();
      },
      { once: true },
    );
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
      const file = DEMO_FILES[path];
      return file ? `${base}${file}` : `${base}demo/missing/${path}`;
    },
    subscribe(handler: EventHandler) {
      handlers.add(handler);
      listening = true;
      maybePlay();
      return () => handlers.delete(handler);
    },
  };
}
