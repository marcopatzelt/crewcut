// An in-memory stand-in for the Crewcut server with the sample data. The web tests set it with setBackend; the CI
// picture server (tools/ci/sample_server.mjs) bundles it for Node and answers /api with it. Never part of the app.
// It answers the calls from docs/api.md with the fixtures and never runs anything.
import { ApiError, type Backend, type EventHandler, type EventKind } from "../../web/src/api/client";
import type { Activity, Card, Episode, EpisodeMedia, EpisodeMotion, Message, UploadResult } from "../../web/src/api/types";
import { CHANNEL } from "../../web/src/api/types";
import { SAMPLE_FILES, makeSample, shortSteps, steps } from "./fixtures";

export { makeSample };

const REPLY = "These are sample data. Nothing runs here, so nobody picks this up.";

export interface SampleBackend extends Backend {
  /** The README animation in two steps; the CI script clicks the real buttons in between (tools/ci/readme_shots.mjs). */
  play: {
    /** The GPU card springs into the crew chat of 012 and the Editor's row waits for the yes. */
    cardIn(): void;
    /** After the yes: the Editor's row is done, the rented GPU starts, its card and render tiles join the media. */
    afterYes(): Promise<void>;
  };
}

export function createSampleBackend(opts: { latency?: number; play?: boolean; base?: string } = {}): SampleBackend {
  const latency = opts.latency ?? 60;
  const base = opts.base ?? "/";
  const data = makeSample(Date.now(), { play: opts.play });
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
    if (playing) return; // the scripted sequence shows the screen, not the reply
    setTimeout(() => emit("message", addMessage(episode, "showrunner", REPLY)), 700);
  };

  const notFound = (path: string) => new ApiError(404, `Nothing at ${path} in the sample data.`);

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    await wait();
    const url = new URL(path, "http://sample.invalid");
    const parts = url.pathname.split("/").filter(Boolean).map(decodeURIComponent); // ["api", ...]
    const q = url.searchParams;
    const [, a, b, c] = parts;
    const out = (v: unknown) => clone(v) as T;

    if (method === "GET" && a === "state") return out(data.state);
    if (method === "GET" && a === "team") return out(data.team);
    if (method === "GET" && a === "profile") return out(data.profile);
    if (method === "GET" && a === "money") return out({ ...data.state.money, rows: [] });

    if (a === "channel" && b === "messages" && !c) {
      if (method === "GET") {
        const after = Number(q.get("after") ?? 0);
        return out((data.messages[CHANNEL] ?? []).filter((message) => message.id > after));
      }
      if (method === "POST") {
        const text = String((body as { text?: string } | undefined)?.text ?? "");
        const message = addMessage(CHANNEL, "user", text);
        emit("message", message);
        reply(CHANNEL);
        return out(message);
      }
    }

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
      if (method === "POST" && c === "gpu" && parts[5] === "stop") {
        const media = data.media[b];
        const gpu = media?.gpu;
        if (!media || !gpu || String(gpu.session) !== parts[4]) throw notFound(path);
        media.gpu = null;
        emit("message", addMessage(b, "editor", `Stopped the rented GPU: 1 machine(s) deleted, $${gpu.so_far_usd.toFixed(2)} in all. The frames that came home stay.`));
        for (const x of data.state.activity) {
          if (x.episode === b && /rented/i.test(x.doing ?? "")) {
            x.status = "done";
            x.doing = "Stopped by you: the frames that came home stay";
            emit("activity", x);
          }
        }
        return out({ stopped: 1, rentals: [gpu.session], cost_usd: gpu.so_far_usd });
      }
      if (method === "POST" && c === "shorts") {
        const src = data.state.episodes.find((x) => x.id === b);
        if (!src) throw notFound(path);
        if (src.kind === "short") throw new ApiError(400, "This is a Short already; make Shorts from a long episode.");
        const n = String((nextEpisode += 1)).padStart(3, "0");
        const ep: Episode = {
          id: `${n}-short-${b.slice(4, 24)}`,
          title: `Short from ${src.title}`.slice(0, 90),
          step: "idea",
          steps: shortSteps(["idea", "title", "edit", "thumbnail", "upload", "results"], ["working", "open", "open", "open", "open", "skipped"]),
          updated: new Date().toISOString(),
          open_cards: 0,
          kind: "short",
          mode: "clip",
          source_episode: b,
        };
        data.state.episodes.unshift(ep);
        data.details[ep.id] = { ...ep, project: { id: ep.id, title: ep.title, created: ep.updated, format: "portrait" }, files: [] };
        data.messages[ep.id] = [];
        const job = Math.max(0, ...data.state.activity.map((x) => x.job)) + 1;
        const row: Activity = {
          job, episode: ep.id, identity: "scout", step: "idea", doing: "Finding passages that stand on their own",
          progress: null, status: "running", started: ep.updated, seconds: 0, cost_usd: 0, equiv_usd: null,
        };
        data.state.activity.unshift(row);
        emit("message", addMessage(b, "showrunner", `Started a Short from this episode (${ep.id}). The Scout looks for passages that stand on their own.`));
        emit("episode", ep);
        emit("activity", row);
        return out({ episode: ep.id, job });
      }
      if (method === "GET" && c === "media") {
        if (!data.details[b]) throw notFound(path);
        const none: EpisodeMedia = { thumbnails: [], cut: null, scenes: null, gpu: null };
        return out(data.media[b] ?? none);
      }
      if (method === "GET" && c === "motion") {
        if (!data.details[b]) throw notFound(path);
        const none: EpisodeMotion = { plan: null, pieces: [], report: null, retention: null };
        return out(data.motion[b] ?? none);
      }
    }

    if (a === "motion" && method === "GET") {
      if (b === "library") return out({ templates: data.shelf });
      if (b === "ratchet") return out(data.ratchet);
    }

    if (a === "cards") {
      if (method === "GET" && !b) {
        const ep = q.get("episode");
        const status = q.get("status");
        return out(data.cards.filter((x) => (!ep || x.episode === ep) && (!status || x.status === status)));
      }
      const card = data.cards.find((x) => x.id === Number(b));
      if (!card) throw notFound(path);
      if (method === "POST" && c === "strike") {
        strikeRow(card);
      }
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
        // the motion view follows its cards: an approved plan, a style frame with a yes (its piece is built next)
        const motion = card.episode ? data.motion[card.episode] : undefined;
        if (motion?.plan && card.kind === "motion-plan" && motion.plan.card?.id === card.id) {
          motion.plan.card = { id: card.id, status: card.status };
          motion.plan.approved = card.status === "accepted";
        }
        if (motion && card.kind === "style-frame" && c === "accept") {
          const insert = card.data?.insert;
          motion.pieces = motion.pieces.map((p) => (p.id === insert ? { ...p, state: "building" } : p));
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

  /**
   * "Not this one" on a motion plan card. The sample plans are all answered (the commercial's has its yes before its
   * style frame), so a strike is refused as the server refuses it on an answered card.
   */
  function strikeRow(card: Card): never {
    if (card.kind !== "motion-plan") throw new ApiError(409, "Only a motion plan card has rows to strike.");
    throw new ApiError(409, "This card is answered already.");
  }

  // ---------- the scripted sequence for the README animation ----------
  // In the episode view of 012: the GPU card springs into the crew chat with "On this machine" chosen; the CI script
  // moves the choice to the rented GPU and presses the button (the real yes, POST /accept); then the Editor's row is
  // done, a new row slides into the working tiles and the rented GPU appears among the media.
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  const stamp = (a: Activity, patch: Partial<Activity>): Activity => {
    const i = data.state.activity.findIndex((x) => x.job === a.job);
    const next = { ...a, ...patch };
    if (i < 0) data.state.activity.unshift(next);
    else data.state.activity[i] = next;
    return next;
  };

  const play = {
    cardIn() {
      const card = data.playCard;
      if (!card) return;
      const ep = data.state.episodes.find((e) => e.id === card.episode);
      const shown = { ...card, created: new Date().toISOString() };
      data.cards.push(shown);
      if (ep) {
        ep.open_cards += 1;
        emit("episode", { ...ep, open_cards: ep.open_cards - 1 }); // the card event adds the count
      }
      emit("card", shown);
      if (data.playWaiting) emit("activity", stamp(data.playWaiting, { seconds: 0, started: new Date().toISOString() }));
    },
    async afterYes() {
      const card = data.playCard;
      if (!card) return;
      if (data.playWaiting) {
        emit("activity", stamp(data.playWaiting, {
          status: "done",
          doing: "Asked for your yes on the GPU",
          seconds: 4,
          ended: new Date().toISOString(),
        }));
      }
      await sleep(450);
      if (card.episode && data.playMedia) data.media[card.episode] = data.playMedia;
      if (data.playRender) emit("activity", stamp(data.playRender, { started: new Date().toISOString() }));
    },
  };

  return {
    request,
    async upload(episode: string, files: File[]): Promise<UploadResult[]> {
      await new Promise((r) => setTimeout(r, 400 + latency));
      const res = files.map((f) => ({ path: `inbox/${f.name}`, size: f.size }));
      const text = `Got ${files.length === 1 ? "1 file" : `${files.length} files`}. Sample data: nothing is ingested.`;
      emit("message", addMessage(episode, "editor", text));
      return res;
    },
    fileUrl(_episode: string, path: string): string {
      const file = SAMPLE_FILES[path];
      return file ? `${base}${file}` : `${base}sample/missing/${path}`;
    },
    subscribe(handler: EventHandler) {
      handlers.add(handler);
      return () => handlers.delete(handler);
    },
    play,
  };
}
