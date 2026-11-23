// The four motion cards (docs/api.md "Motion cards"), media first, one decision each:
//   motion-plan  the three columns as media, density and budget with the cap in one line; a tap strikes a row
//   style-frame  our frame next to the reference (or the bar's frame), per format
//   template     "Keep it in your library?" with the sample loop and the params
//   baseline     the bar now and this video, with their named strengths
// The yes goes through the card's one button (CardView); a note back is a sentence in the chat.
import { useState } from "react";
import { ApiError } from "../api/client";
import type { BaselineSide, Card } from "../api/types";
import { clock, episodeNumber } from "../lib/format";
import { messageOf, strike } from "../store/actions";
import { ErrorLine, Facts, Media } from "./bits";
import {
  baselineOf,
  FormatMarks,
  formatWord,
  Loop,
  motionPlanOf,
  PlanColumns,
  planLine,
  styleFrameOf,
  templateOf,
} from "./Motion";

/** "013" for "013-one-prompt-full-game", else the id. */
function epShort(id: string): string {
  return episodeNumber(id) ?? id;
}

// ---------- motion-plan ----------

export function MotionPlanPreview({ card, folding }: { card: Card; folding: boolean }) {
  const plan = motionPlanOf(card);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ text: string; retry?: () => void } | null>(null);
  if (!plan) return null;
  const open = card.status === "open" && !folding;

  async function onStrike(row: string, struck: boolean) {
    if (busy !== null || !open) return;
    setBusy(row);
    setError(null);
    try {
      await strike(card, row, struck);
    } catch (e) {
      // 409: the server says why in one sentence (the only chosen upgrade, a plan that would break); retrying won't help
      const final = e instanceof ApiError && e.status === 409;
      setError({
        text: `Couldn't ${struck ? "strike" : "bring back"} this row. ${messageOf(e)}`,
        retry: final ? undefined : () => void onStrike(row, struck),
      });
    } finally {
      setBusy(null);
    }
  }

  const quiet = plan.quiet.filter((q) => q.time).map((q) => q.time);
  const hint = [
    quiet.length ? `Without motion: ${quiet.join(", ")}.` : null,
    open ? "Tap a row to strike it." : null,
    plan.bar ? `The bar is ${epShort(plan.bar)}.` : null,
  ]
    .filter(Boolean)
    .join(" ");
  const line = planLine(plan);
  return (
    <div className="mp">
      {line ? <p className="mp-line">{line}</p> : null}
      <PlanColumns plan={plan} onStrike={open ? (row, struck) => void onStrike(row, struck) : undefined} busy={busy} />
      {hint ? <p className="meta mp-hint">{hint}</p> : null}
      {error ? <ErrorLine text={error.text} onRetry={error.retry} /> : null}
    </div>
  );
}

// ---------- style-frame ----------

function refWord(label: string): string {
  if (label === "reference") return "Reference";
  if (label === "the bar") return "The bar";
  return "No reference";
}

function hueWords(hue: { dominant_share: number; ok: boolean; coloured_share?: number; accent_area_limit?: number; sparse_accent?: boolean } | null | undefined): string | null {
  if (!hue || typeof hue.dominant_share !== "number") return null;
  const pct = `${Math.round(hue.dominant_share * 100)} %`;
  if (hue.ok && hue.sparse_accent && typeof hue.coloured_share === "number") {
    return `Colour check passed: coloured area ${Math.round(hue.coloured_share * 100)} % of the image (channel limit ${Math.round((hue.accent_area_limit ?? 0) * 100)} %)`;
  }
  return hue.ok ? `Hue check passed: the strongest hue holds ${pct} of coloured pixels` : `One hue holds ${pct} of coloured pixels (allowed for grass, sky or footage)`;
}

export function StyleFramePreview({ card }: { card: Card }) {
  const sf = styleFrameOf(card);
  const episode = card.episode;
  if (!sf || !episode) return null;
  return (
    <div className="sf">
      {sf.frames.map((f) => {
        const fmt = formatWord(f.format);
        const ref = refWord(f.ref_label);
        const hue = hueWords(f.hue);
        return (
          <figure className={`sf-pair is-${f.format}`} key={f.format}>
            <div className="sf-pics">
              <div className="sf-side">
                <Media episode={episode} path={f.ours} src={f.ours_url} label={`Our frame, ${fmt}`} />
                <span className="sf-label">Ours</span>
              </div>
              {f.launch_url ? (
                <div className="sf-side">
                  <Media episode={episode} path={f.launch ?? f.launch_url} src={f.launch_url} label={`Launch film, ${fmt}`} />
                  <span className="sf-label">Launch film</span>
                </div>
              ) : null}
              {f.ref_url || !f.launch_url ? (
                <div className="sf-side">
                  {f.ref_url ? (
                    <Media episode={episode} path={f.ref ?? f.ref_url} src={f.ref_url} label={`${ref}, ${fmt}`} />
                  ) : (
                    <div className="sf-none">{f.ref_label.charAt(0).toUpperCase() + f.ref_label.slice(1)}.</div>
                  )}
                  <span className="sf-label">{ref}</span>
                </div>
              ) : null}
            </div>
            <figcaption className="sf-cap">{[fmt, hue, f.launch_shows ? `Launch film: ${f.launch_shows}` : null].filter(Boolean).join(" · ")}</figcaption>
          </figure>
        );
      })}
      {sf.covers.length ? <p className="meta sf-covers">Your yes also covers {sf.covers.join(", ")}: they reuse this piece.</p> : null}
    </div>
  );
}

// ---------- template ----------

/** A param's default as the user reads it. */
export function paramValue(v: unknown): string {
  if (v === null || v === undefined) return "none";
  if (typeof v === "string") return v || "empty";
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(paramValue).join(", ");
  return JSON.stringify(v);
}

/** The params a user can set: every one but the comp's name. */
export function paramFacts(params: Record<string, unknown>) {
  return Object.entries(params)
    .filter(([k]) => k !== "comp")
    .map(([k, v]) => ({ label: k, value: paramValue(v) }));
}

export function TemplatePreview({ card }: { card: Card }) {
  const t = templateOf(card);
  if (!t) return null;
  const loops = t.formats.filter((f) => t.samples[f]);
  const facts = paramFacts(t.params);
  const made = t.made_from ? `Made from ${epShort(t.made_from.episode)}, ${t.made_from.insert}` : null;
  return (
    <div className="tpl">
      <div className={loops.length > 1 ? "tpl-loops pair" : "tpl-loops"}>
        {loops.length ? (
          loops.map((f) => (
            <div className={`tpl-loop is-${f}`} key={f}>
              <Loop src={t.samples[f]} poster={t.poster} label={`Sample of ${t.title}, ${formatWord(f)}`} />
            </div>
          ))
        ) : (
          <div className="tpl-loop is-landscape">
            <Loop src={null} poster={t.poster ?? t.samples.poster} label={`Sample of ${t.title}`} />
          </div>
        )}
      </div>
      {facts.length ? <Facts facts={facts} /> : <p className="meta">No params: it always looks the same.</p>}
      <p className="meta tpl-meta">
        <span>
          {[made, `version ${t.version}`, t.replaces ? `replaces version ${t.replaces}` : null].filter(Boolean).join(" · ")}
        </span>
        <FormatMarks formats={t.formats} />
      </p>
    </div>
  );
}

// ---------- baseline ----------

const MEASURE_WORD: Record<string, string> = {
  motion_moments: "Motion moments",
  critic_errors: "Critic errors",
  upgrades_landed_share: "Upgrades landed",
  caused_transitions_share: "Caused transitions",
  custom_pieces: "Custom pieces",
};

function measureWord(key: string): string {
  if (MEASURE_WORD[key]) return MEASURE_WORD[key];
  const w = key.replace(/_share$/, "").replace(/_/g, " ");
  return w.charAt(0).toUpperCase() + w.slice(1);
}

function measureValue(key: string, v: number | null | undefined): string {
  if (typeof v !== "number") return "–";
  return key.endsWith("_share") ? `${Math.round(v * 100)} %` : String(Math.round(v * 100) / 100);
}

function at(t: number | null | undefined): string | null {
  return typeof t === "number" ? clock(t) : null;
}

function Side({ title, side }: { title: string; side: BaselineSide }) {
  const shown = side.strengths.find((s) => s.frame && s.frame !== "…");
  return (
    <section className="bl-side" aria-label={title}>
      <h3 className="mp-head">{title}</h3>
      {shown?.frame ? (
        <Media episode={side.episode} path={shown.frame} label={`${shown.name}${at(shown.time) ? ` at ${at(shown.time)}` : ""}`} />
      ) : null}
      {side.strengths.length ? (
        <ul className="bl-list">
          {side.strengths.map((s, i) => (
            <li key={`${i}-${s.name}`}>
              <span>{s.name}</span>
              {at(s.time) ? <span className="meta">{at(s.time)}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="meta">No named strengths.</p>
      )}
    </section>
  );
}

export function BaselinePreview({ card }: { card: Card }) {
  const b = baselineOf(card);
  if (!b) return null;
  const keys = [...new Set([...Object.keys(b.old?.measured ?? {}), ...Object.keys(b.new.measured ?? {})])];
  const facts = keys.map((k) => ({
    label: measureWord(k),
    value: b.old ? `${measureValue(k, b.old.measured?.[k])} to ${measureValue(k, b.new.measured?.[k])}` : measureValue(k, b.new.measured?.[k]),
  }));
  return (
    <div className="bl">
      <div className="bl-sides">
        {b.old ? (
          <Side title={`The bar now, ${epShort(b.old.episode)}`} side={b.old} />
        ) : (
          <section className="bl-side" aria-label="No bar yet">
            <h3 className="mp-head">No bar yet</h3>
            <p className="meta">The first video with a motion report becomes the bar.</p>
          </section>
        )}
        <Side title={`This video, ${epShort(b.new.episode)}`} side={b.new} />
      </div>
      {b.new.better?.length ? (
        <div>
          <h3 className="mp-head">Better than the bar</h3>
          <ul className="bl-list">
            {b.new.better.map((x, i) => (
              <li key={`${i}-${x.what}`}>
                <span>{x.what}</span>
                <span className="meta">{[at(x.time), x.against ? `against “${x.against}”` : null].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {facts.length ? <Facts facts={facts} /> : null}
    </div>
  );
}
