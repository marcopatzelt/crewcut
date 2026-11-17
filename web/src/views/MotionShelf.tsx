// The "Motion" shelf of the style pack (GET /api/motion/library): your templates first, then the ones that come with
// Crewcut (a small "Crewcut" mark), as a grid of muted sample loops that play while pointed at or focused. Opened, a
// template shows its params with their defaults, the videos that use it and its older versions. Pieces made for one
// video and not kept are listed below. Read-only: a change is a sentence in the chat.
import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Episode, MotionRatchet, ShelfRow } from "../api/types";
import { ErrorLine, Facts, Loading } from "../components/bits";
import { FormatMarks, Loop } from "../components/Motion";
import { paramFacts } from "../components/MotionCards";
import { episodeNumber } from "../lib/format";
import { messageOf, navigate } from "../store/actions";
import { EMPTY, useUi } from "../store/store";

type ShelfLoad =
  | { status: "loading" }
  | { status: "absent" }
  | { status: "error"; error: string }
  | { status: "ready"; rows: ShelfRow[]; ratchet: MotionRatchet | null };

function useShelf() {
  const [state, setState] = useState<ShelfLoad>({ status: "loading" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setState({ status: "loading" });
    Promise.all([api.motionLibrary(), api.motionRatchet().catch(() => null)])
      .then(([lib, ratchet]) => live && setState({ status: "ready", rows: lib?.templates ?? [], ratchet }))
      .catch((e) => {
        if (!live) return;
        // a server without the motion routes: no shelf to show
        if (e instanceof ApiError && e.status === 404) setState({ status: "absent" });
        else setState({ status: "error", error: messageOf(e) });
      });
    return () => {
      live = false;
    };
  }, [tick]);
  return { state, retry: () => setTick((n) => n + 1) };
}

/** "013" for an episode id with a number, else its title or id. */
function epLabel(id: string, episodes: readonly Episode[]): string {
  return episodeNumber(id) ?? episodes.find((e) => e.id === id)?.title ?? id;
}

function epTitle(id: string, episodes: readonly Episode[]): string {
  return episodes.find((e) => e.id === id)?.title ?? id;
}

/** The sample to loop: landscape first. */
function sampleOf(r: ShelfRow): string | null {
  return r.samples.landscape ?? r.samples.stage ?? r.samples.portrait ?? null;
}

function ShelfItem({ r, open, onOpen, episodes }: { r: ShelfRow; open: boolean; onOpen: () => void; episodes: readonly Episode[] }) {
  const [hot, setHot] = useState(false);
  const made = r.made_from?.episode ? `made for ${epLabel(r.made_from.episode, episodes)}` : null;
  const waiting = r.origin === "pack" && r.made_from && !r.approved;
  const name = [
    r.title,
    `version ${r.version}`,
    made,
    r.origin === "app" ? "comes with Crewcut" : null,
    waiting ? "waiting for your yes" : null,
  ]
    .filter(Boolean)
    .join(", ");
  return (
    <li>
      <button
        type="button"
        className="shelf-item"
        aria-expanded={open}
        aria-controls="shelf-detail"
        aria-label={name}
        onClick={onOpen}
        onMouseEnter={() => setHot(true)}
        onMouseLeave={() => setHot(false)}
        onFocus={() => setHot(true)}
        onBlur={() => setHot(false)}
      >
        <span className="shelf-pic">
          <Loop src={sampleOf(r)} poster={r.samples.poster} label="" play="hover" active={hot} />
          {r.origin === "app" ? <span className="glass-tag shelf-mark">Crewcut</span> : null}
          {waiting ? (
            <span className="glass-tag shelf-mark">
              <span className="dot amber" aria-hidden="true" />
              Waiting for your yes
            </span>
          ) : null}
        </span>
        <span className="shelf-words">
          <b className="one-line" title={r.title}>
            {r.title}
          </b>
          <span className="shelf-meta">
            <span className="one-line">{[`v${r.version}`, made].filter(Boolean).join(" · ")}</span>
            <FormatMarks formats={r.formats} />
          </span>
        </span>
      </button>
    </li>
  );
}

function ShelfDetail({ r, episodes }: { r: ShelfRow; episodes: readonly Episode[] }) {
  const facts = paramFacts(r.params);
  const older = (r.versions ?? []).filter((v) => v !== r.version).sort((a, b) => b - a);
  const uses = r.uses;
  const notes = (r.notes ?? []).slice(-3);
  return (
    <div className="shelf-detail" id="shelf-detail" role="region" aria-label={r.title}>
      <div className="shelf-detail-pic">
        <Loop src={sampleOf(r)} poster={r.samples.poster} label={`Sample of ${r.title}`} />
      </div>
      <div className="shelf-detail-words">
        <h3>{r.title}</h3>
        {r.description ? <p className="meta">{r.description}</p> : null}
        <div className="group-label">Params and their defaults</div>
        {facts.length ? <Facts facts={facts} /> : <p className="meta">No params: it always looks the same.</p>}
        {uses ? (
          <>
            <div className="group-label">Videos that use it</div>
            {uses.length ? (
              <ul className="shelf-uses">
                {uses.map((u, i) => (
                  <li key={`${u.episode}-${u.insert ?? i}`}>
                    <button type="button" className="text-button" onClick={() => navigate({ kind: "episode", id: u.episode })}>
                      {epTitle(u.episode, episodes)}
                    </button>
                    <span className="meta">
                      {[u.insert, typeof u.version === "number" ? `pinned to version ${u.version}` : null].filter(Boolean).join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="meta">No video uses it yet.</p>
            )}
          </>
        ) : null}
        <div className="group-label">Versions</div>
        <p className="meta">
          {older.length
            ? `Version ${r.version} is the newest. Older: ${older.map((v) => `version ${v}`).join(", ")}. A plan can pin one, as ${r.name}@${older[0]}.`
            : `Version ${r.version}, the only one.`}
        </p>
        {notes.length ? (
          <>
            <div className="group-label">Notes</div>
            <ul className="shelf-notes">
              {notes.map((n, i) => (
                <li key={i} className="meta">
                  {n.text}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
    </div>
  );
}

function barWords(r: MotionRatchet | null, episodes: readonly Episode[]): string | null {
  if (!r) return null;
  const lessons = r.lessons.length ? ` ${r.lessons.length} ${r.lessons.length === 1 ? "lesson" : "lessons"} so far.` : "";
  if (!r.bar) return `No bar yet: the first video with a motion report becomes it.${lessons}`;
  const strengths = (r.bar.strengths ?? []).map((s) => s.name).slice(0, 3);
  return `The bar is ${epTitle(r.bar.episode, episodes)}${strengths.length ? `: ${strengths.join(", ")}` : ""}.${lessons}`;
}

export function MotionShelf() {
  const { state, retry } = useShelf();
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const [opened, setOpened] = useState<string | null>(null);
  if (state.status === "absent") return null;

  let content;
  if (state.status === "loading") content = <Loading label="Loading the motion templates" />;
  else if (state.status === "error") content = <ErrorLine text={`Couldn't load the motion templates. ${state.error}`} onRetry={retry} />;
  else {
    // the pack's copy wins over the app's of the same name; a promoted piece shows as the template it became
    const shelf = state.rows.filter((r) => r.origin !== "episode" && !r.overridden);
    const oneOffs = state.rows.filter((r) => r.origin === "episode" && !r.promoted_as);
    const open = shelf.find((r) => r.name === opened) ?? null;
    const bar = barWords(state.ratchet, episodes);
    content = (
      <>
        {bar ? <p className="meta shelf-bar">{bar}</p> : null}
        {shelf.length ? (
          <ul className="shelf" aria-label="Motion templates">
            {shelf.map((r) => (
              <ShelfItem
                key={`${r.origin}-${r.name}`}
                r={r}
                open={open?.name === r.name}
                onOpen={() => setOpened((o) => (o === r.name ? null : r.name))}
                episodes={episodes}
              />
            ))}
          </ul>
        ) : (
          <p className="meta">No motion templates yet.</p>
        )}
        {open ? <ShelfDetail r={open} episodes={episodes} /> : null}
        {oneOffs.length ? (
          <>
            <div className="group-label shelf-group">Made for one video, not in your library</div>
            <ul className="shelf-oneoffs">
              {oneOffs.map((r) => (
                <li key={r.name}>
                  <button
                    type="button"
                    className="shelf-oneoff"
                    onClick={() => r.episode && navigate({ kind: "episode", id: r.episode })}
                    aria-label={`${r.title}, made for ${r.episode ? epTitle(r.episode, episodes) : "an episode"}. Open the episode.`}
                  >
                    <span className="shelf-oneoff-pic">
                      <Loop src={null} poster={r.samples.poster} label="" />
                    </span>
                    <span className="shelf-words">
                      <b className="one-line" title={r.title}>
                        {r.title}
                      </b>
                      <span className="meta one-line">
                        {[r.episode ? `made for ${epLabel(r.episode, episodes)}` : null, r.insert].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </>
    );
  }
  return (
    <section className="section shelf-section" aria-labelledby="profile-motion">
      <h2 id="profile-motion">Motion</h2>
      {content}
    </section>
  );
}
