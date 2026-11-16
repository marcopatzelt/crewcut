// Everything that changes the store: boot, navigation, live events, sending, accepting, uploading.
import { api, ApiError, connectEvents, setBackend, usingBackend, type EventKind } from "../api/client";
import { ONBOARDING, type Activity, type Card, type Episode, type Message, type Money, type State } from "../api/types";
import { createDemoBackend } from "../demo/backend";
import { getUi, setUi, type Thread, type UiState, type View } from "./store";

export function messageOf(e: unknown): string {
  if (e instanceof Error && e.message) return e.message;
  return "Something went wrong.";
}

// ---------- navigation (the view lives in the URL hash, so Back works and CI can open each place) ----------

export function viewToHash(v: View): string {
  switch (v.kind) {
    case "episode":
      return v.id === ONBOARDING ? "#/onboarding" : `#/e/${encodeURIComponent(v.id)}`;
    case "new":
      return "#/new";
    case "profile":
      return "#/profile";
    case "crew":
      return "#/crew";
    case "job":
      return `#/job/${v.id}`;
  }
}

export function hashToView(hash: string): View | null {
  const h = hash.replace(/^#\/?/, "");
  if (!h) return null;
  const [head, rest] = [h.split("/")[0], h.split("/").slice(1).join("/")];
  if (head === "e" && rest) return { kind: "episode", id: decodeURIComponent(rest) };
  if (head === "onboarding") return { kind: "episode", id: ONBOARDING };
  if (head === "new") return { kind: "new" };
  if (head === "profile") return { kind: "profile" };
  if (head === "crew") return { kind: "crew" };
  if (head === "job" && /^\d+$/.test(rest)) return { kind: "job", id: Number(rest) };
  return null;
}

function defaultView(state: State): View {
  if (!state.app.onboarded) return { kind: "episode", id: ONBOARDING };
  const first = state.episodes[0];
  return first ? { kind: "episode", id: first.id } : { kind: "new" };
}

export function navigate(v: View, opts: { replace?: boolean; fromHash?: boolean } = {}): void {
  setUi((s) => ({
    view: v,
    menuOpen: false,
    lastEpisode: v.kind === "episode" ? v.id : s.lastEpisode,
  }));
  if (!opts.fromHash && typeof window !== "undefined") {
    const h = viewToHash(v);
    if (window.location.hash !== h) {
      const url = `${window.location.pathname}${window.location.search}${h}`;
      if (opts.replace) window.history.replaceState(null, "", url);
      else window.history.pushState(null, "", url);
    }
  }
  if (v.kind === "episode") void loadThread(v.id);
}

export function onHashChange(): void {
  const v = hashToView(window.location.hash);
  const state = getUi().state;
  if (v) navigate(v, { fromHash: true });
  else if (state) navigate(defaultView(state), { replace: true });
}

// ---------- boot and live ----------

let stopLive: (() => void) | null = null;
let bootSeq = 0;

export async function boot(opts: { demo?: boolean; play?: boolean } = {}): Promise<void> {
  const mine = (bootSeq += 1);
  setUi({ boot: "loading", bootError: null });
  if (opts.demo && !usingBackend()) {
    setBackend(createDemoBackend({ play: opts.play }));
    setUi({ demo: "asked" });
  }
  let state: State;
  try {
    state = await api.state();
  } catch (e) {
    if (mine !== bootSeq) return; // a newer boot owns the screen
    if (e instanceof ApiError && e.unreachable && !usingBackend()) {
      setBackend(createDemoBackend());
      setUi({ demo: "auto" });
      return boot();
    }
    setUi({ boot: "error", bootError: messageOf(e) });
    return;
  }
  if (mine !== bootSeq) return;
  setUi({ state, boot: "ready", seen: stamp(state.activity, {}) });
  const fromHash = typeof window !== "undefined" ? hashToView(window.location.hash) : null;
  navigate(fromHash ?? defaultView(state), { replace: true });
  startLive();
}

export function startLive(): void {
  stopLive?.();
  stopLive = connectEvents({
    onEvent: applyEvent,
    onReconnect: refresh,
    onStatus: (live) => setUi({ live }),
  });
}

export function stopLiveUpdates(): void {
  stopLive?.();
  stopLive = null;
}

/** After a broken stream: fetch the state again and anything new in the open chats. */
export async function refresh(): Promise<void> {
  const state = await api.state();
  setUi((s) => ({ state, seen: stamp(state.activity, s.seen) }));
  const { threads, view } = getUi();
  await Promise.all(
    Object.entries(threads).map(async ([id, t]) => {
      if (t.status !== "ready") return;
      const last = t.messages[t.messages.length - 1]?.id;
      const fresh = await api.messages(id, last);
      addMessages(id, fresh);
    }),
  );
  if (view.kind === "episode") {
    const cards = await api.cards(view.id);
    for (const c of cards) upsertCard(c);
  }
}

function stamp(activity: Activity[], prev: Record<number, number>): Record<number, number> {
  const now = Date.now();
  const seen = { ...prev };
  for (const a of activity) seen[a.job] = now;
  return seen;
}

// ---------- applying data ----------

export function applyEvent(kind: EventKind, data: unknown): void {
  if (!data || typeof data !== "object") return;
  switch (kind) {
    case "activity":
      upsertActivity(data as Activity);
      break;
    case "message": {
      const m = data as Message;
      if (m.card && typeof m.card === "object") upsertCard(m.card);
      if (m.episode) addMessages(m.episode, [m]);
      break;
    }
    case "card":
      upsertCard(data as Card);
      break;
    case "cost":
      applyCost(data as Record<string, unknown>);
      break;
    case "episode":
      upsertEpisode(data as Episode);
      break;
  }
}

function withState(s: UiState, change: (st: State) => Partial<State>): Partial<UiState> {
  if (!s.state) return {};
  return { state: { ...s.state, ...change(s.state) } };
}

let refreshTimer: ReturnType<typeof setTimeout> | undefined;

/** Fetch the state again soon (several events in a row cause one fetch). */
function refreshSoon(): void {
  if (refreshTimer) return;
  refreshTimer = setTimeout(() => {
    refreshTimer = undefined;
    api
      .state()
      .then((state) => setUi((s) => ({ state, seen: stamp(state.activity, s.seen) })))
      .catch(() => undefined);
  }, 300);
}

export function upsertActivity(a: Activity): void {
  const known = getUi().state?.activity.some((x) => x.job === a.job);
  // A partial update about a job this screen has not seen yet: fetch the full rows instead of guessing.
  if (!known && (typeof a.identity !== "string" || typeof a.doing !== "string")) {
    refreshSoon();
    return;
  }
  setUi((s) => ({
    ...withState(s, (st) => {
      const i = st.activity.findIndex((x) => x.job === a.job);
      const activity = i < 0 ? [a, ...st.activity] : st.activity.map((x) => (x.job === a.job ? { ...x, ...a } : x));
      return { activity };
    }),
    seen: { ...s.seen, [a.job]: Date.now() },
  }));
}

export function upsertEpisode(e: Episode, first = false): void {
  if (e.id === ONBOARDING) return;
  setUi((s) =>
    withState(s, (st) => {
      const i = st.episodes.findIndex((x) => x.id === e.id);
      if (i < 0) return { episodes: first ? [e, ...st.episodes] : [...st.episodes, e] };
      return { episodes: st.episodes.map((x) => (x.id === e.id ? { ...x, ...e } : x)) };
    }),
  );
}

export function upsertCard(c: Card): void {
  setUi((s) => {
    const prev = s.cards[c.id];
    const merged: Card = prev ? { ...prev, ...c } : c;
    let delta = 0;
    if (prev?.status === "open" && merged.status !== "open") delta = -1;
    if (prev?.status !== "open" && merged.status === "open") delta = 1;
    return {
      cards: { ...s.cards, [c.id]: merged },
      ...(delta && merged.episode
        ? withState(s, (st) => ({
            episodes: st.episodes.map((x) =>
              x.id === merged.episode ? { ...x, open_cards: Math.max(0, x.open_cards + delta) } : x,
            ),
          }))
        : {}),
    };
  });
}

export function addMessages(episode: string, list: Message[]): void {
  if (!list.length) return;
  for (const m of list) if (m.card && typeof m.card === "object") upsertCard(m.card);
  setUi((s) => {
    const t = s.threads[episode];
    if (!t) return {};
    const byId = new Map(t.messages.map((m) => [m.id, m]));
    for (const m of list) byId.set(m.id, { ...byId.get(m.id), ...m });
    const messages = [...byId.values()].sort((a, b) => a.id - b.id);
    return { threads: { ...s.threads, [episode]: { ...t, messages } } };
  });
}

function applyCost(data: Record<string, unknown>): void {
  setUi((s) =>
    withState(s, (st) => {
      if (typeof data.month_usd === "number") return { money: { ...st.money, ...(data as unknown as Money) } };
      const amount = typeof data.amount_usd === "number" ? data.amount_usd : 0;
      if (!amount) return {};
      const ep = typeof data.episode === "string" ? data.episode : null;
      const money: Money = {
        ...st.money,
        today_usd: st.money.today_usd + amount,
        month_usd: st.money.month_usd + amount,
        episode_usd: ep
          ? { ...st.money.episode_usd, [ep]: (st.money.episode_usd[ep] ?? 0) + amount }
          : st.money.episode_usd,
      };
      return { money };
    }),
  );
}

// ---------- chats ----------

function setThread(id: string, t: Thread): void {
  setUi((s) => ({ threads: { ...s.threads, [id]: t } }));
}

export async function loadThread(id: string, force = false): Promise<void> {
  const t = getUi().threads[id];
  if (t && !force && t.status !== "error") return;
  setThread(id, { status: "loading", error: null, messages: t?.messages ?? [] });
  if (id !== ONBOARDING && !getUi().details[id]) {
    api
      .episode(id)
      .then((d) => setUi((s) => ({ details: { ...s.details, [id]: d } })))
      .catch(() => undefined);
  }
  try {
    const [messages, cards] = await Promise.all([api.messages(id), api.cards(id)]);
    for (const c of cards) upsertCard(c);
    setThread(id, { status: "ready", error: null, messages: [] });
    addMessages(id, messages);
  } catch (e) {
    setThread(id, { status: "error", error: messageOf(e), messages: t?.messages ?? [] });
  }
}

/** Where a sentence from the composer goes, given the open view. null: it starts a new episode. */
export function composerTarget(s: UiState = getUi()): string | null {
  const v = s.view;
  if (v.kind === "episode") return v.id;
  if (s.state && !s.state.app.onboarded) return ONBOARDING;
  if (v.kind === "new") return null;
  return s.lastEpisode;
}

/** Sends one sentence. Throws on failure, so the composer keeps the text. */
export async function send(text: string): Promise<void> {
  const target = composerTarget();
  if (!target) {
    const ep = await api.createEpisode(text);
    upsertEpisode(ep, true);
    navigate({ kind: "episode", id: ep.id });
    await loadThread(ep.id, true);
    return;
  }
  const msg = await api.say(target, text);
  const v = getUi().view;
  if (v.kind !== "episode" || v.id !== target) navigate({ kind: "episode", id: target });
  addMessages(target, [msg]);
}

/** Accepts a card. Throws on failure, so the card can show the error inline. */
export async function accept(card: Card, choice?: number): Promise<void> {
  const result = await api.accept(card.id, choice);
  upsertCard({ ...card, choice: choice ?? null, ...result, status: result?.status ?? "accepted" });
}

/**
 * Declines a card with the user's words. Used only where the one button means "not this way": a spend card with
 * "On this machine" chosen. Accepting a spend card means "rent", so the local way must never call accept.
 */
export async function decline(card: Card, reason: string): Promise<void> {
  const result = await api.decline(card.id, reason);
  upsertCard({ ...card, ...result, status: result?.status ?? "declined" });
}

let uploadSeq = 0;

export async function uploadFiles(files: File[]): Promise<void> {
  const v = getUi().view;
  const episode = v.kind === "episode" && v.id !== ONBOARDING ? v.id : null;
  if (!episode || !files.length) return;
  const lines = files.map((f) => ({
    key: `u${(uploadSeq += 1)}`,
    episode,
    name: f.name,
    size: f.size,
    status: "uploading" as const,
  }));
  setUi((s) => ({ uploads: [...s.uploads, ...lines] }));
  const keys = new Set(lines.map((l) => l.key));
  try {
    await api.upload(episode, files);
    setUi((s) => ({ uploads: s.uploads.map((u) => (keys.has(u.key) ? { ...u, status: "done" } : u)) }));
  } catch (e) {
    const error = messageOf(e);
    setUi((s) => ({
      uploads: s.uploads.map((u) => (keys.has(u.key) ? { ...u, status: "failed", error } : u)),
    }));
  }
}

export function setMenu(open: boolean): void {
  setUi({ menuOpen: open });
}

// ---------- keyboard and palette (DESIGN.md rule 15) ----------

export function setPalette(open: boolean): void {
  setUi({ paletteOpen: open, menuOpen: false });
}

export function setPrompter(open: boolean): void {
  setUi({ prompterOpen: open });
}

export function toggleSide(): void {
  if (typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(max-width: 759px)").matches) {
    setUi((s) => ({ menuOpen: !s.menuOpen }));
    return;
  }
  setUi((s) => ({ sideHidden: !s.sideHidden }));
}

export function toggleCrew(): void {
  setUi((s) => ({ crewHidden: !s.crewHidden }));
}

export function focusComposer(): void {
  const el = typeof document !== "undefined" ? document.getElementById("composer") : null;
  if (el instanceof HTMLTextAreaElement) el.focus();
}

/** Cmd+N: no episode selected, so the next sentence starts one. */
export function newEpisode(): void {
  navigate({ kind: "new" });
  setTimeout(focusComposer, 0);
}

/** Cmd+1 to Cmd+9. */
export function openEpisodeAt(index: number): boolean {
  const ep = getUi().state?.episodes[index];
  if (!ep) return false;
  navigate({ kind: "episode", id: ep.id });
  return true;
}

function scrollToSoon(selector: string): void {
  if (typeof document === "undefined") return;
  let tries = 0;
  const go = () => {
    const el = document.querySelector<HTMLElement>(selector);
    if (el) {
      const smooth = typeof window.matchMedia === "function" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView?.({ block: "center", behavior: smooth ? "smooth" : "auto" });
      return;
    }
    tries += 1;
    if (tries < 20) setTimeout(go, 100);
  };
  setTimeout(go, 0);
}

/** A waiting row in the Crew column jumps to the open card of its episode. Returns false when there is none. */
export function jumpToOpenCard(episode: string | null): boolean {
  if (!episode) return false;
  const card = Object.values(getUi().cards).find((c) => c.episode === episode && c.status === "open");
  if (!card) return false;
  const v = getUi().view;
  if (v.kind !== "episode" || v.id !== episode) navigate({ kind: "episode", id: episode });
  scrollToSoon(`[data-open-card="${card.id}"]`);
  return true;
}

/** A done step dot jumps to the card of that step in the chat, else to its first message. */
export function jumpToStep(step: string): void {
  if (typeof document === "undefined") return;
  const chat = "[data-testid='chat-scroll']";
  const cards = document.querySelectorAll<HTMLElement>(`${chat} [data-card-step="${step}"]`);
  const target = cards[cards.length - 1] ?? document.querySelector<HTMLElement>(`${chat} [data-step="${step}"]`);
  if (!target) return;
  const smooth = typeof window.matchMedia === "function" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView?.({ block: "center", behavior: smooth ? "smooth" : "auto" });
}
