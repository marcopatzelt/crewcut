// The transcript of one episode chat: messages, cards and previews, crew exchanges, uploads (DESIGN.md rules 12, 13).
// Used in the slim crew chat column of the episode view and in the onboarding chat. Files dropped on it upload into
// the episode. It stays at the bottom while the user is there and leaves the scroll alone when they read further up.
import { AlertCircle, Check, LoaderCircle } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { CHANNEL, ONBOARDING, type Card, type Episode, type Identity, type Message } from "../api/types";
import { ErrorLine, Facts, identityOf, Loading, Media } from "./bits";
import { Avatar, SlateFigure } from "../slate/Slate";
import { CardItem } from "./CardView";
import { ExchangeLine } from "./Exchange";
import { ago, bytes, paragraphs } from "../lib/format";
import { loadThread, uploadFiles, viewToHash } from "../store/actions";
import { EMPTY, useUi, type UploadLine } from "../store/store";

type Item = { at: string; key: string; message?: Message; card?: Card };

function timeline(messages: Message[], cards: Card[]): Item[] {
  const referenced = new Set<number>();
  const items: Item[] = [];
  for (const m of messages) {
    const id = typeof m.card === "number" ? m.card : m.card?.id;
    if (typeof id === "number") referenced.add(id);
    items.push({ at: m.at, key: `m${m.id}`, message: m });
  }
  for (const c of cards) {
    if (!referenced.has(c.id)) items.push({ at: c.created, key: `c${c.id}`, card: c });
  }
  return items.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
}

function IdentityMessage({
  m,
  team,
  steps,
  episode,
  fresh,
}: {
  m: Message;
  team: Identity[] | undefined;
  steps: Episode["steps"];
  episode: string;
  fresh: boolean;
}) {
  const who = identityOf(team, m.author);
  const episodes = useUi((state) => state.state?.episodes ?? EMPTY);
  const linked = episode === CHANNEL ? episodes.filter((item) =>
    m.facts?.some((fact) => fact.label === "episode" && fact.value === item.id) ||
    m.text.includes(item.id) || (item.title.length > 0 && m.text.includes(item.title)),
  ).slice(0, 3) : [];
  const facts = m.facts?.filter((fact) => fact.label !== "episode" || !linked.some((item) => item.id === fact.value));
  const step = m.step ? steps.find((s) => s.id === m.step) : undefined;
  return (
    <article className={fresh ? "msg is-new" : "msg"} aria-label={`${who.name}`} data-step={m.step ?? undefined}>
      <Avatar who={who} />
      <div className="msg-main">
        <div className="who">
          <b>{who.name}</b>
          {[step?.label, ago(m.at)].filter(Boolean).join(" · ")}
        </div>
        <div className="txt">
          {paragraphs(m.text).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
        {m.cite ? <p className="cite">{m.cite}</p> : null}
        {linked.length ? <nav className="channel-links" aria-label="Episodes in this reply">
          {linked.map((item) => <a key={item.id} href={viewToHash({ kind: "episode", id: item.id })}>{item.title}</a>)}
        </nav> : null}
        {m.preview || facts?.length ? (
          <div className={m.preview && facts?.length ? "preview" : "preview solo"}>
            {m.preview ? <Media episode={episode} path={m.preview} label={`Preview from ${who.name}`} /> : null}
            {facts?.length ? <Facts facts={facts} /> : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function MessageBlock({
  m,
  card,
  team,
  steps,
  episode,
  fresh,
}: {
  m: Message;
  card: Card | undefined;
  team: Identity[] | undefined;
  steps: Episode["steps"];
  episode: string;
  fresh: boolean;
}) {
  // The server posts a card together with a message that only repeats its title: show the card alone.
  const onlyTitle = card && m.text.trim() === card.title.trim() && !m.cite;
  return (
    <>
      {onlyTitle ? null : m.exchange?.messages?.length ? (
        <ExchangeLine m={m} exchange={m.exchange} team={team} />
      ) : m.author === "user" ? (
        <div className={fresh ? "user is-new" : "user"}>{m.text}</div>
      ) : (
        <IdentityMessage m={m} team={team} steps={steps} episode={episode} fresh={fresh} />
      )}
      {card ? <CardItem card={card} team={team} steps={steps} fresh={fresh} /> : null}
    </>
  );
}

function UploadItem({ u }: { u: UploadLine }) {
  const state =
    u.status === "uploading" ? "uploading" : u.status === "done" ? "in the inbox, the Editor takes it from here" : `couldn't upload. ${u.error ?? ""}`;
  return (
    <div className={u.status === "failed" ? "line-item failed" : "line-item"}>
      {u.status === "uploading" ? (
        <LoaderCircle size={14} className="spin" aria-hidden="true" />
      ) : u.status === "done" ? (
        <Check size={14} aria-hidden="true" />
      ) : (
        <AlertCircle size={14} aria-hidden="true" />
      )}
      <span className="one-line" title={u.name}>
        {u.name}
      </span>
      <span className="meta">
        {bytes(u.size)} · {state}
      </span>
    </div>
  );
}

/** Which items are new since the chat opened: only those animate in (rule 9). */
function useFresh(ready: boolean, keys: string[], id: string) {
  const known = useRef<Set<string> | null>(null);
  const opened = useRef(Date.now());
  useLayoutEffect(() => {
    known.current = null;
    opened.current = Date.now();
  }, [id]);
  useEffect(() => {
    if (ready && known.current === null) known.current = new Set(keys);
  });
  return (key: string, at: string) =>
    known.current !== null && !known.current.has(key) && Date.parse(at) > opened.current - 5000;
}

/** True when the onboarding chat has nothing in it yet: the first start. */
export function useFirstStart(id: string): boolean {
  return useUi(
    (s) =>
      id === ONBOARDING &&
      s.threads[ONBOARDING]?.status === "ready" &&
      (s.threads[ONBOARDING]?.messages.length ?? 0) === 0 &&
      !Object.values(s.cards).some((c) => c.episode === ONBOARDING) &&
      !s.uploads.some((u) => u.episode === ONBOARDING),
  );
}

export function ChatPane({ id, head, empty }: { id: string; head?: ReactNode; empty?: string }) {
  const thread = useUi((s) => s.threads[id]);
  const episode = useUi((s) => s.state?.episodes.find((e) => e.id === id));
  const detail = useUi((s) => s.details[id]);
  const team = useUi((s) => s.state?.team);
  const cardsById = useUi((s) => s.cards);
  const uploads = useUi((s) => s.uploads);
  const steps = episode?.steps ?? detail?.steps ?? EMPTY;
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [dropping, setDropping] = useState(false);

  const messages = thread?.messages ?? EMPTY;
  const cards = Object.values(cardsById).filter((c) => c.episode === id);
  const byId = new Map(cards.map((c) => [c.id, c]));
  const items = timeline(messages, cards);
  const mine = uploads.filter((u) => u.episode === id);
  const canDrop = id !== ONBOARDING && id !== CHANNEL;
  const isFresh = useFresh(thread?.status === "ready", items.map((i) => i.key), id);

  /** The open card when it is the newest item of the transcript, else null. */
  const lastOpenCard = (el: HTMLElement) => {
    const last = el.querySelector(".chat")?.lastElementChild;
    return last instanceof HTMLElement && last.matches("[data-open-card]") ? last : null;
  };

  /**
   * To the newest item. When that is an open card taller than the view, its top stays in view instead: the question
   * and its choices come before the button (rule 12).
   */
  const toEnd = () => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    const card = lastOpenCard(el);
    if (card) {
      const over = card.getBoundingClientRect().top - el.getBoundingClientRect().top - 12;
      if (over < 0) el.scrollTop += over;
    }
  };

  useLayoutEffect(() => {
    if (stick.current) toEnd();
  }, [items.length, mine.length, thread?.status, id]);

  useLayoutEffect(() => {
    stick.current = true;
  }, [id]);

  // Images and videos load after the first scroll; keep the bottom in view while the user is there.
  useEffect(() => {
    const el = scroller.current;
    const content = el?.firstElementChild;
    if (!el || !content || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      if (stick.current) toEnd();
    });
    ro.observe(content);
    ro.observe(el);
    return () => ro.disconnect();
  }, [thread?.status, id]);

  function onScroll() {
    const el = scroller.current;
    if (!el) return;
    const card = lastOpenCard(el);
    const cardInView = card !== null && Math.abs(card.getBoundingClientRect().top - el.getBoundingClientRect().top - 12) < 4;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80 || cardInView;
  }

  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");

  function onDrop(e: DragEvent) {
    if (!canDrop || !hasFiles(e)) return;
    e.preventDefault();
    setDropping(false);
    stick.current = true;
    void uploadFiles(Array.from(e.dataTransfer.files));
  }

  let body;
  if (!thread || (thread.status === "loading" && !messages.length)) {
    body = <Loading label="Loading the chat" />;
  } else if (thread.status === "error" && !messages.length) {
    body = (
      <div className="center-state danger">
        <ErrorLine text={`Couldn't load the chat. ${thread.error ?? ""}`} onRetry={() => void loadThread(id, true)} />
      </div>
    );
  } else {
    body = (
      <div
        className={dropping ? "chat dropping" : "chat"}
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Chat"
        role="log"
      >
        {items.length === 0 && mine.length === 0 && empty ? (
          <div className="chat-empty">
            <SlateFigure size={88} />
            <p>{empty}</p>
          </div>
        ) : null}
        {items.map((it) => {
          const fresh = isFresh(it.key, it.at);
          if (it.card) return <CardItem key={it.key} card={it.card} team={team} steps={steps} fresh={fresh} />;
          const m = it.message as Message;
          const cardId = typeof m.card === "number" ? m.card : m.card?.id;
          const card = typeof cardId === "number" ? byId.get(cardId) : undefined;
          return <MessageBlock key={it.key} m={m} card={card} team={team} steps={steps} episode={id} fresh={fresh} />;
        })}
        {mine.map((u) => (
          <UploadItem key={u.key} u={u} />
        ))}
        {thread.status === "error" ? (
          <ErrorLine text={`Couldn't load new messages. ${thread.error ?? ""}`} onRetry={() => void loadThread(id, true)} />
        ) : null}
      </div>
    );
  }

  return (
    <div
      ref={scroller}
      className="chat-scroll"
      onScroll={onScroll}
      onDragOver={(e) => {
        if (!canDrop || !hasFiles(e)) return;
        e.preventDefault();
        setDropping(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDropping(false);
      }}
      onDrop={onDrop}
      data-testid="chat-scroll"
    >
      <div className="thread">
        {head}
        {body}
      </div>
    </div>
  );
}
