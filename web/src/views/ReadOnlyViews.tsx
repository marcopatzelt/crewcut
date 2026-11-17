// Style pack, Crew, GPU and renders, job log: read-only views in the main column (DESIGN.md rule 2). No edit controls
// anywhere; a change is a sentence in the chat.
import { ArrowLeft } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import { ONBOARDING, type Identity, type JobLog, type Profile, type Source } from "../api/types";
import { ErrorLine, identityOf, Loading, Media } from "../components/bits";
import { Avatar, SlateFigure } from "../slate/Slate";
import { STEP_LABELS } from "../demo/fixtures";
import { ago, clock, day, usd } from "../lib/format";
import { messageOf, navigate } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { Dock } from "./EpisodeView";
import { MotionShelf } from "./MotionShelf";

const CHANGE_LINE = "To change something, say it in the chat.";

/** Loads one resource for a view; keeps the layout while loading, shows an inline error with retry. */
function useResource<T>(load: () => Promise<T>, key: string, pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    load()
      .then((d) => live && setData(d))
      .catch((e) => live && setError(messageOf(e)));
    return () => {
      live = false;
    };
    // The key names the resource; `load` is a new function on every render and is left out on purpose.
  }, [key, tick]);
  useEffect(() => {
    if (!pollMs) return;
    const t = setInterval(() => setTick((n) => n + 1), pollMs);
    return () => clearInterval(t);
  }, [pollMs]);
  return { data, error, retry: () => setTick((n) => n + 1) };
}

function BackToChat() {
  const last = useUi((s) => s.lastEpisode);
  if (!last) return null;
  return (
    <button type="button" className="text-button back" onClick={() => navigate({ kind: "episode", id: last })}>
      <ArrowLeft size={16} aria-hidden="true" />
      Back to the chat
    </button>
  );
}

/** A read-only page: the large title, then the content; the composer floats at the bottom (rule 7). */
export function Page({
  label,
  title,
  sub,
  lead,
  wide,
  children,
}: {
  label: string;
  title: string;
  sub: string;
  lead?: ReactNode;
  /** grids use the width of the column, text pages keep a reading width */
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <main className="main page-main" aria-label={label}>
      <div className="page-scroll">
        <div className={wide ? "doc wide" : "doc"}>
          <div className="page-head">
            {lead}
            <div className="page-words">
              <h1 className="one-line" title={title}>
                {title}
              </h1>
              {sub ? <p className="sub">{sub}</p> : null}
            </div>
          </div>
          {children}
        </div>
      </div>
      <Dock />
    </main>
  );
}

function stepName(id: string): string {
  const i = STEP_LABELS.findIndex(([s]) => s === id);
  const label = STEP_LABELS[i]?.[1];
  return label ? `${i + 1} ${label}` : id;
}

export function ProfileView() {
  const { data, error, retry } = useResource<Profile>(() => api.profile(), "profile");
  let content;
  if (error) content = <ErrorLine text={`Couldn't load the profile. ${error}`} onRetry={retry} />;
  else if (!data) content = <Loading label="Loading the profile" />;
  else {
    const groups = new Map<string, Profile["rules"]>();
    for (const r of data.rules) groups.set(r.step, [...(groups.get(r.step) ?? []), r]);
    const order = STEP_LABELS.map(([id]) => id);
    const steps = [...groups.keys()].sort((a, b) => order.indexOf(a) - order.indexOf(b));
    content = (
      <>
        <section className="section" aria-labelledby="profile-values">
          <h2 id="profile-values">Values</h2>
          {data.rows.length ? (
            <div className="rows">
              {data.rows.map((r) => (
                <div className="prow" key={r.label}>
                  <span className="label">{r.label}</span>
                  <span className="value">
                    {r.kind === "color" ? (
                      <span className="swatch" style={{ background: r.value }} aria-hidden="true" />
                    ) : null}
                    <span className="one-line" title={r.value}>
                      {r.value}
                    </span>
                  </span>
                  <span className="source">{r.source ?? ""}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="meta">No values yet. Paste your links in the chat.</p>
          )}
        </section>
        {data.preview ? (
          <section className="section" aria-labelledby="profile-preview">
            <h2 id="profile-preview">10-second preview</h2>
            <div className="preview solo">
              <Media episode={ONBOARDING} path={data.preview} label="10-second preview in your style" />
            </div>
          </section>
        ) : null}
        <MotionShelf />
        <section className="section" aria-labelledby="profile-rules">
          <h2 id="profile-rules">Rules by step</h2>
          {steps.length ? (
            steps.map((step) => (
              <div className="rule-group" key={step}>
                <div className="group-label">
                  {stepName(step)}
                </div>
                {(groups.get(step) ?? []).map((r, i) => (
                  <div className="rule-item" key={`${r.date}-${i}`}>
                    <div>{r.rule}</div>
                    <div className="meta">
                      {day(r.date)} · {r.source}
                    </div>
                  </div>
                ))}
              </div>
            ))
          ) : (
            <p className="meta">No rules yet. The crew learns them from your corrections.</p>
          )}
        </section>
      </>
    );
  }

  const sub =
    data?.source === "neutral"
      ? "The neutral style pack. Paste your links in the chat to make it yours."
      : "Your style pack. Every value names its source.";
  return (
    <Page label="Style pack" title="Style pack" sub={sub}>
      <BackToChat />
      {content}
      <p className="hint-line">{CHANGE_LINE}</p>
    </Page>
  );
}

function SourceItem({ s }: { s: Source | string }) {
  if (typeof s === "string") {
    return /^https?:\/\//.test(s) ? (
      <a href={s} target="_blank" rel="noreferrer">
        {s}
      </a>
    ) : (
      <>{s}</>
    );
  }
  return (
    <>
      {s.url ? (
        <a href={s.url} target="_blank" rel="noreferrer">
          {s.name}
        </a>
      ) : (
        s.name
      )}
      {s.what ? <span className="meta"> · {s.what}</span> : null}
    </>
  );
}

function Person({ p }: { p: Identity }) {
  const rights = [
    p.may_spend ? "May rent GPUs and pay for APIs, within your cap" : "Does not spend money",
    p.may_publish ? "May publish, after your yes on the exact file" : "Does not publish",
  ];
  return (
    <article className="person" aria-labelledby={`person-${p.id}`}>
      <Avatar who={p} size="big" />
      <div className="msg-main">
        <div className="name" id={`person-${p.id}`}>
          {p.name}
        </div>
        <div className="role">{p.role}</div>
        {p.soul ? <p className="soul">{p.soul}</p> : null}
        <dl>
          <dt>Skills</dt>
          <dd>{p.skills.length ? p.skills.join(", ") : "None"}</dd>
          <dt>Rights</dt>
          <dd>{rights.join(". ")}.</dd>
          {p.sources?.length ? (
            <>
              <dt>Sources</dt>
              <dd>
                <ul>
                  {p.sources.map((s, i) => (
                    <li key={i}>
                      <SourceItem s={s} />
                    </li>
                  ))}
                </ul>
              </dd>
            </>
          ) : null}
        </dl>
      </div>
    </article>
  );
}

export function TeamView() {
  const { data, error, retry } = useResource<Identity[]>(() => api.team(), "team");
  let content;
  if (error) content = <ErrorLine text={`Couldn't load the crew. ${error}`} onRetry={retry} />;
  else if (!data) content = <Loading label="Loading the crew" />;
  else if (!data.length) content = <p className="meta">No crew members found. Check the team folder of the app.</p>;
  else
    content = (
      <div className="people">
        {data.map((p) => (
          <Person key={p.id} p={p} />
        ))}
      </div>
    );
  const anySources = data?.some((p) => p.sources?.length);

  return (
    <Page
      wide
      label="Crew"
      title="Crew"
      sub="Who works on your episodes, what they may do, and whose know-how their skills distil."
    >
      <BackToChat />
      {content}
      {anySources ? <p className="hint-line">Crewcut is not affiliated with or endorsed by these creators.</p> : null}
      <p className={anySources ? "meta" : "hint-line"}>{CHANGE_LINE}</p>
    </Page>
  );
}

export function JobLogView({ id }: { id: number }) {
  const job = useUi((s) => s.state?.activity.find((a) => a.job === id));
  const team = useUi((s) => s.state?.team);
  const episodes = useUi((s) => s.state?.episodes);
  const running = job?.status === "running" || job?.status === "waiting";
  const { data, error, retry } = useResource<JobLog>(() => api.jobLog(id), `job-${id}`, running ? 3000 : undefined);
  const who = identityOf(team, job?.identity);
  const ep = episodes?.find((e) => e.id === job?.episode);
  const step = ep?.steps.find((s) => s.id === job?.step);
  const meta = [
    `Job ${id}`,
    step ? `${step.n} ${step.label}` : job?.step,
    ep?.title,
    job ? clock(job.seconds) : null,
    job ? `${usd(job.cost_usd)} spent` : null,
    job && typeof job.equiv_usd === "number" ? `API equivalent ${usd(job.equiv_usd)} (on your subscription)` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const engine = job ? engineWords(job) : "";

  let content;
  if (error && !data) content = <ErrorLine text={`Couldn't load the log. ${error}`} onRetry={retry} />;
  else if (!data) content = <Loading label="Loading the log" />;
  else if (!data.lines.length) content = <p className="meta">The log is empty so far.</p>;
  else
    content = (
      <ol className="log" aria-label="Log">
        {data.lines.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ol>
    );

  return (
    <Page
      label={`Log of job ${id}`}
      title={job ? `${who.name}: ${job.doing}` : `Job ${id}`}
      sub={meta}
      lead={job ? <Avatar who={who} size="big" /> : undefined}
    >
      <BackToChat />
      {engine ? <p className="meta engine-meta">{engine}</p> : null}
      {content}
      <p className="hint-line">This log is read-only. Secrets are removed before it is shown.</p>
    </Page>
  );
}

const ENGINE_NAME: Record<string, string> = { claude: "Claude Code", codex: "Codex" };

/** "Runs on Claude Code 2.1.325 · model sonnet · effort high": what the engine reported about itself, if anything. */
export function engineWords(job: { engine?: string | null; model?: string | null; effort?: string | null; engine_version?: string | null }): string {
  if (!job.engine && !job.model && !job.effort) return "";
  const name = job.engine ? ENGINE_NAME[job.engine] ?? job.engine : null;
  return [
    name ? `Runs on ${name}${job.engine_version ? ` ${job.engine_version}` : ""}` : null,
    job.model ? `model ${job.model}` : null,
    job.effort ? `effort ${job.effort}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Render work and rented GPUs: the jobs that render or rent, running first. Each opens its log. */
const RENDER_WORDS = /render|gpu|blender|3d/i;

export function RendersView() {
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const team = useUi((s) => s.state?.team);
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const jobs = activity
    .filter((a) => RENDER_WORDS.test(a.doing ?? "") || RENDER_WORDS.test(a.step ?? ""))
    .sort((a, b) => Number(b.status === "running") - Number(a.status === "running") || b.job - a.job);
  return (
    <Page
      wide
      label="GPU and renders"
      title="GPU and renders"
      sub="Every render job and rented GPU. A rented machine is deleted when its frames are home."
    >
      <BackToChat />
      {jobs.length ? (
        <ul className="renders">
          {jobs.map((a) => {
            const who = identityOf(team, a.identity);
            const ep = episodes.find((e) => e.id === a.episode);
            return (
              <li key={a.job}>
                <button
                  type="button"
                  className="render-row"
                  onClick={() => navigate({ kind: "job", id: a.job })}
                  aria-label={`${who.name}: ${a.doing}, ${a.status}. Open the log.`}
                >
                  <Avatar who={who} size="crew" state={a.status === "running" ? "working" : a.status === "done" ? "done" : "plain"} still />
                  {a.preview ? <img src={a.preview} alt="" className="render-pic" loading="lazy" /> : null}
                  <span className="render-words">
                    <b className="one-line">{a.doing}</b>
                    <span className="meta one-line">
                      {[who.name, ep?.title, a.status === "running" ? `running ${clock(a.seconds)}` : `${a.status} ${ago(a.ended ?? a.started)}`, a.cost_usd ? usd(a.cost_usd) : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="home-empty">
          <SlateFigure state="idle" size={80} />
          <p>No renders right now. When a step needs a GPU, a card asks first.</p>
        </div>
      )}
      <p className="hint-line">{CHANGE_LINE}</p>
    </Page>
  );
}
