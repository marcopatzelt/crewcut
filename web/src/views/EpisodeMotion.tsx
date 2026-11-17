// The motion graphics of an episode (GET /api/episodes/{id}/motion): each motion insert as a tile on the film strip
// with its loop and state, the motion plan's three columns (compact, read-only: a strike happens on the card), and
// after the build the motion report's three lines. Loads again while a job of the episode runs, and at once when one
// of its cards changes (a struck row points the plan card at a new version).
import { Badge } from "@astryxdesign/core/Badge";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { api, ApiError } from "../api/client";
import type { EpisodeMotion, MotionPiece, MotionRetention, MotionReport } from "../api/types";
import { PieceTile, PlanColumns, planLine } from "../components/Motion";
import { jumpToCard, messageOf } from "../store/actions";
import { EMPTY, useUi } from "../store/store";

const POLL_MS = 4000;

type MotionLoad = { status: "loading" | "ready" | "error"; motion: EpisodeMotion | null; error: string | null };

/** True when there is something to show: a plan, a piece or a report. */
export function hasMotion(m: EpisodeMotion | null | undefined): m is EpisodeMotion {
  return Boolean(m && (m.plan || m.pieces.length || m.report));
}

export function useMotion(id: string) {
  const [state, setState] = useState<MotionLoad>({ status: "loading", motion: null, error: null });
  const running = useUi((s) => s.state?.activity.some((a) => a.episode === id && a.status === "running") ?? false);
  const pulse = useUi((s) => {
    const jobs = (s.state?.activity ?? EMPTY).filter((a) => a.episode === id).map((a) => `${a.job}:${a.status}`);
    const cards = Object.values(s.cards)
      .filter((c) => c.episode === id)
      .map((c) => `${c.id}:${c.status}:${c.sha256 ?? ""}`);
    return [...jobs, ...cards].join(",");
  });
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = (seq.current += 1);
    try {
      const m = await api.motion(id);
      const motion: EpisodeMotion = { plan: m?.plan ?? null, pieces: m?.pieces ?? [], report: m?.report ?? null, retention: m?.retention ?? null };
      if (mine === seq.current) setState({ status: "ready", motion, error: null });
    } catch (e) {
      if (mine !== seq.current) return;
      // a server without the motion route, or before the motion pass: nothing to show
      if (e instanceof ApiError && e.status === 404) setState({ status: "ready", motion: null, error: null });
      else setState((s) => ({ ...s, status: s.status === "ready" ? "ready" : "error", error: messageOf(e) }));
    }
  }, [id]);

  useEffect(() => {
    setState({ status: "loading", motion: null, error: null });
  }, [id]);

  useEffect(() => {
    void load();
  }, [load, pulse]);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [running, load]);

  return { ...state, reload: load };
}

/** Where a piece starts, in seconds, when it is known as a number. */
function startOf(p: MotionPiece): number | null {
  return typeof p.start === "number" && Number.isFinite(p.start) ? p.start : null;
}

/** The pieces in the order they play: by start time, then by beat, then as listed. */
export function inOrder(pieces: MotionPiece[]): MotionPiece[] {
  return pieces
    .map((p, i) => ({ p, i }))
    .sort((x, y) => {
      const a = startOf(x.p) ?? (typeof x.p.beat === "number" ? x.p.beat * 1e6 : Infinity);
      const b = startOf(y.p) ?? (typeof y.p.beat === "number" ? y.p.beat * 1e6 : Infinity);
      return a === b ? x.i - y.i : a - b;
    })
    .map((x) => x.p);
}

/** The tiles of the motion inserts, in the order they play. */
export function MotionLane({ pieces }: { pieces: MotionPiece[] }) {
  if (!pieces.length) return null;
  return (
    <ol className="mlane" aria-label="Motion on the strip">
      {inOrder(pieces).map((p) => (
        <PieceTile key={p.id} p={p} />
      ))}
    </ol>
  );
}

/** Where each motion insert sits on the waveform: a quiet band from its start to its end. */
export function MotionBands({ pieces, seconds }: { pieces: MotionPiece[]; seconds: number }) {
  const total = Math.max(1, seconds);
  return (
    <>
      {pieces.map((p) => {
        const s = startOf(p);
        if (s === null) return null;
        const e = typeof p.end === "number" && p.end > s ? p.end : s + 3;
        const from = Math.min(1, Math.max(0, s / total));
        const to = Math.min(1, Math.max(from, e / total));
        return (
          <span
            key={p.id}
            className="wave-band"
            style={{ "--from": from, "--span": to - from } as CSSProperties}
            aria-hidden="true"
          />
        );
      })}
    </>
  );
}

function ReportLines({ report }: { report: MotionReport }) {
  const lines: Array<[string, string | null]> = [
    ["Better", report.better],
    ["Behind", report.behind],
    ["Next", report.next],
  ];
  return (
    <div className="mreport">
      <dl>
        {lines.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v || "Nothing named."}</dd>
          </div>
        ))}
      </dl>
      {report.url ? (
        <a className="mreport-link" href={report.url} target="_blank" rel="noreferrer">
          Read the motion report
        </a>
      ) : null}
    </div>
  );
}

function retentionWords(r: MotionRetention): string | null {
  const s = r.summary;
  if (!s || !s.moments) return null;
  const line = `Retention: ${s.held} of ${s.moments} motion moments held the viewers${s.dropped ? `, ${s.dropped} lost some` : ""}.`;
  return r.unproven ? `${line} A hint, not proof, until it repeats in three videos.` : line;
}

/** The motion panel: the plan's three columns, density and budget, the tiles when there is no cut, the report. */
export function MotionPanel({ motion, inCut }: { motion: EpisodeMotion; inCut: boolean }) {
  const { plan, pieces, report, retention } = motion;
  const open = plan?.card?.status === "open" ? plan.card : null;
  const sub = plan
    ? plan.approved
      ? `Plan v${plan.version}, approved`
      : open
        ? `Plan v${plan.version} waits for your yes`
        : `Plan v${plan.version}`
    : "No motion plan yet";
  const verdict = report?.verdict === "better" ? "Better than the bar" : report?.verdict ? "Not better than the bar yet" : null;
  const kept = retention ? retentionWords(retention) : null;
  return (
    <section className="panel motion-panel" aria-labelledby="motion-heading">
      <div className="panel-head">
        <h2 id="motion-heading">Motion</h2>
        <span className="panel-sub">{sub}</span>
        <div className="panel-chips">
          {verdict ? <Badge variant="neutral" label={verdict} className="chip" /> : null}
          {open ? (
            <button type="button" className="link-button" onClick={() => jumpToCard(open.id)}>
              Show the card
            </button>
          ) : null}
        </div>
      </div>
      {plan ? (
        <>
          <PlanColumns plan={plan} compact />
          <p className="meta mp-line">{planLine(plan)}</p>
        </>
      ) : null}
      {!inCut ? <MotionLane pieces={pieces} /> : null}
      {report ? <ReportLines report={report} /> : null}
      {kept ? <p className="meta">{kept}</p> : null}
    </section>
  );
}
