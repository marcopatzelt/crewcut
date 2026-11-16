// The right place: who works on what right now, done today, and the money row (DESIGN.md rules 2, 13, 14).
// An opaque floating panel: it holds numbers that must read safely. The running jobs are a grouped list on a card.
import { ChevronUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Activity, Episode, Identity, Money } from "../api/types";
import { clock, countWord, sameDay, usd, usdShort } from "../lib/format";
import { jumpToOpenCard, navigate } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { identityOf, Mark } from "./bits";

const ACTIVE = new Set(["running", "waiting", "queued"]);
const ORDER: Record<string, number> = { running: 0, waiting: 1, queued: 2 };

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

function JobRow({
  a,
  who,
  meta,
  seconds,
  fresh,
  hasCard,
}: {
  a: Activity;
  who: Identity;
  meta: string;
  seconds: number;
  fresh: boolean;
  hasCard: boolean;
}) {
  const running = a.status === "running";
  const doing = a.status === "queued" && !a.doing ? "Waiting for a free slot" : a.doing;
  const toCard = a.status === "waiting" && hasCard;
  const open = () => {
    if (toCard && jumpToOpenCard(a.episode)) return;
    navigate({ kind: "job", id: a.job });
  };
  return (
    <div className={fresh ? "job-wrap is-new" : "job-wrap"}>
      <button
        type="button"
        className="job"
        data-job={a.job}
        onClick={open}
        aria-label={`${who.name}: ${doing}. ${meta}. ${toCard ? "Open the card." : "Open the log."}`}
      >
        <Mark mark={who.mark} state={running ? "working" : a.status === "waiting" ? "waiting" : undefined} />
        <span className="job-main">
          <span className="job-name one-line">{who.name}</span>
          <span className="job-doing one-line">{doing}</span>
          <span className="job-meta one-line">{meta}</span>
        </span>
        <span className="job-right">
          <b>{clock(seconds)}</b>
          {running ? usd(a.cost_usd) : null}
        </span>
        {running ? (
          typeof a.progress === "number" ? (
            <span className="prog" aria-hidden="true">
              <i style={{ transform: `scaleX(${Math.min(1, Math.max(0, a.progress))})` }} />
            </span>
          ) : (
            <span className="prog unknown" aria-hidden="true">
              <i />
            </span>
          )
        ) : null}
      </button>
    </div>
  );
}

function MoneyRow({ money, episode }: { money: Money | undefined; episode: string | null }) {
  if (!money) return null;
  const cap = money.cap_month_usd;
  const share = cap > 0 ? money.month_usd / cap : 0;
  const tone = share >= 1 ? "danger" : share > 0.8 ? "warn" : undefined;
  const ep = episode ? money.episode_usd[episode] ?? 0 : 0;
  const zero = money.today_usd === 0 && money.month_usd === 0 && ep === 0;
  return (
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
        <span className={tone ? `cap ${tone}` : "cap"} aria-hidden="true">
          <i style={{ transform: `scaleX(${Math.min(1, Math.max(0, share))})` }} />
        </span>
      </span>
    </div>
  );
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

/** The engine is not logged in: one line with a --warn dot (rule 11). */
export function engineLine(engine: string): string {
  return engine === "claude"
    ? "Claude Code is not logged in. Run claude setup-token, put the value in .env and restart Crewcut."
    : `${engine} is not logged in. Run ${engine} login, put the value in .env and restart Crewcut.`;
}

/** The content of the Crew place, used in the right column and in the narrow-window sheet. */
export function CrewContent({ headingId }: { headingId: string }) {
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const team = useUi((s) => s.state?.team);
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const money = useUi((s) => s.state?.money);
  const engineOk = useUi((s) => s.state?.app.engine_ok ?? true);
  const engine = useUi((s) => s.state?.app.engine ?? "claude");
  const cards = useUi((s) => s.cards);
  const seen = useUi((s) => s.seen);
  const view = useUi((s) => s.view);
  const lastEpisode = useUi((s) => s.lastEpisode);
  const boot = useUi((s) => s.boot);

  const episode = view.kind === "episode" ? view.id : lastEpisode;
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
    <>
      <h2 id={headingId} className="crew-title">
        Working now
      </h2>
      <p className="hint">{boot === "ready" ? hintFor(active, episode) : " "}</p>
      {boot === "ready" && !engineOk ? (
        <p className="engine-line" role="alert">
          <span className="dot warn" aria-hidden="true" />
          <span>{engineLine(engine)}</span>
        </p>
      ) : null}
      <div className="crew-list">
        {active.length ? (
          <div className="group">
            {active.map((a) => (
              <JobRow
                key={a.job}
                a={a}
                who={identityOf(team, a.identity)}
                meta={metaFor(a)}
                seconds={elapsed(a, seen[a.job], now)}
                fresh={fresh(`a${a.job}`)}
                hasCard={openCardIn.has(a.episode)}
              />
            ))}
          </div>
        ) : null}
        {done.length ? (
          <div className="later">
            <div className="group-label">Done today</div>
            {done.map((a) => (
              <div key={a.job} className={fresh(`d${a.job}`) ? "job-wrap is-new" : "job-wrap"}>
                <button
                  type="button"
                  className={a.status === "done" ? "fin" : "fin failed"}
                  onClick={() => navigate({ kind: "job", id: a.job })}
                  aria-label={`${identityOf(team, a.identity).name}: ${a.doing}, ${a.status}. Open the log.`}
                >
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
      <MoneyRow money={money} episode={episode === "_onboarding" ? null : episode} />
    </>
  );
}

export function CrewColumn() {
  return (
    <aside className="crew" aria-labelledby="crew-heading">
      <CrewContent headingId="crew-heading" />
    </aside>
  );
}

/** Below 1100 px the Crew place folds into this bar above the composer. */
export function CrewBar() {
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const team = useUi((s) => s.state?.team);
  const money = useUi((s) => s.state?.money);
  const engineOk = useUi((s) => s.state?.app.engine_ok ?? true);
  const engine = useUi((s) => s.state?.app.engine ?? "claude");
  const [open, setOpen] = useState(false);
  const active = activity.filter((a) => ACTIVE.has(a.status));
  const first = active.find((a) => a.status === "running") ?? active[0];
  const marks = [...new Set(active.map((a) => a.identity))].slice(0, 4);
  const summary = !engineOk
    ? engineLine(engine)
    : first
      ? `${identityOf(team, first.identity).name}: ${first.doing}`
      : "Nobody is working. Nothing is running, nothing costs money.";
  const monthLine = money && engineOk ? ` · Month ${usd(money.month_usd)} of ${usdShort(money.cap_month_usd)}` : "";

  return (
    <>
      {open ? (
        <div className="crew-sheet" role="region" aria-labelledby="crew-sheet-heading">
          <CrewContent headingId="crew-sheet-heading" />
        </div>
      ) : null}
      <button
        type="button"
        className="crewbar"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        aria-label={`Crew: ${summary}. ${open ? "Hide" : "Show"} who is working.`}
      >
        <span className="marks" aria-hidden="true">
          {!engineOk ? <span className="dot warn" /> : null}
          {marks.map((id) => (
            <Mark key={id} mark={identityOf(team, id).mark} small />
          ))}
        </span>
        <span className="summary one-line">
          {summary}
          {monthLine}
        </span>
        <ChevronUp size={16} aria-hidden="true" className={open ? "chev" : "chev down"} />
      </button>
    </>
  );
}
