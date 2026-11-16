// The media of an episode, first (DESIGN.md rule 2): the thumbnail variants with a phone-size check, the cut as a film
// strip with its waveform and the Critic's notes, the 3D scenes with their render tiles, and the rented GPU.
// Everything comes from GET /api/episodes/{id}/media; what is missing shows an honest empty line, never a stand-in
// picture. The media load again while a job of the episode runs.
import { Badge } from "@astryxdesign/core/Badge";
import { Button } from "@astryxdesign/core/Button";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Cpu } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { api, ApiError } from "../api/client";
import type { Card, EpisodeMedia, MediaCut, MediaGpu, MediaScenes, MediaThumb } from "../api/types";
import { ErrorLine, Loading } from "../components/bits";
import { clock, usd } from "../lib/format";
import { accept, messageOf, sayTo, upsertCard } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { Avatar, SlateFigure } from "../slate/Slate";

/** The sentence the GPU card's Stop sends: the crew stops the machine and keeps what is done (rule 3). */
export const STOP_GPU = "Stop the rented GPU now. Keep the frames that are done.";

const EMPTY_MEDIA: EpisodeMedia = { thumbnails: [], cut: null, scenes: null, gpu: null };
const POLL_MS = 4000;

type MediaState = { status: "loading" | "ready" | "error"; media: EpisodeMedia; error: string | null };

/**
 * Loads the media of one episode. Again every few seconds while one of its jobs runs, and at once when its jobs or
 * cards change. A server without the media endpoint (404) counts as "no media yet".
 */
export function useMedia(id: string) {
  const [state, setState] = useState<MediaState>({ status: "loading", media: EMPTY_MEDIA, error: null });
  const running = useUi((s) => s.state?.activity.some((a) => a.episode === id && a.status === "running") ?? false);
  const pulse = useUi((s) => {
    const jobs = (s.state?.activity ?? EMPTY).filter((a) => a.episode === id).map((a) => `${a.job}:${a.status}`);
    const cards = Object.values(s.cards).filter((c) => c.episode === id).map((c) => `${c.id}:${c.status}`);
    return [...jobs, ...cards].join(",");
  });
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = (seq.current += 1);
    try {
      const media = await api.media(id);
      if (mine === seq.current) setState({ status: "ready", media: { ...EMPTY_MEDIA, ...media }, error: null });
    } catch (e) {
      if (mine !== seq.current) return;
      if (e instanceof ApiError && e.status === 404) setState({ status: "ready", media: EMPTY_MEDIA, error: null });
      else setState((s) => ({ ...s, status: s.status === "ready" ? "ready" : "error", error: messageOf(e) }));
    }
  }, [id]);

  useEffect(() => {
    setState({ status: "loading", media: EMPTY_MEDIA, error: null });
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

function Head({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="panel-head">
      <h2>{title}</h2>
      {sub ? <span className="panel-sub">{sub}</span> : null}
      {children ? <div className="panel-chips">{children}</div> : null}
    </div>
  );
}

// ---------- thumbnails ----------

/** The choice a thumbnail card expects for a variant: the option that names it, else its place in the list. */
export function choiceFor(card: Card | undefined, thumbs: MediaThumb[], t: MediaThumb): number {
  const options = card?.options ?? [];
  const i = options.findIndex((o) => {
    const w = o.trim().toLowerCase();
    return w === t.id.toLowerCase() || w.startsWith(`${t.id.toLowerCase()} `) || w === t.label.toLowerCase();
  });
  return i >= 0 ? i : thumbs.indexOf(t);
}

function PhoneCheck({ pick, others }: { pick: MediaThumb; others: string[] }) {
  return (
    <figure className="phone-check">
      <div className="phone" aria-hidden="true">
        <div className="phone-screen">
          {[pick.url, ...others].slice(0, 3).map((url, i) => (
            <span className="feed-item" key={`${i}-${url}`}>
              <img src={url} alt="" loading="lazy" />
              <i />
              <i />
            </span>
          ))}
        </div>
      </div>
      <figcaption>{pick.id} in your feed, at phone size</figcaption>
    </figure>
  );
}

export function ThumbnailPanel({ episode, thumbs }: { episode: string; thumbs: MediaThumb[] }) {
  const cardId = thumbs.find((t) => typeof t.card === "number")?.card ?? null;
  const card = useUi((s) => (cardId !== null ? s.cards[cardId] : undefined));
  const team = useUi((s) => s.state?.team);
  const covers = useUi((s) => s.state?.episodes ?? EMPTY)
    .filter((e) => e.id !== episode && e.kind !== "short" && e.cover)
    .map((e) => e.cover as string);
  const recommended = thumbs.find((t) => t.recommended) ?? thumbs.find((t) => t.picked) ?? thumbs[0];
  const [selected, setSelected] = useState<string | undefined>(recommended?.id);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const picked = thumbs.find((t) => t.picked);
  const open = cardId !== null && (card ? card.status === "open" : true);
  const shown = thumbs.slice(0, 3);
  const pick = shown.find((t) => t.id === selected) ?? shown[0];
  const designer = team?.find((t) => t.id === "designer") ?? { id: "designer" };

  async function use(t: MediaThumb) {
    if (cardId === null || busy) return;
    setBusy(t.id);
    setError(null);
    const choice = choiceFor(card, thumbs, t);
    try {
      if (card) await accept(card, choice);
      else upsertCard({ ...(await api.accept(cardId, choice)), choice });
    } catch (e) {
      setError(`Couldn't send your pick. ${messageOf(e)}`);
    } finally {
      setBusy(null);
    }
  }

  const sub = open
    ? "Pick one. YouTube can test the other later."
    : picked
      ? `${picked.id} is in use.`
      : "The Designer's newest round.";

  return (
    <section className="panel thumbs-panel" aria-labelledby={`thumbs-${episode}`}>
      <div className="panel-head">
        <h2 id={`thumbs-${episode}`}>Thumbnail</h2>
        <span className="panel-sub">{sub}</span>
      </div>
      <div className="thumb-row">
        <div className="variants" role="radiogroup" aria-label="Thumbnail variants">
          {shown.map((t) => {
            const on = t.id === pick?.id;
            return (
              <div className={on ? "variant on" : "variant"} key={t.id}>
                <button
                  type="button"
                  role="radio"
                  aria-checked={on}
                  className="variant-pic"
                  onClick={() => setSelected(t.id)}
                  aria-label={`${t.id}: ${t.label}${t.recommended ? ", the Designer's pick" : ""}`}
                >
                  <img src={t.url} alt="" loading="lazy" />
                </button>
                <div className="variant-cap">
                  <span className={on ? "letter on" : "letter"} aria-hidden="true">
                    {t.id}
                  </span>
                  <span className="variant-words">
                    <b className="one-line">{t.label}</b>
                    {t.recommended ? (
                      <span className="pick-note">
                        <Avatar who={designer} size="small" />
                        Designer's pick
                      </span>
                    ) : t.note ? (
                      <span className="variant-note one-line">{t.note}</span>
                    ) : null}
                  </span>
                  {open ? (
                    <Button
                      label={`Use ${t.id}`}
                      size="sm"
                      variant={on ? "primary" : "secondary"}
                      isLoading={busy === t.id}
                      isDisabled={busy !== null && busy !== t.id}
                      onClick={() => void use(t)}
                      className="variant-use"
                    />
                  ) : t.picked ? (
                    <Badge variant="success" label="In use" className="variant-use" />
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
        {pick ? <PhoneCheck pick={pick} others={covers} /> : null}
      </div>
      {error ? <ErrorLine text={error} /> : null}
    </section>
  );
}

// ---------- the cut ----------

/** The waveform as bars, from the peaks (0..1, evenly spaced over the cut). */
export function wavePath(peaks: number[], width = 1000, height = 40): string {
  if (!peaks.length) return "";
  const step = width / peaks.length;
  const bar = Math.max(1, step * 0.6);
  let d = "";
  peaks.forEach((p, i) => {
    const h = Math.max(2, Math.min(1, Math.max(0, p)) * (height - 2));
    d += `M${(i * step).toFixed(1)} ${((height - h) / 2).toFixed(1)}h${bar.toFixed(1)}v${h.toFixed(1)}h-${bar.toFixed(1)}z`;
  });
  return d;
}

function ruler(seconds: number): number[] {
  const marks: number[] = [];
  const every = seconds > 600 ? 120 : seconds > 240 ? 60 : seconds > 60 ? 30 : 10;
  for (let t = 0; t < seconds - every * 0.4; t += every) marks.push(t);
  marks.push(seconds);
  return marks;
}

export function CutPanel({ cut }: { cut: MediaCut }) {
  const frames = cut.frames;
  const span = cut.seconds / Math.max(1, frames.length);
  const notes = cut.markers.filter((m) => m.level !== "error");
  const errors = cut.markers.filter((m) => m.level === "error");
  const markedAt = (t: number) => cut.markers.filter((m) => m.t >= t - span / 2 && m.t < t + span / 2);
  const sub = cut.pending
    ? "The strip and the waveform are on their way."
    : [
        frames.length && cut.shots ? `${frames.length} of ${cut.shots} shots.` : null,
        notes.length ? "Amber marks a note from the Critic." : null,
        errors.length ? "Red marks an error." : null,
      ]
        .filter(Boolean)
        .join(" ");
  return (
    <section className="panel cut-panel" aria-labelledby="cut-heading">
      <Head title={`Cut ${cut.version}`} sub={sub || undefined}>
        {(cut.facts ?? []).map((f) => (
          <Badge key={f} variant="neutral" label={f} className="chip" />
        ))}
      </Head>
      {frames.length ? (
        <div className="strip-wrap">
          <ol className="frames" aria-label="Frames of the cut" style={{ "--n": frames.length } as CSSProperties}>
            {frames.map((f) => {
              const marks = markedAt(f.t);
              const level = marks.some((m) => m.level === "error") ? "error" : marks.length ? "note" : null;
              return (
                <li key={`${f.t}-${f.url}`} className={level ? `frame mark-${level}` : "frame"} title={marks.map((m) => m.text).join(" ") || undefined}>
                  <img src={f.url} alt={`Frame at ${clock(f.t)}`} loading="lazy" />
                  <span className="frame-time" aria-hidden="true">
                    {clock(f.t)}
                  </span>
                </li>
              );
            })}
          </ol>
          {cut.peaks.length ? (
            <div className="wave">
              <svg viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden="true">
                <path d={wavePath(cut.peaks)} />
              </svg>
              {cut.markers.map((m, i) => (
                <span
                  key={`${m.t}-${i}`}
                  className={`wave-mark ${m.level === "error" ? "error" : "note"}`}
                  style={{ "--at": Math.min(1, Math.max(0, m.t / Math.max(1, cut.seconds))) } as CSSProperties}
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : null}
          <div className="ruler" aria-hidden="true">
            {ruler(cut.seconds).map((t) => (
              <span key={t}>{clock(t)}</span>
            ))}
          </div>
          {cut.markers.length ? (
            <ul className="sr-only" aria-label="Notes from the Critic">
              {cut.markers.map((m, i) => (
                <li key={i}>
                  {clock(m.t)}: {m.text}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="panel-empty">
          {cut.pending ? "Frames come as soon as the cut is read." : "No frames from this cut yet."}
        </p>
      )}
    </section>
  );
}

// ---------- 3D scenes ----------

const TILES = 24;

function Scene({ s, big }: { s: MediaScenes["items"][number]; big: boolean }) {
  const pct = typeof s.progress === "number" ? Math.round(Math.min(1, Math.max(0, s.progress)) * 100) : null;
  const tag =
    s.status === "rendering"
      ? `${s.name}, ${pct ?? 0} %`
      : s.status === "queued"
        ? `${s.name}, queued`
        : s.name;
  const doneTiles = s.status === "rendering" ? Math.floor(((pct ?? 0) / 100) * TILES) : 0;
  return (
    <li className={["scene", big ? "big" : null, s.status].filter(Boolean).join(" ")}>
      {s.url ? <img src={s.url} alt={`${s.name}${s.status === "rendering" ? ", rendering" : ""}`} loading="lazy" /> : null}
      {s.status === "rendering" && s.url ? (
        <span className="tiles" aria-hidden="true">
          {Array.from({ length: TILES }, (_, i) => (
            <i key={i} className={i < doneTiles ? "d" : i === doneTiles ? "a" : undefined} />
          ))}
        </span>
      ) : null}
      <span className="glass-tag">{tag}</span>
    </li>
  );
}

export function ScenesPanel({ scenes }: { scenes: MediaScenes }) {
  const items = scenes.items.slice(0, 5);
  return (
    <section className="panel scenes-panel" aria-labelledby="scenes-heading">
      <Head title="3D scenes" sub={scenes.title !== "3D scenes" ? scenes.title : undefined}>
        <Badge variant="neutral" label={`${scenes.done} of ${scenes.total} done`} className="chip" />
      </Head>
      {items.length ? (
        <ul className={`scenes n${items.length}`} aria-label="Scenes">
          {items.map((s, i) => (
            <Scene key={s.id} s={s} big={i === 0 && items.length > 2} />
          ))}
        </ul>
      ) : (
        <p className="panel-empty">No scenes in the plan.</p>
      )}
    </section>
  );
}

// ---------- the rented GPU ----------

function hm(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function GpuCard({ gpu, episode, frame }: { gpu: MediaGpu; episode: string; frame: string | null }) {
  const [state, setState] = useState<"idle" | "asked" | "error">("idle");
  const [error, setError] = useState("");
  const progress = typeof gpu.progress === "number" ? Math.round(Math.min(1, Math.max(0, gpu.progress)) * 100) : null;
  const started = hm(gpu.started);
  return (
    <section
      className="gpu-card"
      aria-labelledby="gpu-heading"
      style={frame ? ({ "--gpu-frame": `url("${frame}")` } as CSSProperties) : undefined}
    >
      <div className="gpu-top">
        <span className="gpu-chip" aria-hidden="true">
          <Cpu size={18} />
        </span>
        <div>
          <h2 id="gpu-heading">Rented {gpu.name}</h2>
          {started ? <p className="gpu-sub">Running since {started}</p> : null}
        </div>
      </div>
      <dl className="gpu-nums">
        <div>
          <dt>Left</dt>
          <dd>{typeof gpu.minutes_left === "number" ? `${Math.max(0, Math.round(gpu.minutes_left))} min` : "–"}</dd>
        </div>
        <div>
          <dt>So far</dt>
          <dd>{usd(gpu.so_far_usd)}</dd>
        </div>
        <div>
          <dt>Cap</dt>
          <dd>{typeof gpu.cap_usd === "number" ? usd(gpu.cap_usd) : "–"}</dd>
        </div>
      </dl>
      <ProgressBar
        className="gpu-bar"
        label="Render progress on the rented GPU"
        isLabelHidden
        value={progress ?? undefined}
        isIndeterminate={progress === null}
      />
      <div className="gpu-foot">
        <span className="dot mint" aria-hidden="true" />
        <span className="gpu-note">{state === "asked" ? "Asked the crew to stop it. The frames that are done come home." : gpu.delete_note}</span>
        {state !== "asked" ? (
          <Button
            label="Stop"
            size="sm"
            variant="secondary"
            className="gpu-stop"
            tooltip="Asks the crew in the chat to stop the machine"
            clickAction={async () => {
              try {
                await sayTo(episode, STOP_GPU);
                setState("asked");
              } catch (e) {
                setError(messageOf(e));
                setState("error");
              }
            }}
          />
        ) : null}
      </div>
      {state === "error" ? <ErrorLine text={`Couldn't ask the crew. ${error}`} /> : null}
    </section>
  );
}

// ---------- all of it ----------

export function EpisodeMediaPanels({ id }: { id: string }) {
  const { status, media, error, reload } = useMedia(id);
  if (status === "loading") return <Loading label="Loading the pictures" />;
  if (status === "error") {
    return <ErrorLine text={`Couldn't load the pictures of this episode. ${error ?? ""}`} onRetry={() => void reload()} />;
  }
  const { thumbnails, cut, scenes, gpu } = media;
  const nothing = !thumbnails.length && !cut && !scenes && !gpu;
  if (nothing) {
    return (
      <div className="media-empty">
        <SlateFigure state="idle" size={88} />
        <p>No pictures yet. Thumbnails, the cut and renders show here as the crew makes them.</p>
      </div>
    );
  }
  const frame =
    scenes?.items.find((s) => s.status === "rendering" && s.url)?.url ??
    [...(scenes?.items ?? [])].reverse().find((s) => s.url)?.url ??
    null;
  return (
    <>
      {thumbnails.length ? <ThumbnailPanel episode={id} thumbs={thumbnails} /> : null}
      {cut ? <CutPanel cut={cut} /> : null}
      {scenes || gpu ? (
        <div className={scenes && gpu ? "media-row" : "media-row solo"}>
          {scenes ? <ScenesPanel scenes={scenes} /> : null}
          {gpu ? <GpuCard gpu={gpu} episode={id} frame={frame} /> : null}
        </div>
      ) : null}
    </>
  );
}
