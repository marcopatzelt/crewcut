// The format system in the app (docs/formats.md): what New episode asks (long, short or auto, and optionally a show
// format), the Scout's pick with its reason in the episode, the idea cards from the scout and saved links, and the
// scoreboard per format. No text fields: the composer stays the one place for words (DESIGN.md rule 3).
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EpisodeFormat, FormatScore, Idea, Length, Scoreboard, ShowFormat } from "../api/types";
import { messageOf, navigate, upsertEpisode } from "../store/actions";
import { setUi, useUi } from "../store/store";
import "../styles/formats.css";

const LENGTHS: Array<{ id: Length; label: string; hint: string }> = [
  { id: "long", label: "Long", hint: "A long video" },
  { id: "short", label: "Short", hint: "A Short, 9:16" },
  { id: "auto", label: "Auto", hint: "Crewcut decides" },
];

const TOPIC_WORDS: Record<string, string> = {
  far_past: "far past",
  recent_past: "recent past",
  present: "present",
  trending: "trending",
  manufactured: "made for the video",
};

export function topicWord(t: string | null | undefined): string | null {
  return t ? TOPIC_WORDS[t] ?? t : null;
}

/** Long, Short or Auto, and which show format: the choices above the composer in New episode. */
export function NewEpisodeChoices() {
  const choice = useUi((s) => s.newEpisode);
  const [formats, setFormats] = useState<ShowFormat[] | null>(null);
  useEffect(() => {
    let live = true;
    api
      .formats()
      .then((lib) => live && setFormats(lib.enabled ? lib.formats : []))
      .catch(() => live && setFormats([]));
    return () => {
      live = false;
    };
  }, []);
  const set = (patch: Partial<{ length: Length; format: string | null }>) =>
    setUi((s) => ({ newEpisode: { ...s.newEpisode, ...patch } }));
  const shown = (formats ?? []).filter((f) => choice.length === "auto" || f.length === choice.length);
  const picked = (formats ?? []).find((f) => f.id === choice.format) ?? null;
  return (
    <div className="new-choices">
      <div className="pills" role="group" aria-label="Length">
        {LENGTHS.map((l) => (
          <button
            key={l.id}
            type="button"
            className="pill"
            aria-pressed={choice.length === l.id}
            title={l.hint}
            onClick={() => {
              const keep = picked && (l.id === "auto" || picked.length === l.id);
              set({ length: l.id, format: keep ? choice.format : null });
            }}
          >
            {l.label}
          </button>
        ))}
      </div>
      {shown.length ? (
        <div className="pills" role="group" aria-label="Format">
          <button type="button" className="pill" aria-pressed={choice.format === null} onClick={() => set({ format: null })}>
            Crewcut picks
          </button>
          {shown.map((f) => (
            <button
              key={f.id}
              type="button"
              className="pill"
              aria-pressed={choice.format === f.id}
              title={f.when}
              onClick={() => set({ format: f.id })}
            >
              {f.name}
              <span className="pill-count">{f.length === "short" ? "Short" : "Long"}</span>
            </button>
          ))}
        </div>
      ) : null}
      <p className="meta format-hint">
        {picked
          ? `${picked.name}: ${picked.when}`
          : shown.length
            ? "The Scout reads your input, picks the format that fits and says why. Then the Writer writes the full script."
            : "The Scout reads your input and starts the episode."}
      </p>
    </div>
  );
}

/** The Scout's pick in the episode head: the format and its short reason. */
export function FormatPick({ pick }: { pick: EpisodeFormat | null | undefined }) {
  if (!pick) return null;
  const facts = [pick.length === "short" ? "Short" : pick.length === "long" ? "Long" : null, topicWord(pick.topic_type)]
    .filter(Boolean)
    .join(" · ");
  return (
    <section className="format-pick" aria-label="Format">
      <p>
        <b>Format: {pick.name}</b>
        {facts ? <span className="meta"> · {facts}</span> : null}
      </p>
      {pick.reason ? <p className="format-reason">{pick.reason}</p> : <p className="meta">The Scout is choosing; the reason follows.</p>}
      {pick.runner_up ? <p className="meta">Runner-up: {pick.runner_up}</p> : null}
    </section>
  );
}

function sourceWord(s: string): string {
  return s === "scout" ? "Scout" : s === "braindump" ? "Saved link" : s;
}

/** Open idea cards: "Start episode" makes the episode the same way as New episode; "Dismiss" hides it for good. */
export function Ideas({ limit = 6 }: { limit?: number }) {
  const [ideas, setIdeas] = useState<Idea[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .ideas()
      .then((rows) => live && setIdeas(rows))
      .catch(() => live && setIdeas([]));
    return () => {
      live = false;
    };
  }, []);
  const open = (ideas ?? []).filter((i) => i.status === "open");
  if (!open.length) return null;

  async function act(idea: Idea, what: "start" | "dismiss") {
    setBusy(idea.id);
    setError(null);
    try {
      if (what === "start") {
        const res = await api.startIdea(idea.id);
        setIdeas((rows) => (rows ?? []).map((r) => (r.id === idea.id ? res.idea : r)));
        upsertEpisode(res.episode, true);
        navigate({ kind: "episode", id: res.episode.id });
      } else {
        const res = await api.dismissIdea(idea.id);
        setIdeas((rows) => (rows ?? []).map((r) => (r.id === idea.id ? res : r)));
      }
    } catch (e) {
      setError(`Couldn't ${what === "start" ? "start it" : "dismiss it"}. ${messageOf(e)}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="home-section" aria-labelledby="ideas-heading">
      <div className="section-head">
        <h2 id="ideas-heading">Ideas</h2>
        <span className="section-note">{open.length > limit ? `${limit} of ${open.length} open` : `${open.length} open`}</span>
      </div>
      {error ? (
        <p className="composer-error" role="alert">
          {error}
        </p>
      ) : null}
      <ul className="ideas">
        {open.slice(0, limit).map((idea) => (
          <li key={idea.id} className="idea">
            <p className="meta">
              {sourceWord(idea.source)}
              {topicWord(idea.topic_type) ? ` · ${topicWord(idea.topic_type)}` : ""}
            </p>
            <h3 className="idea-title">
              {idea.url && /^https?:\/\//.test(idea.url) ? (
                <a href={idea.url} target="_blank" rel="noreferrer">
                  {idea.title}
                </a>
              ) : (
                idea.title
              )}
            </h3>
            {idea.summary ? <p className="idea-summary">{idea.summary}</p> : null}
            <p className="meta">
              {idea.suggested_format
                ? `Suggested format: ${idea.suggested_format}${idea.suggestion === "rule" ? " (a guess from keywords; the Scout decides)" : ""}`
                : "No format suggested; the Scout picks one."}
            </p>
            <div className="idea-actions">
              <button type="button" className="pill" disabled={busy !== null} onClick={() => void act(idea, "start")}>
                Start episode
              </button>
              <button type="button" className="pill" disabled={busy !== null} onClick={() => void act(idea, "dismiss")}>
                Dismiss
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function num(v: number | null | undefined, unit = ""): string {
  if (v === null || v === undefined) return "-";
  return `${Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-US") : String(v)}${unit}`;
}

/** Which formats win: one row per format with measured numbers, and a hint (never a rule). */
export function ScoreboardTable() {
  const [board, setBoard] = useState<Scoreboard | null>(null);
  useEffect(() => {
    let live = true;
    api
      .scoreboard()
      .then((b) => live && setBoard(b))
      .catch(() => live && setBoard(null));
    return () => {
      live = false;
    };
  }, []);
  if (!board?.formats.length) return null;
  return (
    <section className="home-section" aria-labelledby="score-heading">
      <div className="section-head">
        <h2 id="score-heading">Formats</h2>
        <span className="section-note">Measured results per format. CTR comes from YouTube Studio, when you add it.</span>
      </div>
      <table className="scoreboard">
        <thead>
          <tr>
            <th scope="col">Format</th>
            <th scope="col">Episodes</th>
            <th scope="col">Median views</th>
            <th scope="col">Watched</th>
            <th scope="col">Subs per 1,000 views</th>
            <th scope="col">CTR</th>
            <th scope="col">Hint</th>
          </tr>
        </thead>
        <tbody>
          {board.formats.map((f: FormatScore) => (
            <tr key={f.format}>
              <th scope="row">{f.name}</th>
              <td>{f.measured === f.episodes ? f.episodes : `${f.measured} of ${f.episodes}`}</td>
              <td>{num(f.median_views)}</td>
              <td>{num(f.median_avg_view_pct, " %")}</td>
              <td>{num(f.subs_per_1000)}</td>
              <td>{f.ctr === null ? "missing" : `${(f.ctr * 100).toFixed(1)} %`}</td>
              <td className={f.verdict === "more" ? "verdict more" : "verdict"}>{f.verdict_text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
