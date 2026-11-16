// All episodes and Shorts as large cards with their cover (DESIGN.md rule 2): filter pills on top, groups by time,
// a grid instead of a list. The sidebar keeps the compact list for switching; this is the overview.
import { RectangleVertical } from "lucide-react";
import { useMemo, useState } from "react";
import type { Episode } from "../api/types";
import { StepBar } from "../components/bits";
import { ago } from "../lib/format";
import { Avatar } from "../slate/Slate";
import { navigate } from "../store/actions";
import { useUi } from "../store/store";
import { Page } from "./ReadOnlyViews";

const EMPTY: Episode[] = [];

type Filter = "all" | "long" | "shorts" | "needs" | "work" | "done";

const FILTERS: { id: Filter; label: string; test: (e: Episode) => boolean }[] = [
  { id: "all", label: "All", test: () => true },
  { id: "long", label: "Long videos", test: (e) => e.kind !== "short" },
  { id: "shorts", label: "Shorts", test: (e) => e.kind === "short" },
  { id: "needs", label: "Needs you", test: (e) => e.open_cards > 0 },
  { id: "work", label: "In work", test: (e) => !isDone(e) },
  { id: "done", label: "Published", test: (e) => isDone(e) },
];

function isDone(e: Episode): boolean {
  return e.steps.some((s) => s.id === "upload" && s.status === "done");
}

function current(e: Episode) {
  return e.steps.find((s) => s.id === e.step) ?? e.steps.find((s) => s.status === "working" || s.status === "waiting");
}

/** Today, this week, earlier: like a photo library, the newest first. */
function groupOf(updated: string, now: number): string {
  const t = Date.parse(updated);
  if (!Number.isFinite(t)) return "Earlier";
  const days = (now - t) / 86_400_000;
  if (days < 1 && new Date(t).toDateString() === new Date(now).toDateString()) return "Today";
  if (days < 7) return "This week";
  return "Earlier";
}

function number(id: string): string | null {
  const m = /^(\d{3})-/.exec(id);
  return m ? m[1] ?? null : null;
}

function EpisodeCard({ e }: { e: Episode }) {
  const step = current(e);
  const short = e.kind === "short";
  const n = number(e.id);
  const meta = [
    short ? (e.mode === "clip" && e.source_episode ? `Short from ${number(e.source_episode) ?? e.source_episode}` : "Short") : n ? `Episode ${n}` : null,
    step ? `${step.n} of ${e.steps.length} · ${step.label}` : null,
    ago(e.updated),
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <button
      type="button"
      className={short ? "ep-card is-short" : "ep-card"}
      onClick={() => navigate({ kind: "episode", id: e.id })}
      aria-label={`${e.title}. ${meta}.${e.open_cards ? " Needs your yes." : ""}`}
    >
      <span className="ep-cover" aria-hidden="true">
        {e.cover ? (
          <img src={e.cover} alt="" loading="lazy" />
        ) : (
          <span className="ep-cover-blank">
            <Avatar who={{ id: "showrunner" }} size="big" state={isDone(e) ? "done" : "plain"} still />
          </span>
        )}
        {short ? (
          <span className="ep-chip">
            <RectangleVertical size={14} aria-hidden="true" />
            Short
          </span>
        ) : null}
        {e.open_cards ? (
          <span className="ep-chip needs">
            <span className="ep-dot" />
            Needs you
          </span>
        ) : null}
      </span>
      <span className="ep-card-text">
        <span className="ep-card-title">{e.title}</span>
        <span className="ep-card-meta one-line">{meta}</span>
        <StepBar steps={e.steps} />
      </span>
    </button>
  );
}

export function EpisodesGrid() {
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const [filter, setFilter] = useState<Filter>("all");
  const shown = useMemo(() => {
    const test = FILTERS.find((f) => f.id === filter)?.test ?? (() => true);
    return [...episodes].filter(test).sort((a, b) => Date.parse(b.updated) - Date.parse(a.updated));
  }, [episodes, filter]);
  const groups = useMemo(() => {
    const now = Date.now();
    const out: { name: string; items: Episode[] }[] = [];
    for (const e of shown) {
      const name = groupOf(e.updated, now);
      const g = out.find((x) => x.name === name);
      if (g) g.items.push(e);
      else out.push({ name, items: [e] });
    }
    return out;
  }, [shown]);

  return (
    <Page wide label="All episodes" title="Episodes" sub="Every video and Short, newest first. Open one to see its chat.">
      <div className="pills" role="group" aria-label="Show">
        {FILTERS.map((f) => {
          const count = episodes.filter(f.test).length;
          if (f.id !== "all" && count === 0) return null;
          return (
            <button
              key={f.id}
              type="button"
              className="pill"
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
              <span className="pill-count">{count}</span>
            </button>
          );
        })}
      </div>
      {episodes.length === 0 ? (
        <p className="meta">No episodes yet. Say an idea in the composer below.</p>
      ) : shown.length === 0 ? (
        <p className="meta">Nothing here right now.</p>
      ) : (
        groups.map((g) => (
          <section key={g.name} className="ep-group" aria-label={g.name}>
            <h2 className="group-title">{g.name}</h2>
            <div className="ep-grid">
              {g.items.map((e) => (
                <EpisodeCard key={e.id} e={e} />
              ))}
            </div>
          </section>
        ))
      )}
    </Page>
  );
}
