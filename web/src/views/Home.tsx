// The Episodes home, the start view (DESIGN.md rule 2): what needs a yes as two large media cards, every long video
// as a 16:9 thumbnail, the Shorts in 9:16, filter pills on top. Pictures come first; the state is a line under the
// picture, never on the thumbnail. A card opens its episode.
import { Button } from "@astryxdesign/core/Button";
import { Download, Plus } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Activity, Episode, Identity } from "../api/types";
import { StepBar, identityOf } from "../components/bits";
import { ago, clock, countWord, episodeNumber } from "../lib/format";
import { importFootage, navigate, newEpisode } from "../store/actions";
import { EMPTY, useUi, type Filter } from "../store/store";
import { Avatar, SlateFigure } from "../slate/Slate";

const FILTERS: { id: Filter; label: string; test: (e: Episode) => boolean }[] = [
  { id: "all", label: "All", test: () => true },
  { id: "needs", label: "Needs you", test: (e) => e.open_cards > 0 },
  { id: "work", label: "In work", test: (e) => !isDone(e) },
  { id: "long", label: "Long videos", test: (e) => e.kind !== "short" },
  { id: "shorts", label: "Shorts", test: (e) => e.kind === "short" },
  { id: "done", label: "Published", test: (e) => isDone(e) },
];

/** What the crew member does in a step, for the line on a thumbnail: "Editor is cutting, 6 of 10". */
const DOING: Record<string, string> = {
  idea: "looking for topics",
  title: "writing titles",
  proof: "checking facts",
  script: "writing",
  record: "taking in the footage",
  edit: "cutting",
  thumbnail: "drawing thumbnails",
  blog: "writing the blog",
  upload: "uploading",
  results: "reading the results",
};

export function isDone(e: Episode): boolean {
  return e.steps.some((s) => s.id === "upload" && s.status === "done");
}

function current(e: Episode) {
  return e.steps.find((s) => s.id === e.step) ?? e.steps.find((s) => s.status === "working" || s.status === "waiting");
}

/** The episode that takes footage now: the newest long video in work at the record or the edit step. */
export function footageTarget(episodes: readonly Episode[]): Episode | undefined {
  return [...episodes]
    .filter((e) => e.kind !== "short" && !isDone(e) && (e.step === "record" || e.step === "edit"))
    .sort((a, b) => Date.parse(b.updated) - Date.parse(a.updated))[0];
}

function metaOf(e: Episode): string {
  const step = current(e);
  const n = episodeNumber(e.id);
  const what =
    e.kind === "short"
      ? e.mode === "clip" && e.source_episode
        ? `Short from ${episodeNumber(e.source_episode) ?? e.source_episode}`
        : "Short"
      : n
        ? `Episode ${n}`
        : null;
  return [what, step ? `${step.n} of ${e.steps.length} · ${step.label}` : null, ago(e.updated)].filter(Boolean).join(" · ");
}

/** The quiet line under a thumbnail: published when, or the step in work. */
function stateLine(e: Episode): string {
  if (isDone(e)) return `Published ${ago(e.updated)}`;
  const step = current(e);
  return step ? `In work, step ${step.n} of ${e.steps.length}` : "In work";
}

function workerOf(e: Episode, activity: readonly Activity[], team: Identity[] | undefined): { who: Identity; text: string } | null {
  const a = activity.find((x) => x.episode === e.id && x.status === "running");
  if (!a) return null;
  const step = e.steps.find((s) => s.id === a.step);
  const who = identityOf(team, a.identity);
  return { who, text: `${who.name} is ${DOING[a.step] ?? "working"}${step ? `, ${step.n} of ${e.steps.length}` : ""}` };
}

function Blank({ needs }: { needs?: boolean }) {
  return (
    <span className="cover-blank">
      <Avatar who={{ id: "showrunner" }} size="big" state={needs ? "waiting" : "plain"} still />
    </span>
  );
}

function NeedCard({ e }: { e: Episode }) {
  const step = current(e);
  const needs = e.needs;
  const n = episodeNumber(e.id);
  const images = needs?.images?.slice(0, 3) ?? [];
  const ab = needs?.kind === "thumbnail";
  const meta = [n ? `Episode ${n}` : e.kind === "short" ? "Short" : null, step ? `step ${step.n} of ${e.steps.length}` : null]
    .filter(Boolean)
    .join(", ");
  return (
    <button
      type="button"
      className="need"
      onClick={() => navigate({ kind: "episode", id: e.id })}
      aria-label={`${e.title}. ${metaOf(e)}. Needs your yes.`}
    >
      <span className={ab && images.length > 1 ? "need-media pick" : "need-media"} aria-hidden="true">
        {e.cover ? <img src={e.cover} alt="" decoding="async" className="need-ground" /> : <Blank needs />}
        <span className="need-top">
          <span className="glass-tag">
            <span className="dot amber" />
            {needs?.title || "Needs your yes"}
          </span>
          {typeof e.seconds === "number" ? <span className="glass-tag">{clock(e.seconds)}</span> : null}
        </span>
        {images.length ? (
          <span className={ab ? "need-minis ab" : "need-minis"}>
            {images.map((url, i) => (
              <span className="mini" key={`${i}-${url}`}>
                <img src={url} alt="" decoding="async" />
                {ab ? <span className="mini-letter">{String.fromCharCode(65 + i)}</span> : null}
              </span>
            ))}
          </span>
        ) : null}
      </span>
      <span className="need-info">
        <span className="need-words">
          <span className="need-title" title={e.title}>
            {e.title}
          </span>
          <span className="need-meta">{meta}</span>
        </span>
        <StepBar steps={e.steps} />
      </span>
    </button>
  );
}

function EpisodeCard({ e, worker }: { e: Episode; worker: { who: Identity; text: string } | null }) {
  return (
    <button
      type="button"
      className="ep-card"
      onClick={() => navigate({ kind: "episode", id: e.id })}
      aria-label={`${e.title}. ${metaOf(e)}.`}
    >
      <span className="thumb" aria-hidden="true">
        {e.cover ? <img src={e.cover} alt="" decoding="async" /> : <Blank />}
        {worker ? (
          <span className="thumb-work">
            <Avatar who={worker.who} size="small" state="working" still />
            {worker.text}
          </span>
        ) : typeof e.seconds === "number" ? (
          <span className="len">{clock(e.seconds)}</span>
        ) : null}
      </span>
      <span className="ep-card-title" title={e.title}>
        {e.title}
      </span>
      <span className="ep-card-meta">{stateLine(e)}</span>
    </button>
  );
}

function ShortCard({ e }: { e: Episode }) {
  const done = isDone(e);
  return (
    <button
      type="button"
      className="short-card"
      onClick={() => navigate({ kind: "episode", id: e.id })}
      aria-label={`${e.title}. ${metaOf(e)}.`}
    >
      <span className="short-pic" aria-hidden="true">
        {e.cover ? <img src={e.cover} alt="" decoding="async" /> : <Blank />}
        {done ? null : <span className="glass-tag">In work</span>}
        {/* The app writes the title over the frame: the frames carry no words of their own. */}
        <span className="short-title">{e.title}</span>
      </span>
    </button>
  );
}

function ImportButton({ target }: { target: Episode }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button
        label="Import footage"
        variant="secondary"
        icon={<Download size={16} aria-hidden="true" />}
        tooltip={`Into ${target.title}`}
        onClick={() => input.current?.click()}
      />
      <input
        ref={input}
        type="file"
        multiple
        accept="video/*,audio/*"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(ev) => {
          const files = Array.from(ev.target.files ?? []);
          ev.target.value = "";
          void importFootage(target.id, files);
        }}
      />
    </>
  );
}

/**
 * How many columns a grid has right now, read from its laid-out CSS (container queries set them), so the home can
 * show one complete row. Without layout (tests) it keeps the widest count.
 */
function useColumns(widest: number, present: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [cols, setCols] = useState(widest);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof getComputedStyle !== "function") return;
    const read = () => {
      const n = getComputedStyle(el).gridTemplateColumns.split(" ").filter(Boolean).length;
      if (n > 0) setCols(n);
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [present]);
  return [ref, cols] as const;
}

function headLine(episodes: readonly Episode[]): string {
  if (!episodes.length) return "Nothing here yet. Start with one sentence.";
  const needs = episodes.filter((e) => e.open_cards > 0).length;
  const moving = episodes.filter((e) => !isDone(e) && e.open_cards === 0).length;
  const first = needs ? `${countWord(needs)} ${needs === 1 ? "needs" : "need"} your yes.` : "Nothing needs your yes.";
  const second = moving ? (needs ? " Everything else is moving." : " The crew keeps going.") : "";
  return first + second;
}

export function Home() {
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const team = useUi((s) => s.state?.team);
  const boot = useUi((s) => s.boot);
  const filter = useUi((s) => (s.view.kind === "episodes" ? s.view.filter ?? "all" : "all"));

  const shown = useMemo(() => {
    const test = FILTERS.find((f) => f.id === filter)?.test ?? (() => true);
    return [...episodes].filter(test).sort((a, b) => Date.parse(b.updated) - Date.parse(a.updated));
  }, [episodes, filter]);
  const needs = shown.filter((e) => e.open_cards > 0);
  const allLong = shown.filter((e) => e.open_cards === 0 && e.kind !== "short");
  const allShorts = shown.filter((e) => e.open_cards === 0 && e.kind === "short");
  // "All" shows one complete row of each; a filter shows everything.
  const [gridRef, gridCols] = useColumns(4, allLong.length > 0);
  const [shortsRef, shortsCols] = useColumns(7, allShorts.length > 0);
  const long = filter === "all" ? allLong.slice(0, gridCols) : allLong;
  const shorts = filter === "all" ? allShorts.slice(0, shortsCols) : allShorts;
  const everyShort = episodes.filter((e) => e.kind === "short");
  const from = new Set(everyShort.map((e) => e.source_episode).filter(Boolean)).size;
  const target = footageTarget(episodes);

  return (
    <main className="main home" aria-label="Episodes">
      <div className="home-scroll">
        <header className="home-head">
          <div>
            <h1>Episodes</h1>
            <p className="sub">{boot === "ready" ? headLine(episodes) : " "}</p>
          </div>
          <div className="home-actions">
            {target ? <ImportButton target={target} /> : null}
            <Button
              label="New episode"
              variant="primary"
              icon={<Plus size={16} aria-hidden="true" />}
              onClick={newEpisode}
            />
          </div>
        </header>

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
                onClick={() => navigate(f.id === "all" ? { kind: "episodes" } : { kind: "episodes", filter: f.id }, { replace: true })}
              >
                {f.id === "needs" ? <span className="dot amber" aria-hidden="true" /> : null}
                {f.label}{" "}
                <span className="pill-count">{count}</span>
              </button>
            );
          })}
        </div>

        {episodes.length === 0 ? (
          <div className="home-empty">
            <SlateFigure state="idle" size={88} />
            <p>No episodes yet. Start one with New episode.</p>
          </div>
        ) : shown.length === 0 ? (
          <p className="meta">Nothing here right now.</p>
        ) : null}

        {needs.length ? (
          <section className="home-section" aria-labelledby="needs-heading">
            <div className="section-head">
              <h2 id="needs-heading">Needs you</h2>
            </div>
            <div className="needs">
              {needs.map((e) => (
                <NeedCard key={e.id} e={e} />
              ))}
            </div>
          </section>
        ) : null}

        {long.length ? (
          <section className="home-section" aria-labelledby="grid-heading">
            <div className="section-head">
              <h2 id="grid-heading">{filter === "done" ? "Published" : filter === "work" ? "In work" : "In work and published"}</h2>
              {allLong.length > long.length ? (
                <button type="button" className="more-link" onClick={() => navigate({ kind: "episodes", filter: "long" })}>
                  Show all {allLong.length}
                </button>
              ) : (
                <span className="section-note">Newest first</span>
              )}
            </div>
            <div className="ep-grid" ref={gridRef}>
              {long.map((e) => (
                <EpisodeCard key={e.id} e={e} worker={workerOf(e, activity, team)} />
              ))}
            </div>
          </section>
        ) : null}

        {shorts.length ? (
          <section className="home-section" aria-labelledby="shorts-heading">
            <div className="section-head">
              <h2 id="shorts-heading">Shorts</h2>
              <span className="section-note">
                {from
                  ? `${everyShort.length} made from ${from === 1 ? "one episode" : `${countWord(from).toLowerCase()} episodes`}`
                  : `${everyShort.length} in all`}
              </span>
              {allShorts.length > shorts.length ? (
                <button type="button" className="more-link" onClick={() => navigate({ kind: "episodes", filter: "shorts" })}>
                  Show all {allShorts.length}
                </button>
              ) : null}
            </div>
            <div className="shorts" ref={shortsRef}>
              {shorts.map((e) => (
                <ShortCard key={e.id} e={e} />
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
