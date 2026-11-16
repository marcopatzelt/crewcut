// Profile, Crew and job log: read-only views in the center place (DESIGN.md rule 2). No edit controls anywhere.
import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ONBOARDING, type Identity, type JobLog, type Profile, type Source } from "../api/types";
import { ErrorLine, identityOf, Loading, Mark, Media } from "../components/bits";
import { STEP_LABELS } from "../demo/fixtures";
import { clock, day, usd } from "../lib/format";
import { messageOf, navigate } from "../store/actions";
import { useUi } from "../store/store";

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

  return (
    <section className="view" aria-label="Profile">
      <header className="head plain">
        <h1>Profile</h1>
        <p className="sub">
          {data?.source === "neutral"
            ? "The neutral style pack. Paste your links in the chat to make it yours."
            : "Your style pack. Every value names its source."}
        </p>
      </header>
      <div className="page">
        <div className="doc">
          <BackToChat />
          {content}
          <p className="hint-line">{CHANGE_LINE}</p>
        </div>
      </div>
    </section>
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
      <Mark mark={p.mark} big />
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
  else content = data.map((p) => <Person key={p.id} p={p} />);
  const anySources = data?.some((p) => p.sources?.length);

  return (
    <section className="view" aria-label="Crew">
      <header className="head plain">
        <h1>Crew</h1>
        <p className="sub">Who works on your episodes, what they may do, and whose know-how their skills distil.</p>
      </header>
      <div className="page">
        <div className="doc">
          <BackToChat />
          {content}
          {anySources ? (
            <p className="hint-line">Crewcut is not affiliated with or endorsed by these creators.</p>
          ) : null}
          <p className={anySources ? "meta" : "hint-line"}>{CHANGE_LINE}</p>
        </div>
      </div>
    </section>
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
    <section className="view" aria-label={`Log of job ${id}`}>
      <header className="head plain">
        <div className="head-row">
          {job ? <Mark mark={who.mark} /> : null}
          <div className="head-text">
            <h1 className="one-line" title={job?.doing}>
              {job ? `${who.name}: ${job.doing}` : `Job ${id}`}
            </h1>
            <p className="sub">{meta}</p>
          </div>
        </div>
      </header>
      <div className="page">
        <div className="doc">
          <BackToChat />
          {content}
          <p className="hint-line">This log is read-only. Secrets are removed before it is shown.</p>
        </div>
      </div>
    </section>
  );
}
