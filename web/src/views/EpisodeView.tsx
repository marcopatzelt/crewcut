// The Chat place: the episode header with the ten steps, the transcript with cards and previews.
import { AlertCircle, Check, LoaderCircle } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type DragEvent } from "react";
import { ONBOARDING, type Card, type Episode, type Identity, type Message } from "../api/types";
import { ErrorLine, Facts, identityOf, Loading, Mark, Media, StepBar } from "../components/bits";
import { CardItem } from "../components/CardView";
import { PrompterButton } from "../components/PrompterPopover";
import { ago, bytes, episodeNumber, paragraphs } from "../lib/format";
import { loadThread, uploadFiles } from "../store/actions";
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

function Header({ episode, id }: { episode: Episode | undefined; id: string }) {
  const detail = useUi((s) => s.details[id]);
  if (id === ONBOARDING) {
    return (
      <header className="head plain">
        <h1>Set up your style</h1>
        <p className="sub">The Brand identity reads your links and builds your profile. Nothing else to fill in.</p>
      </header>
    );
  }
  const title = episode?.title ?? detail?.title ?? id;
  const steps = episode?.steps ?? detail?.steps ?? [];
  const n = episodeNumber(id);
  const sub = [
    n ? `Episode ${n}` : null,
    detail?.project?.format ?? null,
    detail?.project?.created ? `started ${ago(detail.project.created)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const now = steps.find((s) => s.id === (episode?.step ?? detail?.step));
  return (
    <header className="head">
      <div className="head-row">
        <div className="head-text">
          <h1 className="one-line" title={title}>
            {title}
          </h1>
          <p className="sub">{sub || " "}</p>
        </div>
        <PrompterButton episode={id} />
      </div>
      <ol className="steps" aria-label="Steps">
        {steps.map((s) => {
          const cls = s.id === now?.id ? "step now" : `step ${s.status}`;
          return (
            <li key={s.id} className={cls} title={`${s.n} ${s.label}: ${s.status}`} aria-current={s.id === now?.id ? "step" : undefined}>
              <span className="n">{s.n}</span>
              {s.label}
            </li>
          );
        })}
      </ol>
      {now ? (
        <div className="steps-compact meta">
          Step {now.n} of {steps.length} · {now.label}
          <StepBar steps={steps} />
        </div>
      ) : null}
    </header>
  );
}

function IdentityMessage({ m, team, steps, episode }: { m: Message; team: Identity[] | undefined; steps: Episode["steps"]; episode: string }) {
  const who = identityOf(team, m.author);
  const step = m.step ? steps.find((s) => s.id === m.step) : undefined;
  return (
    <article className="msg" aria-label={`${who.name}`}>
      <Mark mark={who.mark} />
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

function EmptyChat({ id, onboarding }: { id: string; onboarding: boolean }) {
  if (id === ONBOARDING || onboarding) {
    return (
      <div className="chat-empty">
        <strong>Paste your links.</strong>
        Your channel, your website, or a video you like.
      </div>
    );
  }
  return <div className="chat-empty">Nothing here yet. The Showrunner writes first.</div>;
}

export function EpisodeView({ id }: { id: string }) {
  const thread = useUi((s) => s.threads[id]);
  const episode = useUi((s) => s.state?.episodes.find((e) => e.id === id));
  const team = useUi((s) => s.state?.team);
  const cardsById = useUi((s) => s.cards);
  const uploads = useUi((s) => s.uploads);
  const onboarding = useUi((s) => s.state !== null && !s.state.app.onboarded);
  const detailSteps = useUi((s) => s.details[id]?.steps);
  const steps = episode?.steps ?? detailSteps ?? EMPTY;
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [faded, setFaded] = useState(false);
  const [dropping, setDropping] = useState(false);

  const messages = thread?.messages ?? EMPTY;
  const cards = Object.values(cardsById).filter((c) => c.episode === id);
  const byId = new Map(cards.map((c) => [c.id, c]));
  const items = timeline(messages, cards);
  const mine = uploads.filter((u) => u.episode === id);
  const canDrop = id !== ONBOARDING;

  // Stay at the bottom while the user is there; leave the scroll alone when they read further up.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
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
    });
    ro.observe(content);
    return () => ro.disconnect();
  }, [thread?.status, id]);

  function onScroll() {
    const el = scroller.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setFaded(el.scrollTop > 4);
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
        {items.length === 0 && mine.length === 0 ? <EmptyChat id={id} onboarding={onboarding} /> : null}
        {items.map((it) => {
          if (it.card) return <CardItem key={it.key} card={it.card} team={team} steps={steps} />;
          const m = it.message as Message;
          const cardId = typeof m.card === "number" ? m.card : m.card?.id;
          const card = typeof cardId === "number" ? byId.get(cardId) : undefined;
          return (
            <MessageBlock key={it.key} m={m} card={card} team={team} steps={steps} episode={id} />
          );
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
    <section className="view" aria-label={episode?.title ?? "Chat"}>
      <Header episode={episode} id={id} />
      <div
        ref={scroller}
        className={faded ? "scroll faded" : "scroll"}
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
        {body}
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
}: {
  m: Message;
  card: Card | undefined;
  team: Identity[] | undefined;
  steps: Episode["steps"];
  episode: string;
}) {
  // The server posts a card together with a message that only repeats its title: show the card alone.
  const onlyTitle = card && m.text.trim() === card.title.trim() && !m.cite;
  return (
    <>
      {onlyTitle ? null : m.author === "user" ? (
        <div className="user">{m.text}</div>
      ) : (
        <IdentityMessage m={m} team={team} steps={steps} episode={episode} />
      )}
      {card ? <CardItem card={card} team={team} steps={steps} /> : null}
    </>
  );
}

export function NewEpisodeView() {
  const count = useUi((s) => s.state?.episodes.length ?? 0);
  return (
    <section className="view" aria-label="New episode">
      <header className="head plain">
        <h1>New episode</h1>
        <p className="sub">One sentence is enough. The Showrunner starts from it.</p>
      </header>
      <div className="scroll">
        <div className="chat">
          <div className="chat-empty">{count ? "Say an idea below." : "No episodes yet. Say an idea below."}</div>
        </div>
      </div>
    </section>
  );
}
