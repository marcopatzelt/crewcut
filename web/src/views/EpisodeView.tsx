// The Chat place: the toolbar with the ten steps, the large title, the transcript with cards and previews.
// The transcript runs under the toolbar and under the composer (DESIGN.md rule 7).
import { AlertCircle, Check, LoaderCircle } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type DragEvent } from "react";
import { ONBOARDING, type Card, type Episode, type Identity, type Message, type Step } from "../api/types";
import { ErrorLine, Facts, identityOf, Loading, Media } from "../components/bits";
import { Avatar, SlateFigure } from "../slate/Slate";
import { CardItem } from "../components/CardView";
import { ExchangeLine } from "../components/Exchange";
import { PrompterButton, PrompterPopover } from "../components/PrompterPopover";
import { LargeTitle, Toolbar, useScrollChrome } from "../components/Toolbar";
import { ago, bytes, episodeNumber, paragraphs } from "../lib/format";
import { jumpToStep, loadThread, uploadFiles } from "../store/actions";
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

const STATUS_WORD: Record<string, string> = {
  done: "done",
  working: "working",
  waiting: "waiting for your yes",
  open: "not started",
  skipped: "switched off",
};

function stepTip(s: Step, cards: Card[]): string {
  const approved = cards
    .filter((c) => c.step === s.id && c.status === "accepted" && c.decided_at)
    .sort((a, b) => Date.parse(b.decided_at ?? "") - Date.parse(a.decided_at ?? ""))[0];
  if (s.status === "done" && approved?.decided_at) return `${s.label} · approved ${ago(approved.decided_at)}`;
  return `${s.label} · ${STATUS_WORD[s.status] ?? s.status}`;
}

/**
 * The ten steps as dots on a line (rule 2): done dots are filled and jump to their card, the current one is the accent
 * dot with a soft ring, open ones are rings. The accent dot moves on with --spring-soft. For screen readers it stays a
 * list of ten items. In a narrow toolbar only "6 of 10 · Edit" and a thin capsule remain.
 */
export function StepStrip({ steps, current, cards }: { steps: Step[]; current: string | undefined; cards: Card[] }) {
  const index = steps.findIndex((s) => s.id === current);
  const now = index >= 0 ? steps[index] : undefined;
  const done = steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  if (!steps.length) return <div className="strip" />;
  return (
    <div className="strip">
      <div className="dots" style={{ "--now": Math.max(0, index) } as CSSProperties}>
        <ol aria-label="Steps">
          {steps.map((s, i) => {
            const isNow = i === index;
            const cls = ["step", isNow ? "now" : s.status].join(" ");
            const tip = stepTip(s, cards);
            const words = `${s.n} ${s.label}, ${isNow ? "current step" : STATUS_WORD[s.status] ?? s.status}`;
            return (
              <li key={s.id} className={cls} aria-current={isNow ? "step" : undefined}>
                {s.status === "done" && !isNow ? (
                  <button
                    type="button"
                    className="tip"
                    data-tip={tip}
                    aria-label={`${words}. Show it in the chat.`}
                    onClick={() => jumpToStep(s.id)}
                  >
                    <i aria-hidden="true" />
                  </button>
                ) : (
                  <span className="tip" data-tip={tip}>
                    <i aria-hidden="true" />
                    <span className="sr-only">{words}</span>
                  </span>
                )}
              </li>
            );
          })}
        </ol>
        {now ? <span className="now-dot" aria-hidden="true" /> : null}
      </div>
      {now ? (
        <div className="strip-text">
          <span className="one-line">
            {now.n} of {steps.length} · {now.label}
          </span>
          <span className="capsule" aria-hidden="true">
            <i style={{ transform: `scaleX(${done / steps.length})` }} />
          </span>
        </div>
      ) : null}
    </div>
  );
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
        {m.preview || m.facts?.length ? (
          <div className={m.preview && m.facts?.length ? "preview" : "preview solo"}>
            {m.preview ? <Media episode={episode} path={m.preview} label={`Preview from ${who.name}`} /> : null}
            {m.facts?.length ? <Facts facts={m.facts} /> : null}
          </div>
        ) : null}
      </div>
    </article>
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

/** The first start (rule 3, DESIGN plan 6.14): no toolbar, the mark, one sentence; the composer floats below it. */
function Onboarding() {
  return (
    <div className="hero">
      <span className="hero-mark">
        <SlateFigure state="wave" size={120} />
      </span>
      <h1>Paste your links.</h1>
      <p>Website, YouTube channel, socials. The crew reads the rest.</p>
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

export function EpisodeView({ id }: { id: string }) {
  const thread = useUi((s) => s.threads[id]);
  const episode = useUi((s) => s.state?.episodes.find((e) => e.id === id));
  const detail = useUi((s) => s.details[id]);
  const team = useUi((s) => s.state?.team);
  const cardsById = useUi((s) => s.cards);
  const uploads = useUi((s) => s.uploads);
  const steps = episode?.steps ?? detail?.steps ?? EMPTY;
  const { scroller, large, scrolled, showTitle, update } = useScrollChrome();
  const stick = useRef(true);
  const [dropping, setDropping] = useState(false);

  const messages = thread?.messages ?? EMPTY;
  const cards = Object.values(cardsById).filter((c) => c.episode === id);
  const byId = new Map(cards.map((c) => [c.id, c]));
  const items = timeline(messages, cards);
  const mine = uploads.filter((u) => u.episode === id);
  const canDrop = id !== ONBOARDING;
  const isFresh = useFresh(thread?.status === "ready", items.map((i) => i.key), id);
  const firstStart = id === ONBOARDING && thread?.status === "ready" && items.length === 0 && mine.length === 0;

  // Stay at the bottom while the user is there; leave the scroll alone when they read further up.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
    update();
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
      if (stick.current) el.scrollTop = el.scrollHeight;
      update();
    });
    ro.observe(content);
    ro.observe(el);
    return () => ro.disconnect();
  }, [thread?.status, id, firstStart]);

  function onScroll() {
    const el = scroller.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    update();
  }

  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");

  function onDrop(e: DragEvent) {
    if (!canDrop || !hasFiles(e)) return;
    e.preventDefault();
    setDropping(false);
    stick.current = true;
    void uploadFiles(Array.from(e.dataTransfer.files));
  }

  const onboardingChat = id === ONBOARDING;
  const title = onboardingChat ? "Set up your style" : episode?.title ?? detail?.title ?? id;
  const n = episodeNumber(id);
  const sub = onboardingChat
    ? "The Brand identity reads your links and builds your profile. Nothing else to fill in."
    : [
        n ? `Episode ${n}` : null,
        detail?.project?.format ?? null,
        detail?.project?.created ? `started ${ago(detail.project.created)}` : null,
      ]
        .filter(Boolean)
        .join(" · ");

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
        {items.length === 0 && mine.length === 0 && !onboardingChat ? (
          <div className="chat-empty">
            <SlateFigure size={96} />
            <p>Say an idea below, or ask the Scout for three.</p>
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

  if (firstStart) {
    return (
      <section className="view first-start" aria-label="Set up your style">
        <div className="scroll" ref={scroller} data-testid="chat-scroll">
          <Onboarding />
          {body}
        </div>
      </section>
    );
  }

  return (
    <section className="view" aria-label={onboardingChat ? title : episode?.title ?? "Chat"}>
      <Toolbar
        title={title}
        sub={sub}
        showTitle={showTitle}
        scrolled={scrolled}
        actions={onboardingChat ? null : <PrompterButton />}
      >
        {onboardingChat ? <div className="strip" /> : <StepStrip steps={steps} current={episode?.step ?? detail?.step} cards={cards} />}
      </Toolbar>
      {onboardingChat ? null : <PrompterPopover episode={id} />}
      <div
        ref={scroller}
        className="scroll"
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
          <LargeTitle innerRef={large} title={title} sub={sub || undefined} />
          {body}
        </div>
      </div>
    </section>
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

export function NewEpisodeView() {
  const count = useUi((s) => s.state?.episodes.length ?? 0);
  const { scroller, large, scrolled, showTitle, update } = useScrollChrome();
  return (
    <section className="view" aria-label="New episode">
      <Toolbar title="New episode" showTitle={showTitle} scrolled={scrolled}>
        <div className="strip" />
      </Toolbar>
      <div className="scroll" ref={scroller} onScroll={update}>
        <div className="thread">
          <LargeTitle innerRef={large} title="New episode" sub="One sentence is enough. The Showrunner starts from it." />
          <div className="chat">
            <div className="chat-empty">
              <SlateFigure size={96} />
              <p>{count ? "Say an idea below." : "No episodes yet. Say an idea below."}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
