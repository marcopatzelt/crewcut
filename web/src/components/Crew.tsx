// The right place: who works on what right now, done today, and the money row (DESIGN.md rules 2, 13, 14).
import { ChevronUp } from "lucide-react";
import { useEffect, useState } from "react";
import type { Activity, Episode, Identity, Money } from "../api/types";
import { clock, countWord, sameDay, usd, usdShort } from "../lib/format";
import { navigate } from "../store/actions";
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
}: {
  a: Activity;
  who: Identity;
  meta: string;
  seconds: number;
}) {
  const waiting = a.status !== "running";
  return (
    <button
      type="button"
      className="job"
      onClick={() => navigate({ kind: "job", id: a.job })}
      aria-label={`${who.name}: ${a.doing}. ${meta}. Open the log.`}
    >
      <Mark mark={who.mark} />
      <span className="job-main">
        <span className="job-name one-line">{who.name}</span>
        <span className="job-doing">{a.status === "queued" && !a.doing ? "Waiting for a free slot" : a.doing}</span>
        <span className="job-meta">{meta}</span>
      </span>
      <span className="job-right">
        <b>{clock(seconds)}</b>
        {waiting ? null : usd(a.cost_usd)}
      </span>
      {a.status === "running" ? (
        typeof a.progress === "number" ? (
          <span className="prog" aria-hidden="true">
            <i style={{ width: `${Math.round(Math.min(1, Math.max(0, a.progress)) * 100)}%` }} />
          </span>
        ) : (
          <span className="prog unknown" aria-hidden="true">
            <i />
          </span>
        )
      ) : null}
    </button>
  );
}

function MoneyRow({ money, episode }: { money: Money | undefined; episode: string | null }) {
  if (!money) return null;
  const cap = money.cap_month_usd;
  const share = cap > 0 ? money.month_usd / cap : 0;
  const tone = share >= 1 ? "danger" : share > 0.8 ? "warn" : undefined;
  return (
    <div className="money" aria-label="Money spent">
      <span>
        Today<b>{usd(money.today_usd)}</b>
      </span>
      <span>
        Episode<b>{episode ? usd(money.episode_usd[episode] ?? 0) : "–"}</b>
      </span>
      <span>
        Month
        <b className={tone}>
          {usd(money.month_usd)} of {usdShort(cap)}
        </b>
      </span>
    </div>
  );
}

function hintFor(active: Activity[], episode: string | null): string {
  if (!active.length) return "Nobody is working right now.";
  if (!episode) {
    const n = new Set(active.map((a) => a.identity)).size;
    return n === 1 ? "One of the crew is working." : `${countWord(n)} of the crew are working.`;
  }
  const here = new Set(active.filter((a) => a.episode === episode).map((a) => a.identity)).size;
  if (here === 0) return "Nobody is on this episode right now.";
  return here === 1 ? "One of the crew is on this episode." : `${countWord(here)} of the crew are on this episode.`;
}

/** The content of the Crew place, used in the right column and in the narrow-window sheet. */
export function CrewContent({ headingId }: { headingId: string }) {
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const team = useUi((s) => s.state?.team);
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const money = useUi((s) => s.state?.money);
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
      <h2 id={headingId}>Working now</h2>
      <p className="hint">{boot === "ready" ? hintFor(active, episode) : " "}</p>
      <div className="crew-list">
        {active.map((a) => (
          <JobRow
            key={a.job}
            a={a}
            who={identityOf(team, a.identity)}
            meta={metaFor(a)}
            seconds={elapsed(a, seen[a.job], now)}
          />
        ))}
        {done.length ? (
          <div className="later">
            <div className="group-label">Done today</div>
            {done.map((a) => (
              <button
                type="button"
                key={a.job}
                className={a.status === "done" ? "fin" : "fin failed"}
                onClick={() => navigate({ kind: "job", id: a.job })}
                aria-label={`${identityOf(team, a.identity).name}: ${a.doing}, ${a.status}. Open the log.`}
              >
                <span className="one-line">
                  {identityOf(team, a.identity).name} · {a.status === "done" ? lowerFirst(a.doing ?? "") : `${a.doing ?? "job"}, ${a.status}`}
                </span>
                <span>{clock(a.seconds)}</span>
              </button>
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
  const [open, setOpen] = useState(false);
  const active = activity.filter((a) => ACTIVE.has(a.status));
  const first = active.find((a) => a.status === "running") ?? active[0];
  const marks = [...new Set(active.map((a) => a.identity))].slice(0, 4);
  const summary = first
    ? `${identityOf(team, first.identity).name}: ${first.doing}`
    : "Nobody is working right now.";
  const monthLine = money ? ` · Month ${usd(money.month_usd)} of ${usdShort(money.cap_month_usd)}` : "";

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
          {marks.map((id) => (
            <Mark key={id} mark={identityOf(team, id).mark} />
          ))}
        </span>
        <span className="summary one-line">
          {summary}
          {monthLine}
        </span>
        <ChevronUp size={16} aria-hidden="true" style={{ transform: open ? "none" : "rotate(180deg)" }} />
      </button>
    </>
  );
}
