// The episode view (DESIGN.md rule 2): media first. The title with the episode's facts and its ten steps, then the
// thumbnail variants, the cut, the 3D scenes and the rented GPU; the crew chat is a slim column on the right with the
// working tiles on top and the composer at the bottom. The onboarding chat and "New episode" use the main column.
import { Badge } from "@astryxdesign/core/Badge";
import { useEffect, useState, type CSSProperties } from "react";
import { api } from "../api/client";
import { ONBOARDING, type Card, type ImportedFiles, type Step } from "../api/types";
import { ErrorLine, Loading } from "../components/bits";
import { ChatPane, useFirstStart } from "../components/ChatPane";
import { Composer } from "../components/Composer";
import { MoneyLine, WorkingHint, WorkingList } from "../components/Crew";
import { ConnectEngine } from "../components/ConnectEngine";
import { ago, clock, episodeNumber } from "../lib/format";
import { jumpToStep, messageOf } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { Avatar, SlateFigure } from "../slate/Slate";
import { EpisodeMediaPanels } from "./EpisodeMedia";

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
 * The steps as segments (rule 2): done segments are filled and jump to their card in the chat, the current one is the
 * accent, open ones are faint. For screen readers it stays a list of the steps with aria-current="step".
 */
export function StepStrip({ steps, current, cards }: { steps: Step[]; current: string | undefined; cards: Card[] }) {
  const index = steps.findIndex((s) => s.id === current);
  const now = index >= 0 ? steps[index] : undefined;
  if (!steps.length) return <div className="stages" />;
  const next = now ? steps.slice(index + 1).filter((s) => s.status !== "skipped").slice(0, 2) : [];
  return (
    <div className="stages" style={{ "--n": steps.length } as CSSProperties}>
      {now ? (
        <p className="stage-text">
          Step <b>{`${now.n} of ${steps.length} · ${now.label}`}</b>
          {next.length ? <span className="stage-next">, then {next.map((s) => s.label.toLowerCase()).join(" and ")}</span> : null}
        </p>
      ) : null}
      <ol aria-label="Steps" className="segs">
        {steps.map((s, i) => {
          const isNow = i === index;
          const cls = ["seg", isNow ? "now" : s.status].join(" ");
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
    </div>
  );
}

function formatWords(format: string | undefined, short: boolean): string | null {
  if (short || format === "portrait") return "Short, 9:16";
  if (format === "landscape" || !format) return "Long video, 16:9";
  return format;
}

function EpisodeHead({ id }: { id: string }) {
  const episode = useUi((s) => s.state?.episodes.find((e) => e.id === id));
  const detail = useUi((s) => s.details[id]);
  const cardsById = useUi((s) => s.cards);
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const team = useUi((s) => s.state?.team);
  const steps = episode?.steps ?? detail?.steps ?? EMPTY;
  const cards = Object.values(cardsById).filter((c) => c.episode === id);
  const title = episode?.title ?? detail?.title ?? id;
  const n = episodeNumber(id);
  const short = (episode?.kind ?? detail?.kind) === "short";
  const seconds = episode?.seconds ?? detail?.seconds;
  const facts = [
    short ? null : n ? `Episode ${n}` : null,
    formatWords(detail?.project?.format, short),
    typeof seconds === "number" ? `${short ? "Clip" : "Cut"} ${clock(seconds)}` : null,
    detail?.project?.created ? `Started ${ago(detail.project.created)}` : null,
  ].filter((x): x is string => Boolean(x));
  const crew = [...new Set(activity.filter((a) => a.episode === id && a.status !== "done" && a.status !== "failed" && a.status !== "cancelled").map((a) => a.identity))];
  return (
    <header className="ep-head">
      <div className="ep-title">
        <h1 className="one-line" title={title}>
          {title}
        </h1>
        {facts.length ? (
          <div className="ep-facts">
            {facts.map((f) => (
              <Badge key={f} variant="neutral" label={f} className="chip" />
            ))}
          </div>
        ) : null}
      </div>
      <StepStrip steps={steps} current={episode?.step ?? detail?.step} cards={cards} />
      {crew.length ? (
        <span className="stack" aria-hidden="true">
          {crew.slice(0, 4).map((who) => (
            <Avatar key={who} who={team?.find((t) => t.id === who) ?? { id: who }} size="crew" />
          ))}
        </span>
      ) : null}
    </header>
  );
}

/** The crew chat column: who works now, the money line, the transcript, the composer. */
function CrewChat({ id }: { id: string }) {
  return (
    <section className="chatcol" aria-labelledby="chat-heading">
      <header className="chat-head">
        <h2 id="chat-heading">Crew chat</h2>
        <WorkingHint episode={id} />
      </header>
      <div className="chat-work">
        <WorkingList shape="chat" episode={id} />
      </div>
      <div className="chat-money">
        <MoneyLine episode={id} />
      </div>
      <ChatPane id={id} empty="Say an idea below, or ask the Scout for three." />
      <div className="chat-dock">
        <Composer />
      </div>
    </section>
  );
}

function ImportedMaterial({ id }: { id: string }) {
  const [folder, setFolder] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<ImportedFiles | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    api.importedFiles(id, folder, offset)
      .then((result) => live && setData(result))
      .catch((reason) => live && setError(messageOf(reason)));
    return () => { live = false; };
  }, [id, folder, offset, retry]);
  const open = (path: string) => { setFolder(path); setOffset(0); };
  return (
    <div>
      <p className="meta">Earlier material is reference only. Opening a file does not start work.</p>
      {folder ? <button type="button" className="text-button" onClick={() => open(folder.split("/").slice(0, -1).join("/"))}>Back to parent folder</button> : null}
      <p className="meta">{folder || "Imported studio files"}</p>
      {error ? <ErrorLine text={error} onRetry={() => setRetry(retry + 1)} /> : !data ? <Loading label="Loading imported files" /> : (
        <>
          {data.total === 0 ? <p className="meta">No files in this folder.</p> : null}
          <ul>
            {data.entries.map((entry) => (
              <li key={entry.path}>
                {entry.directory ? <button type="button" className="text-button" onClick={() => open(entry.path)}>{entry.name}/</button> : (
                  <a href={`${api.fileUrl(id, `legacy/${entry.path}`)}?download=true`} download>{entry.name}</a>
                )}
              </li>
            ))}
          </ul>
          {offset > 0 ? <button type="button" className="text-button" onClick={() => setOffset(Math.max(0, offset - 100))}>Previous files</button> : null}
          {offset + data.entries.length < data.total ? <button type="button" className="text-button" onClick={() => setOffset(offset + 100)}>Next files</button> : null}
        </>
      )}
    </div>
  );
}

function EpisodeMaterial({ id }: { id: string }) {
  const detail = useUi((state) => state.details[id]);
  const [showImported, setShowImported] = useState(false);
  const documents = detail?.files.filter((file) => file.path.startsWith("brief/")) ?? [];
  if (!documents.length && !detail?.project.legacy) return null;
  return (
    <section className="section" aria-label="Scripts and reference files">
      <h2>Scripts and reference files</h2>
      <ul>
        {documents.map((file) => <li key={file.path}><a href={`${api.fileUrl(id, file.path)}?download=true`} download>{file.path.slice(6)}</a></li>)}
      </ul>
      {detail?.project.legacy ? (
        <>
          <button type="button" className="text-button" aria-expanded={showImported} onClick={() => setShowImported(!showImported)}>
            {showImported ? "Hide imported files" : "Browse imported files"}
          </button>
          {showImported ? <ImportedMaterial id={id} /> : null}
        </>
      ) : null}
    </section>
  );
}

export function EpisodeView({ id }: { id: string }) {
  const title = useUi((s) => s.state?.episodes.find((e) => e.id === id)?.title ?? s.details[id]?.title ?? id);
  return (
    <>
      <main className="main media-main" aria-label={title}>
        <div className="media-scroll">
          <EpisodeHead id={id} />
          <EpisodeMediaPanels key={id} id={id} />
          <EpisodeMaterial key={`files-${id}`} id={id} />
        </div>
      </main>
      <CrewChat id={id} />
    </>
  );
}

/** The composer floating at the bottom of the main column (rule 7); on the first start it sits under the sentence. */
export function Dock({ centered, narrow }: { centered?: boolean; narrow?: boolean }) {
  const cls = ["dock", narrow ? "narrow" : null, centered ? "centered" : null].filter(Boolean).join(" ");
  return (
    <div className={cls}>
      <Composer />
    </div>
  );
}

/** The first start (rule 3): no top bar actions, Slate waving, one sentence; the composer floats below it. Until
 *  Claude is connected, the first step is "Connect Claude". */
function Welcome() {
  const engineOk = useUi((s) => s.state?.app.engine_ok ?? true);
  if (!engineOk) {
    return (
      <div className="hero">
        <span className="hero-mark">
          <SlateFigure state="wave" size={120} />
        </span>
        <h1>Connect Claude first.</h1>
        <p>Crewcut runs on your own Claude plan. Sign in once, then paste your links.</p>
        <ConnectEngine />
      </div>
    );
  }
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

/** The onboarding chat in the main column: the Brand identity reads the links and builds the style pack. */
export function OnboardingView() {
  const firstStart = useFirstStart(ONBOARDING);
  const engineOk = useUi((s) => s.state?.app.engine_ok ?? true);
  const head = firstStart ? null : (
    <div className="page-head">
      <h1 className="one-line">Set up your style</h1>
      <p className="sub">The Brand identity reads your links and builds your profile. Nothing else to fill in.</p>
      {engineOk ? null : <ConnectEngine />}
    </div>
  );
  return (
    <main className={firstStart ? "main chat-main first-start" : "main chat-main"} aria-label="Set up your style">
      {firstStart ? <Welcome /> : null}
      <ChatPane id={ONBOARDING} head={head} />
      <Dock narrow centered={firstStart} />
    </main>
  );
}

export function NewEpisodeView() {
  const count = useUi((s) => s.state?.episodes.length ?? 0);
  return (
    <main className="main chat-main" aria-label="New episode">
      <div className="chat-scroll">
        <div className="thread">
          <div className="page-head">
            <h1 className="one-line">New episode</h1>
            <p className="sub">One sentence is enough. The Showrunner starts from it.</p>
          </div>
          <div className="chat">
            <div className="chat-empty">
              <SlateFigure size={96} />
              <p>{count ? "Say an idea below." : "No episodes yet. Say an idea below."}</p>
            </div>
          </div>
        </div>
      </div>
      <Dock />
    </main>
  );
}
