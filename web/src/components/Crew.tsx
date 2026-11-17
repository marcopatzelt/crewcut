// Who works on what right now, done today, and the money (DESIGN.md rules 1.5, 13, 14). Two shapes:
// - "rail": the right column of the home and the read-only views, each running job with its newest picture;
// - "chat": slim tiles on top of the episode's crew chat.
// A waiting row jumps to the open card of its episode; every other row opens the job's log.
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { useEffect, useRef, useState } from "react";
import type { Activity, Episode, Identity, Money } from "../api/types";
import { clock, countWord, sameDay, usd, usdShort } from "../lib/format";
import { jumpToOpenCard, navigate } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { identityOf } from "./bits";
import { Avatar } from "../slate/Slate";

const ACTIVE = new Set(["running", "waiting", "queued"]);
const ORDER: Record<string, number> = { running: 0, waiting: 1, queued: 2 };
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** Re-renders every second while work runs; otherwise nothing counts (rule 1.3). */
export function useTicker(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

/**
 * Rows that arrive after the column first showed slide in; the ones already there do not (rule 9). A job that moves
 * from "Working now" to "Done today" counts as arriving there.
 */
function useArrivals(ready: boolean, keys: string[]) {
  const known = useRef<Set<string> | null>(null);
  if (ready && known.current === null) known.current = new Set(keys);
  return (k: string) => known.current !== null && !known.current.has(k);
}

/** "Cut check v1" becomes "cut check v1" after a name; "API check" stays as it is. */
function lowerFirst(text: string): string {
  return /^[A-Z][a-z]/.test(text) ? text.charAt(0).toLowerCase() + text.slice(1) : text;
}

function elapsed(a: Activity, seenAt: number | undefined, now: number): number {
  if (a.status !== "running" || !seenAt) return a.seconds;
  return a.seconds + Math.max(0, (now - seenAt) / 1000);
}

function stepLabel(episodes: readonly Episode[], a: Activity): string {
  const ep = episodes.find((e) => e.id === a.episode);
  const step = ep?.steps.find((s) => s.id === a.step);
  return step ? `${step.n} ${step.label}` : a.step;
}

export type Shape = "rail" | "chat";

function JobRow({
  a,
  who,
  meta,
  seconds,
  fresh,
  hasCard,
  shape,
}: {
  a: Activity;
  who: Identity;
  meta: string;
  seconds: number;
  fresh: boolean;
  hasCard: boolean;
  shape: Shape;
}) {
  const running = a.status === "running";
  const doing = a.status === "queued" && !a.doing ? "Waiting for a free slot" : a.doing;
  const toCard = a.status === "waiting" && hasCard;
  const progress = typeof a.progress === "number" ? Math.min(1, Math.max(0, a.progress)) : null;
  const open = () => {
    if (toCard && jumpToOpenCard(a.episode)) return;
    navigate({ kind: "job", id: a.job });
  };
  const live = shape === "rail" && a.preview && ACTIVE.has(a.status);
  return (
    <div className={fresh ? "job-wrap is-new" : "job-wrap"}>
      <button
        type="button"
        className={`job job-${shape}`}
        data-job={a.job}
        onClick={open}
        aria-label={`${who.name}: ${doing}. ${meta}. ${toCard ? "Open the card." : "Open the log."}`}
      >
        {/* The key restarts the tick when the crew member reports a new step: Slate ticks when something happens. */}
        <Avatar
          key={`${a.status}:${doing}`}
          who={who}
          size={shape === "rail" ? "rail" : "crew"}
          state={running ? "working" : a.status === "waiting" ? "waiting" : "idle"}
        />
        <span className="job-main">
          <span className="job-who">
            <span className="job-name one-line">{who.name}</span>
            <span className="job-time">{clock(seconds)}</span>
          </span>
          <span className={shape === "rail" ? "job-doing" : "job-doing one-line"}>{doing}</span>
          {shape === "rail" ? <span className="job-meta one-line">{meta}</span> : null}
          {live ? (
            <span className="job-live">
              <img src={a.preview ?? ""} alt="" decoding="async" />
              <span className="glass-tag">
                {progress !== null ? `${Math.round(progress * 100)} %` : a.status === "waiting" ? "Waits for you" : "Draft"}
              </span>
            </span>
          ) : null}
          {running ? (
            <ProgressBar
              className="job-bar"
              label={`${who.name}: progress`}
              isLabelHidden
              value={progress !== null ? Math.round(progress * 100) : undefined}
              isIndeterminate={progress === null}
            />
          ) : null}
        </span>
        {running && a.cost_usd > 0 ? <span className="job-cost">{usd(a.cost_usd)}</span> : null}
      </button>
    </div>
  );
}

/** The engine is not logged in: one line with a --warn dot (rule 11). */
export function engineLine(engine: string): string {
  return engine === "claude"
    ? "Claude Code is not logged in. Run claude setup-token, put the value in .env and restart Crewcut."
    : `${engine} is not logged in. Run ${engine} login, put the value in .env and restart Crewcut.`;
}

function hintFor(active: Activity[], episode: string | null): string {
  if (!active.length) return "Nobody is working. Nothing is running, nothing costs money.";
  if (!episode) {
    const n = new Set(active.map((a) => a.identity)).size;
    return n === 1 ? "One of the crew is working." : `${countWord(n)} of the crew are working.`;
  }
  const here = new Set(active.filter((a) => a.episode === episode).map((a) => a.identity)).size;
  if (here === 0) return "Nobody is on this episode right now.";
  return here === 1 ? "One of the crew is on this episode." : `${countWord(here)} of the crew are on this episode.`;
}

/** The running, waiting and queued jobs, then "Done today". `episode` is the chat in view, if any. */
export function WorkingList({ shape, episode }: { shape: Shape; episode: string | null }) {
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const team = useUi((s) => s.state?.team);
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const cards = useUi((s) => s.cards);
  const seen = useUi((s) => s.seen);
  const boot = useUi((s) => s.boot);

  const active = activity
    .filter((a) => ACTIVE.has(a.status))
    .sort((x, y) => (ORDER[x.status] ?? 9) - (ORDER[y.status] ?? 9));
  const running = active.some((a) => a.status === "running");
  const now = useTicker(running);
  const today = new Date(now);
  const done = activity.filter((a) => {
    if (ACTIVE.has(a.status)) return false;
    const end = a.ended ?? (a.started ? new Date(Date.parse(a.started) + a.seconds * 1000).toISOString() : null);
    return sameDay(end, today);
  });
  const fresh = useArrivals(boot === "ready", [...active.map((a) => `a${a.job}`), ...done.map((a) => `d${a.job}`)]);
  // The crew chat shows the jobs of its episode; the others stay one line away (rule 1.5: nothing runs out of sight).
  const shown = shape === "chat" && episode ? active.filter((a) => a.episode === episode) : active;
  const elsewhere = active.length - shown.length;
  const openCardIn = new Set(Object.values(cards).filter((c) => c.status === "open").map((c) => c.episode));

  const metaFor = (a: Activity) => {
    const step = stepLabel(episodes, a);
    if (a.episode && a.episode !== episode) {
      const title = episodes.find((e) => e.id === a.episode)?.title;
      return title ? `${step} · ${title}` : step;
    }
    return step;
  };

  return (
    <div className={`crew-list crew-${shape}`}>
      {shown.length ? (
        <div className="group">
          {shown.map((a) => (
            <JobRow
              key={a.job}
              a={a}
              who={identityOf(team, a.identity)}
              meta={metaFor(a)}
              seconds={elapsed(a, seen[a.job], now)}
              fresh={fresh(`a${a.job}`)}
              hasCard={openCardIn.has(a.episode)}
              shape={shape}
            />
          ))}
        </div>
      ) : null}
      {elsewhere > 0 ? (
        <button type="button" className="elsewhere" onClick={() => navigate({ kind: "episodes" })}>
          {elsewhere === 1 ? "One more job" : `${countWord(elsewhere)} more jobs`} on other episodes
        </button>
      ) : null}
      {done.length && shape === "rail" ? (
        <div className="later">
          <h3 className="group-label">Done today</h3>
          {done.map((a) => (
            <div key={a.job} className={fresh(`d${a.job}`) ? "job-wrap is-new" : "job-wrap"}>
              <button
                type="button"
                className={a.status === "done" ? "fin" : "fin failed"}
                onClick={() => navigate({ kind: "job", id: a.job })}
                aria-label={`${identityOf(team, a.identity).name}: ${a.doing}, ${a.status}. Open the log.`}
              >
                <Avatar
                  who={identityOf(team, a.identity)}
                  size="small"
                  state={a.status === "done" ? "done" : "plain"}
                  still={!fresh(`d${a.job}`)}
                />
                <span className="one-line">
                  {identityOf(team, a.identity).name} ·{" "}
                  {a.status === "done" ? lowerFirst(a.doing ?? "") : `${a.doing ?? "job"}, ${a.status}`}
                </span>
                <span>{clock(a.seconds)}</span>
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** The head of the working list: the hint line and, when the engine is not logged in, the warn line. */
export function WorkingHint({ episode }: { episode: string | null }) {
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const engineOk = useUi((s) => s.state?.app.engine_ok ?? true);
  const engine = useUi((s) => s.state?.app.engine ?? "claude");
  const boot = useUi((s) => s.boot);
  const active = activity.filter((a) => ACTIVE.has(a.status));
  return (
    <>
      <p className="hint">{boot === "ready" ? hintFor(active, episode) : " "}</p>
      {boot === "ready" && !engineOk ? (
        <p className="engine-line" role="alert">
          <span className="dot warn" aria-hidden="true" />
          <span>{engineLine(engine)}</span>
        </p>
      ) : null}
    </>
  );
}

function moneyTone(money: Money): "danger" | "warn" | undefined {
  const share = money.cap_month_usd > 0 ? money.month_usd / money.cap_month_usd : 0;
  return share >= 1 ? "danger" : share > 0.8 ? "warn" : undefined;
}

/** The Spend card of the right column (rule 14): today, this episode, this month against the cap. */
export function SpendCard({ episode }: { episode: string | null }) {
  const money = useUi((s) => s.state?.money);
  const engine = useUi((s) => s.state?.app.engine ?? "claude");
  if (!money) return null;
  const cap = money.cap_month_usd;
  const share = cap > 0 ? Math.min(1, money.month_usd / cap) : 0;
  const tone = moneyTone(money);
  const ep = episode ? money.episode_usd[episode] ?? 0 : 0;
  const zero = money.today_usd === 0 && money.month_usd === 0 && ep === 0;
  const plan = engine === "claude" ? "your Claude Code plan" : `your ${engine} plan`;
  return (
    <section className="rail-card spend" aria-labelledby="spend-heading">
      <div className="rail-head">
        <h2 className="rail-title" id="spend-heading">
          Spend
        </h2>
        <span className="rail-note">{MONTHS[new Date().getMonth()]}</span>
      </div>
      <div className={zero ? "money zero" : "money"} aria-label="Money spent" data-testid="money">
        <span>
          Today<b key={usd(money.today_usd)}>{usd(money.today_usd)}</b>
        </span>
        <span>
          Episode<b key={episode ? usd(ep) : "none"}>{episode ? usd(ep) : "–"}</b>
        </span>
        <span className="month">
          Month
          <b className={tone} key={usd(money.month_usd)}>
            {usd(money.month_usd)} of {usdShort(cap)}
          </b>
        </span>
      </div>
      <ProgressBar
        className="cap-bar"
        label="This month against the cap"
        isLabelHidden
        value={Math.round(share * 100)}
        variant={tone === "danger" ? "error" : tone === "warn" ? "warning" : "neutral"}
      />
      <p className="foot-note">
        Cap {usdShort(cap)} a month. Rented GPUs and paid APIs only; the crew runs on {plan}.
      </p>
    </section>
  );
}

/** The money in one quiet line, under the working tiles of the crew chat (rule 14). */
export function MoneyLine({ episode }: { episode: string }) {
  const money = useUi((s) => s.state?.money);
  if (!money) return null;
  const tone = moneyTone(money);
  const ep = money.episode_usd[episode] ?? 0;
  const zero = money.today_usd === 0 && money.month_usd === 0 && ep === 0;
  return (
    <p className={zero ? "money-line zero" : "money-line"} aria-label="Money spent" data-testid="money">
      <span>
        Today <b>{usd(money.today_usd)}</b>
      </span>
      <span>
        Episode <b>{usd(ep)}</b>
      </span>
      <span>
        Month{" "}
        <b className={tone}>
          {usd(money.month_usd)} of {usdShort(money.cap_month_usd)}
        </b>
      </span>
    </p>
  );
}

/** The demo says so, always (rule 17). */
export function DemoNote() {
  const demo = useUi((s) => s.demo);
  if (!demo) return null;
  return (
    <p className="demo-note">
      {demo === "auto" ? "Demo data. Crewcut is not running at this address." : "Demo data. Nothing here is real."}
    </p>
  );
}

/** The right column of the home and the read-only views: "Working now", then "Spend". */
export function CrewRail() {
  const view = useUi((s) => s.view);
  const lastEpisode = useUi((s) => s.lastEpisode);
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const episode = view.kind === "episode" ? view.id : lastEpisode;
  const n = activity.filter((a) => ACTIVE.has(a.status)).length;
  return (
    <aside className="rail" aria-labelledby="crew-heading">
      <section className="rail-card working">
        <div className="rail-head">
          <h2 className="rail-title" id="crew-heading">
            Working now
          </h2>
          {n ? <span className="rail-note">{n === 1 ? "1 job" : `${n} jobs`}</span> : null}
        </div>
        <WorkingHint episode={null} />
        <WorkingList shape="rail" episode={null} />
      </section>
      <SpendCard episode={episode === "_onboarding" ? null : episode} />
      <DemoNote />
    </aside>
  );
}
