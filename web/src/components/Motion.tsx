// Shared pieces of the motion graphics views: a muted loop that plays only in view (or while pointed at), the format
// marks, plain words for states and sources, and the three columns of a motion plan. The motion-plan card makes the
// rows tappable ("not this one"); the episode view shows the same columns read-only and compact.
import { Film, RectangleHorizontal, RectangleVertical, Square } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type {
  Card,
  MotionBeat,
  MotionNew,
  MotionPiece,
  MotionPlanData,
  MotionPlanView,
  MotionState,
  MotionUpgrade,
  StyleFrameData,
  MotionTemplate,
  BaselineData,
  WordAnchor,
} from "../api/types";
import { clock, usd, usdShort } from "../lib/format";
import { reducedMotion } from "../lib/platform";

// ---------- words ----------

/** "Number roll" from "number_roll@2"; a custom piece keeps its id. */
export function pieceName(scene: string | null | undefined): string {
  if (!scene) return "Motion";
  const base = scene.split("@")[0] ?? scene;
  const words = base.replace(/[_-]+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : scene;
}

const STATE_WORD: Record<MotionState, string> = {
  planned: "Planned",
  "style frame": "Style frame",
  building: "Building",
  "in review": "In review",
  done: "Done",
};

export function stateWord(s: MotionState | string): string {
  return STATE_WORD[s as MotionState] ?? s;
}

/** The reason of an upgrade, in words: "Lesson 2026-11-17-3", "Reference ref-012", "Behind the bar". */
export function sourceWords(source: MotionUpgrade["source"]): string {
  if (!source) return "";
  const ref = source.ref ? ` ${source.ref}` : "";
  switch (source.kind) {
    case "lesson":
      return `Lesson${ref}`;
    case "reference":
      return `Reference${ref}`;
    case "baseline":
      return "Behind the bar";
    case "retention":
      return `Retention${ref}`;
    default:
      return `${source.kind}${ref}`;
  }
}

/** Where a piece sits in the cut: "0:41", "on “thirty”", "beat 3", or nothing. */
export function atWords(at: number | WordAnchor | null | undefined, beat?: number | null): string {
  if (typeof at === "number" && Number.isFinite(at)) return clock(at);
  if (at && typeof at === "object" && typeof at.word === "string") return `on “${at.word}”`;
  return typeof beat === "number" ? `beat ${beat}` : "";
}

/** The first letter up: the server writes its density line in lower case. */
function sentence(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** The money of a plan with the cap per video ($2 long, $0.50 a Short): "GPU about $0.30, cap $2 for this video". */
export function moneyWords(plan: Pick<MotionPlanData, "estimate_usd" | "cap_usd" | "budget" | "short">): string {
  const where = plan.short ? "for this Short" : "for this video";
  if (typeof plan.cap_usd === "number") {
    const est = plan.estimate_usd ?? 0;
    const spend = est > 0 ? `GPU about ${usd(est)}` : "No GPU money";
    return `${spend}, cap ${usdShort(plan.cap_usd)} ${where}`;
  }
  return plan.budget ? sentence(plan.budget) : "";
}

/** Density and budget in one line. */
export function planLine(plan: Pick<MotionPlanData, "density" | "estimate_usd" | "cap_usd" | "budget" | "short">): string {
  return [plan.density ? sentence(plan.density) : null, moneyWords(plan) || null].filter(Boolean).join(" · ");
}

/** The motion moments a plan shows: shelf rows, the beats of new pieces and of upgrades, none struck. */
export function moments(plan: Pick<MotionPlanData, "columns">): number {
  const c = plan.columns;
  const live = (b: MotionBeat) => !b.struck;
  return (
    c.a.filter(live).length +
    c.b.filter((n) => !n.struck).reduce((n, x) => n + x.beats.filter(live).length, 0) +
    c.c.filter((u) => !u.struck).reduce((n, x) => n + x.beats.filter(live).length, 0)
  );
}

// ---------- card data, read defensively (every field may be missing) ----------

function obj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function list<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

export function motionPlanOf(card: Card): MotionPlanData | null {
  const p = obj(card.data?.motion_plan);
  if (!p) return null;
  const cols = obj(p.columns) ?? {};
  return {
    ...(p as unknown as MotionPlanData),
    columns: {
      a: list<MotionBeat>(cols.a),
      b: list<MotionNew>(cols.b).map((x) => ({ ...x, beats: list<MotionBeat>(x.beats) })),
      c: list<MotionUpgrade>(cols.c).map((x) => ({ ...x, beats: list<MotionBeat>(x.beats) })),
    },
    quiet: list<MotionBeat>(p.quiet),
    density: typeof p.density === "string" ? p.density : null,
    budget: typeof p.budget === "string" ? p.budget : null,
    estimate_usd: typeof p.estimate_usd === "number" ? p.estimate_usd : null,
    cap_usd: typeof p.cap_usd === "number" ? p.cap_usd : typeof card.data?.cap_usd === "number" ? card.data.cap_usd : null,
    short: Boolean(p.short),
  };
}

export function styleFrameOf(card: Card): StyleFrameData | null {
  const d = card.data;
  const frames = list<StyleFrameData["frames"][number]>(d?.frames).filter((f) => obj(f) && typeof f.ours_url === "string");
  if (!frames.length) return null;
  return { insert: String(d?.insert ?? ""), round: typeof d?.round === "number" ? d.round : 1, frames };
}

export function templateOf(card: Card): MotionTemplate | null {
  const t = obj(card.data?.template);
  if (!t || typeof t.name !== "string") return null;
  return {
    ...(t as unknown as MotionTemplate),
    title: typeof t.title === "string" && t.title ? t.title : pieceName(t.name),
    formats: list<string>(t.formats),
    params: obj(t.params) ?? {},
    samples: (obj(t.samples) as Record<string, string> | null) ?? {},
  };
}

export function baselineOf(card: Card): BaselineData | null {
  const n = obj(card.data?.new);
  if (!n || typeof n.episode !== "string") return null;
  const side = (s: Record<string, unknown>) => ({
    ...(s as unknown as BaselineData["new"]),
    strengths: list<BaselineData["new"]["strengths"][number]>(s.strengths),
    better: list<NonNullable<BaselineData["new"]["better"]>[number]>(s.better),
    measured: (obj(s.measured) as Record<string, number | null> | null) ?? {},
  });
  const o = obj(card.data?.old);
  return { old: o && typeof o.episode === "string" ? side(o) : null, new: side(n) };
}

// ---------- a muted loop ----------

function start(v: HTMLVideoElement) {
  try {
    const p = v.play() as Promise<void> | undefined;
    if (p && typeof p.catch === "function") p.catch(() => undefined);
  } catch {
    // the browser refused to play; the first frame stays
  }
}

function stop(v: HTMLVideoElement) {
  try {
    v.pause();
  } catch {
    // nothing to stop
  }
}

/**
 * A sample loop: muted, never with sound or controls. `play="view"` plays while at least half of it is on screen,
 * `"hover"` while the parent says it is pointed at or focused (`active`), `"never"` shows the still. With reduced
 * motion only the poster shows. An empty `label` makes it decorative (the row around it has the name).
 */
export function Loop({
  src,
  poster,
  label,
  play = "view",
  active,
  className,
}: {
  src: string | null | undefined;
  poster: string | null | undefined;
  label: string;
  play?: "view" | "hover" | "never";
  active?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [videoFailed, setVideoFailed] = useState(false);
  const [posterFailed, setPosterFailed] = useState(false);
  const moving = Boolean(src) && !videoFailed && play !== "never" && !reducedMotion();
  const cls = ["loop", className].filter(Boolean).join(" ");
  const hidden = label ? undefined : true;

  useEffect(() => {
    const v = ref.current;
    if (!v || !moving || play !== "view" || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) start(v);
          else if (!v.paused) stop(v);
        }
      },
      { threshold: 0.5 },
    );
    io.observe(v);
    return () => io.disconnect();
  }, [moving, play, src]);

  useEffect(() => {
    const v = ref.current;
    if (!v || !moving || play !== "hover") return;
    if (active) start(v);
    else if (!v.paused) stop(v);
  }, [active, moving, play]);

  if (moving && src) {
    return (
      <video
        ref={ref}
        className={cls}
        src={src}
        poster={poster ?? undefined}
        muted
        loop
        playsInline
        preload="metadata"
        aria-label={label || undefined}
        aria-hidden={hidden}
        data-loop="moving"
        onError={() => setVideoFailed(true)}
      />
    );
  }
  if (poster && !posterFailed) {
    return (
      <img
        className={cls}
        src={poster}
        alt={label}
        loading="lazy"
        decoding="async"
        data-loop="still"
        onError={() => setPosterFailed(true)}
      />
    );
  }
  if (src && !videoFailed) {
    // reduced motion without a poster: the first frame of the loop, standing still
    return (
      <video
        className={cls}
        src={src}
        muted
        playsInline
        preload="metadata"
        aria-label={label || undefined}
        aria-hidden={hidden}
        data-loop="still"
        onError={() => setVideoFailed(true)}
      />
    );
  }
  return (
    <span className={`${cls} loop-blank`} role={label ? "img" : undefined} aria-label={label || undefined} aria-hidden={hidden}>
      <Film size={16} aria-hidden="true" />
    </span>
  );
}

// ---------- format marks ----------

const FORMAT_WORD: Record<string, string> = { landscape: "Landscape 16:9", portrait: "Portrait 9:16", stage: "Square" };

export function formatWord(f: string): string {
  return FORMAT_WORD[f] ?? f;
}

/** Small outlines for the formats a template renders in, with the words for screen readers and the tooltip. */
export function FormatMarks({ formats }: { formats: string[] }) {
  if (!formats.length) return null;
  const words = formats.map(formatWord).join(", ");
  return (
    <span className="formats" title={words}>
      {formats.map((f) =>
        f === "portrait" ? (
          <RectangleVertical key={f} size={14} aria-hidden="true" />
        ) : f === "landscape" ? (
          <RectangleHorizontal key={f} size={14} aria-hidden="true" />
        ) : (
          <Square key={f} size={12} aria-hidden="true" />
        ),
      )}
      <span className="sr-only">{words}</span>
    </span>
  );
}

// ---------- the three columns of a motion plan ----------

type Plan = Pick<MotionPlanData, "columns"> | Pick<MotionPlanView, "columns">;

/** "0:12" or "0:12, 0:40" for the beats a new piece or an upgrade shows in. */
function times(beats: MotionBeat[]): string {
  return beats.map((b) => b.time).filter(Boolean).join(", ");
}

function Row({
  struck,
  name,
  tip,
  onToggle,
  busy,
  disabled,
  children,
}: {
  struck: boolean;
  name: string;
  tip: string;
  onToggle?: () => void;
  busy: boolean;
  disabled: boolean;
  children: ReactNode;
}) {
  const cls = ["mp-row", struck ? "struck" : null].filter(Boolean).join(" ");
  if (!onToggle) {
    return (
      <div className={cls} title={tip}>
        {children}
        {struck ? <span className="mp-mark">Struck</span> : null}
      </div>
    );
  }
  return (
    <button
      type="button"
      className={cls}
      aria-pressed={struck}
      aria-busy={busy || undefined}
      aria-label={`Not this one: ${name}`}
      title={struck ? "Struck. Tap to bring it back." : `${tip}. Tap to strike it.`}
      disabled={disabled}
      onClick={onToggle}
    >
      {children}
      {struck ? <span className="mp-mark">Struck</span> : null}
    </button>
  );
}

function Column({ title, count, empty, children }: { title: string; count: number; empty: string; children: ReactNode }) {
  return (
    <div className="mp-col">
      <h3 className="mp-head">
        {title}
        <span className="mp-count">{count}</span>
      </h3>
      {count ? <ul className="mp-list">{children}</ul> : <p className="meta">{empty}</p>}
    </div>
  );
}

/**
 * (a) what we have that fits, as loops of the shelf pieces; (b) what we build new, as the brief's line; (c) what makes
 * this video clearly better than the last one, with the reason. With `onStrike` a tap on a row strikes it or brings it
 * back; without it the columns are read-only (the episode view).
 */
export function PlanColumns({
  plan,
  onStrike,
  busy = null,
  disabled = false,
  compact = false,
}: {
  plan: Plan;
  onStrike?: (row: string, struck: boolean) => void;
  busy?: string | null;
  disabled?: boolean;
  compact?: boolean;
}) {
  const { a, b, c } = plan.columns;
  const toggle = (row: string, struck: boolean) => (onStrike ? () => onStrike(row, !struck) : undefined);
  const off = disabled || busy !== null;
  const chosen = c.filter((u) => u.chosen);
  const later = c.filter((u) => !u.chosen);
  return (
    <div className={compact ? "mp-cols compact" : "mp-cols"}>
      <Column title="What we have that fits" count={a.length} empty="Nothing on the shelf fits this video.">
        {a.map((r) => {
          const name = pieceName(r.piece);
          return (
            <li key={r.row}>
              <Row
                struck={r.struck}
                name={`${r.time} ${name}, ${r.purpose ?? ""}`}
                tip={r.picture ?? name}
                onToggle={toggle(r.row, r.struck)}
                busy={busy === r.row}
                disabled={off}
              >
                <span className="mp-pic">
                  <Loop src={r.media?.loop} poster={r.media?.poster} label="" play={compact ? "never" : "view"} />
                </span>
                <span className="mp-words">
                  <b className="one-line">
                    {r.time} · {name}
                  </b>
                  {r.purpose ? <span className="mp-sub">{r.purpose}</span> : null}
                </span>
              </Row>
            </li>
          );
        })}
      </Column>
      <Column title={compact ? "New for this video" : "What we build new for this video"} count={b.length} empty="Nothing new this time.">
        {b.map((n) => {
          const meta = [
            times(n.beats),
            n.effort ? `effort ${n.effort}` : null,
            n.plates ? `${n.plates} ${n.plates === 1 ? "plate" : "plates"}` : null,
            n.cost_usd > 0 ? `about ${usd(n.cost_usd)}` : null,
            typeof n.cap_usd === "number" ? `cap ${usd(n.cap_usd)}` : null,
          ].filter(Boolean);
          return (
            <li key={n.row}>
              <Row
                struck={n.struck}
                name={n.brief ?? n.id}
                tip={n.why_new ?? n.brief ?? n.id}
                onToggle={toggle(n.row, n.struck)}
                busy={busy === n.row}
                disabled={off}
              >
                <span className="mp-words">
                  <b>{n.brief ?? n.id}</b>
                  {meta.length ? <span className="mp-sub">{meta.join(" · ")}</span> : null}
                  {n.why_new && !compact ? <span className="mp-why">{n.why_new}</span> : null}
                </span>
              </Row>
            </li>
          );
        })}
      </Column>
      <Column
        title={compact ? "Better than the last one" : "What makes this video clearly better than the last one"}
        count={c.length}
        empty="No upgrade yet."
      >
        {chosen.map((u) => {
          const meta = [
            sourceWords(u.source),
            times(u.beats),
            u.effort ? `effort ${u.effort}` : null,
            u.cost_usd > 0 ? `about ${usd(u.cost_usd)}` : null,
          ].filter(Boolean);
          return (
            <li key={u.row}>
              <Row
                struck={u.struck}
                name={u.upgrade}
                tip={sourceWords(u.source) || u.upgrade}
                onToggle={toggle(u.row, u.struck)}
                busy={busy === u.row}
                disabled={off}
              >
                <span className="mp-words">
                  <b>{u.upgrade}</b>
                  {meta.length ? <span className="mp-sub">{meta.join(" · ")}</span> : null}
                </span>
              </Row>
            </li>
          );
        })}
        {later.map((u) => (
          <li key={u.row}>
            <div className="mp-row later" title={sourceWords(u.source) || undefined}>
              <span className="mp-words">
                <b>{u.upgrade}</b>
                <span className="mp-sub">{["For a later video", sourceWords(u.source)].filter(Boolean).join(" · ")}</span>
              </span>
            </div>
          </li>
        ))}
      </Column>
    </div>
  );
}

// ---------- a motion piece as a tile ----------

/** A motion insert on the film strip: its loop (or style frame), its state on a tag, where it sits and what it is. */
export function PieceTile({ p }: { p: MotionPiece }) {
  const name = p.kind === "custom" ? p.brief || p.id : pieceName(p.scene);
  const at = atWords(p.start, p.beat);
  const state = stateWord(p.state);
  const kind = p.kind === "custom" ? "Made for this video" : p.transparent ? "Overlay" : "Full frame";
  return (
    <li className={`mtile is-${p.state.replace(/\s+/g, "-")}`} aria-label={`${[at, name].filter(Boolean).join(", ")}. ${state}.`}>
      <span className="mtile-pic">
        <Loop src={p.loop} poster={p.poster} label="" />
        <span className="glass-tag mtile-state">
          {p.state === "style frame" || p.state === "in review" ? <span className="dot amber" aria-hidden="true" /> : null}
          {p.state === "building" ? <span className="dot mint" aria-hidden="true" /> : null}
          {state}
        </span>
      </span>
      <span className="mtile-words">
        <b className="one-line" title={name}>
          {name}
        </b>
        <span className="mtile-meta one-line">{[at, kind].filter(Boolean).join(" · ")}</span>
      </span>
    </li>
  );
}
