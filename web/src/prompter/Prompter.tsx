// The teleprompter: the script as numbered speaking blocks in big letters, on phones and on the prompter glass.
// Every screen follows one shared timeline (timeline.ts, sync.ts). Tap a block on any screen and every screen jumps to
// its start; Previous, Repeat and Next do the same for the blocks around the reading line. A hand scroll on one screen
// moves the others with it. The block on the reading line is marked on every screen.
import {
  AlignLeft,
  ArrowDown,
  ArrowUp,
  ArrowUpToLine,
  ChevronLeft,
  ChevronRight,
  FlipHorizontal2,
  List,
  LoaderCircle,
  Minus,
  Pause,
  Play,
  Plus,
  RotateCcw,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PrompterControl, PrompterScript } from "../api/types";
import { measure, placeOn, scrollFor, type Layout } from "./geometry";
import { guidePercent, ReadingLine } from "./ReadingLine";
import { DEFAULT_CONTROL, httpSource, PrompterSync, type PrompterSource } from "./sync";
import { DEFAULT_CPS, normalizeBlocks, placeAt, stepTarget, type Block, type ControlPatch } from "./timeline";

export { DEFAULT_CONTROL, httpSource, type PrompterSource };

const SPEED = { min: 0.3, max: 3, step: 0.1 };
const SIZE = { min: 0.6, max: 2, step: 0.1 };

/** Reads the token from /p/<token> (or ?token= during development). */
export function tokenFromLocation(loc: Pick<Location, "pathname" | "search">): string | null {
  const m = loc.pathname.match(/\/p\/([^/]+)\/?$/);
  if (m?.[1]) return decodeURIComponent(m[1]);
  return new URLSearchParams(loc.search).get("token");
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(v * 10) / 10));

function Panel({
  ctl,
  mode,
  change,
  setMode,
  dim,
}: {
  ctl: PrompterControl;
  mode: "full" | "points";
  change: (patch: ControlPatch) => void;
  setMode: (m: "full" | "points") => void;
  dim: boolean;
}) {
  return (
    <div className={dim ? "pr-panel dim" : "pr-panel"} role="toolbar" aria-label="Teleprompter controls">
      <button
        type="button"
        className="pr-btn play"
        onClick={() => change({ playing: !ctl.playing })}
        aria-label={ctl.playing ? "Pause" : "Play"}
      >
        {ctl.playing ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
        {ctl.playing ? "Pause" : "Play"}
      </button>
      <span className="pr-sep" aria-hidden="true" />
      <button type="button" className="pr-btn" aria-label="Slower" onClick={() => change({ speed: clamp(ctl.speed - SPEED.step, SPEED.min, SPEED.max) })}>
        <Minus size={16} aria-hidden="true" />
      </button>
      <span className="pr-value" aria-label={`Speed ${ctl.speed.toFixed(1)}`}>
        {ctl.speed.toFixed(1)}×
      </span>
      <button type="button" className="pr-btn" aria-label="Faster" onClick={() => change({ speed: clamp(ctl.speed + SPEED.step, SPEED.min, SPEED.max) })}>
        <Plus size={16} aria-hidden="true" />
      </button>
      <span className="pr-sep" aria-hidden="true" />
      <button type="button" className="pr-btn" aria-label="Smaller text" onClick={() => change({ size: clamp(ctl.size - SIZE.step, SIZE.min, SIZE.max) })}>
        A−
      </button>
      <span className="pr-value" aria-label={`Text size ${Math.round(ctl.size * 100)} percent`}>
        {Math.round(ctl.size * 100)} %
      </span>
      <button type="button" className="pr-btn" aria-label="Bigger text" onClick={() => change({ size: clamp(ctl.size + SIZE.step, SIZE.min, SIZE.max) })}>
        A+
      </button>
      <span className="pr-sep" aria-hidden="true" />
      <button
        type="button"
        className="pr-btn"
        aria-label={mode === "full" ? "Show key points" : "Show full text"}
        title={mode === "full" ? "Key points" : "Full text"}
        onClick={() => setMode(mode === "full" ? "points" : "full")}
      >
        {mode === "full" ? <List size={16} aria-hidden="true" /> : <AlignLeft size={16} aria-hidden="true" />}
      </button>
      <button
        type="button"
        className="pr-btn"
        aria-label="Mirror"
        aria-pressed={ctl.mirror}
        onClick={() => change({ mirror: !ctl.mirror })}
      >
        <FlipHorizontal2 size={16} aria-hidden="true" />
      </button>
      <button type="button" className="pr-btn" aria-label="Back to the start" title="Back to the start" onClick={() => change({ action: "start" })}>
        <ArrowUpToLine size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

/** Previous, Repeat and Next: big enough for a thumb, the same on every screen. */
function BlockBar({ blocks, current, step, dim }: {
  blocks: Block[];
  current: number;
  step: (kind: "prev" | "next" | "repeat") => void;
  dim: boolean;
}) {
  const number = blocks[current]?.n ?? null;
  const total = blocks.filter((b) => !b.heading).length;
  return (
    <div className={dim ? "pr-panel pr-blocks dim" : "pr-panel pr-blocks"} role="toolbar" aria-label="Speaking blocks">
      <button type="button" className="pr-btn pr-step" aria-label="Previous block"
        disabled={stepTarget(blocks, current, -1) === null} onClick={() => step("prev")}>
        <ChevronLeft size={20} aria-hidden="true" />
        Previous
      </button>
      <button type="button" className="pr-btn pr-step repeat"
        aria-label={number === null ? "Repeat block" : `Repeat block ${number} of ${total}`}
        disabled={!blocks.length} onClick={() => step("repeat")}>
        <RotateCcw size={20} aria-hidden="true" />
        {number === null ? "Repeat" : `Repeat ${number}`}
      </button>
      <button type="button" className="pr-btn pr-step" aria-label="Next block"
        disabled={stepTarget(blocks, current, 1) === null} onClick={() => step("next")}>
        Next
        <ChevronRight size={20} aria-hidden="true" />
      </button>
    </div>
  );
}

export function Prompter({ source, remote }: { source: PrompterSource | null; remote: boolean }) {
  const [script, setScript] = useState<PrompterScript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"full" | "points">("full");
  const [ctl, setCtl] = useState<PrompterControl>(DEFAULT_CONTROL);
  const [offline, setOffline] = useState(false);
  const [current, setCurrent] = useState(0);
  const [flash, setFlash] = useState<{ block: number; cue: number } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const copy = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLOListElement>(null);
  const sync = useRef<PrompterSync | null>(null);
  const blocks = useMemo(() => normalizeBlocks(script?.blocks ?? []), [script]);
  const blocksRef = useRef(blocks);
  blocksRef.current = blocks;
  const pace = useRef({ weights: [] as number[], cps: DEFAULT_CPS });
  const weights = useMemo(() => blocks.map((b) => b.weight), [blocks]);
  pace.current = { weights, cps: script?.cps ?? DEFAULT_CPS };
  const currentRef = useRef(0);
  const layout = useRef<Layout | null>(null);
  const dirty = useRef(true);
  const frame = useRef(0);
  const endSent = useRef<number | null>(null);
  // A hand scroll: touching, the time of the last scroll by hand (ms), and whether this touch moved the text.
  const hand = useRef({ touching: false, at: -1e9, moved: false, timer: 0 as unknown as ReturnType<typeof setTimeout> });
  const loaded = useRef(false);

  const loadScript = useCallback(() => {
    if (!source) return;
    setError(null);
    source
      .script()
      .then((s) => {
        setScript(s);
        if (!loaded.current) setMode(s.mode === "points" ? "points" : "full");
        loaded.current = true;
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Something went wrong."));
  }, [source]);

  useEffect(loadScript, [loadScript]);

  // A finger on the text (a touch that ended unseen, as when the phone locks, counts for 4 s at most) or a scroll by
  // hand in the last 250 ms: this screen does not move the text itself.
  const byHand = () => {
    const since = performance.now() - hand.current.at;
    return (hand.current.touching && since < 4000) || since < 250;
  };

  const getLayout = (): Layout | null => {
    const el = scroller.current;
    const text = copy.current;
    if (!el || !text) return null;
    if (dirty.current || !layout.current) {
      const line = el.parentElement?.querySelector<HTMLElement>(":scope > .pr-line") ?? null;
      layout.current = measure(el, text, line, guidePercent(sync.current?.state.guide));
      dirty.current = false;
    }
    return layout.current;
  };

  const markCurrent = (block: number) => {
    if (currentRef.current === block) return;
    currentRef.current = block;
    setCurrent(block);
  };

  // One frame: put the shared place on the reading line (unless a hand scrolls here) and mark its block.
  const draw = useCallback(() => {
    frame.current = 0;
    const s = sync.current;
    const { weights, cps } = pace.current;
    if (!s || !weights.length) return;
    const state = s.state;
    const place = placeAt(state, weights, cps, s.clock.now());
    if (!byHand()) {
      const el = scroller.current;
      const l = getLayout();
      if (el && l) {
        const top = scrollFor(l, place.block, place.offset);
        if (Math.abs(el.scrollTop - top) >= 1) el.scrollTop = top;
      }
      markCurrent(place.block);
    }
    if (place.end && state.playing && endSent.current !== (state.seq ?? 0)) {
      endSent.current = state.seq ?? 0;
      void s.send({ action: "end" });
    }
    if (state.playing && !place.end) frame.current = requestAnimationFrame(draw);
  }, []); // reads refs only

  const kick = useCallback(() => {
    if (!frame.current) frame.current = requestAnimationFrame(draw);
  }, [draw]);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  // Follow the shared state.
  useEffect(() => {
    if (!source) return;
    const s = new PrompterSync(source, (state, off) => {
      setCtl(state);
      setOffline(off);
    });
    sync.current = s;
    s.setScript(pace.current.weights, pace.current.cps);
    s.start();
    return () => {
      s.stop();
      if (sync.current === s) sync.current = null;
    };
  }, [source]);

  useEffect(() => {
    sync.current?.setScript(pace.current.weights, pace.current.cps);
  }, [weights, script]);

  // A new script version on the server (approved again, changed): load it.
  const reloadedFor = useRef<string | null>(null);
  useEffect(() => {
    const v = ctl.version;
    if (!script || !v || script.version === undefined || v === script.version || reloadedFor.current === v) return;
    reloadedFor.current = v;
    loadScript();
  }, [ctl.version, script, loadScript]);

  // Mark the block a jump went to, on every screen (not when the page opens).
  const lastCue = useRef<number | null>(null);
  useEffect(() => {
    if (ctl.seq === undefined) return;
    const cue = ctl.cue ?? 0;
    if (lastCue.current !== null && cue > lastCue.current) setFlash({ block: ctl.block ?? 0, cue });
    lastCue.current = cue;
  }, [ctl.seq, ctl.cue, ctl.block]);

  // Layout changes move the text: measure again before the next frame.
  useLayoutEffect(() => {
    dirty.current = true;
    kick();
  }, [blocks, mode, ctl.size, ctl.guide, ctl.mirror, kick]);

  useEffect(() => {
    kick();
  }, [ctl, kick]);

  useEffect(() => {
    const again = () => {
      dirty.current = true;
      kick();
    };
    window.addEventListener("resize", again);
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(again) : null;
    if (observer && copy.current) observer.observe(copy.current);
    void document.fonts?.ready.then(again).catch(() => undefined);
    return () => {
      window.removeEventListener("resize", again);
      observer?.disconnect();
    };
  }, [kick, script, remote]);

  // A hand scroll here: every other screen follows at once, and the end of the scroll goes to the take log.
  const endScroll = () => {
    const h = hand.current;
    clearTimeout(h.timer);
    const el = scroller.current;
    const l = getLayout();
    if (h.moved && el && l && sync.current) {
      const p = placeOn(l, el.scrollTop);
      sync.current.scroll(p.block, p.offset, true);
    }
    h.moved = false;
    h.at = -1e9;
    kick();
  };
  const finishScroll = useCallback(() => {
    const h = hand.current;
    clearTimeout(h.timer);
    if (h.touching && performance.now() - h.at < 4000) {
      h.timer = setTimeout(finishScroll, 250);
      return;
    }
    if (performance.now() - h.at < 200) {
      h.timer = setTimeout(finishScroll, 250);
      return;
    }
    endScroll();
  }, []); // reads refs only

  const onScroll = () => {
    const h = hand.current;
    const now = performance.now();
    if (!((h.touching && now - h.at < 4000) || now - h.at < 250)) return; // this screen's own move along the timeline
    h.at = now;
    h.moved = true;
    const el = scroller.current;
    const l = getLayout();
    if (!el || !l || !sync.current) return;
    const p = placeOn(l, el.scrollTop);
    markCurrent(p.block);
    sync.current.scroll(p.block, p.offset, false);
    clearTimeout(h.timer);
    h.timer = setTimeout(finishScroll, 250);
  };

  const touchStart = () => {
    hand.current.touching = true;
    hand.current.at = performance.now();
  };
  const touchEnd = () => {
    hand.current.touching = false;
    hand.current.at = performance.now();
    clearTimeout(hand.current.timer);
    hand.current.timer = setTimeout(finishScroll, 250);
  };
  const wheel = () => {
    hand.current.at = performance.now();
    clearTimeout(hand.current.timer);
    hand.current.timer = setTimeout(finishScroll, 250);
  };
  useEffect(() => () => clearTimeout(hand.current.timer), []);

  const change = useCallback((patch: ControlPatch) => {
    // A command right after a hand scroll: the scroll's end is written first, so the command starts from there.
    if (hand.current.moved && !hand.current.touching) endScroll();
    void sync.current?.send(patch);
  }, []); // reads refs only
  const jumpTo = useCallback((block: number) => change({ action: "jump", block }), [change]);
  const step = useCallback((kind: "prev" | "next" | "repeat") => {
    const all = blocksRef.current;
    if (!all.length) return;
    const here = Math.min(currentRef.current, all.length - 1);
    const target = kind === "repeat" ? here : stepTarget(all, here, kind === "next" ? 1 : -1);
    if (target !== null) change({ action: kind, block: target });
  }, [change]);

  // Keep the screen on while it plays, where the browser allows it.
  useEffect(() => {
    if (!ctl.playing) return;
    const nav = navigator as Navigator & { wakeLock?: { request(type: "screen"): Promise<{ release(): Promise<void> }> } };
    let lock: { release(): Promise<void> } | null = null;
    nav.wakeLock
      ?.request("screen")
      .then((l) => {
        lock = l;
      })
      .catch(() => undefined);
    return () => {
      void lock?.release().catch(() => undefined);
    };
  }, [ctl.playing]);

  // The remote keeps the marked block in view, unless a thumb moved the list a moment ago.
  const listTouched = useRef(-1e9);
  useEffect(() => {
    if (!remote || performance.now() - listTouched.current < 3000) return;
    const row = list.current?.querySelector<HTMLElement>(`[data-index="${current}"]`);
    if (row && typeof row.scrollIntoView === "function") row.scrollIntoView({ block: "center" });
  }, [current, remote]);

  // Keys: Space plays and pauses, arrows change the speed, +/- the size, M mirrors, P switches the mode, Home goes to
  // the start. Page Down or N goes to the next block, Page Up or B to the previous one, R repeats the block (a
  // presenter clicker sends Page Up and Page Down).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const c = sync.current?.state ?? DEFAULT_CONTROL;
      if (e.target instanceof HTMLButtonElement && (e.key === " " || e.key === "Enter")) return;
      if (e.key === " ") {
        e.preventDefault();
        change({ playing: !c.playing });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        change({ speed: clamp(c.speed + SPEED.step, SPEED.min, SPEED.max) });
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        change({ speed: clamp(c.speed - SPEED.step, SPEED.min, SPEED.max) });
      } else if (e.key === "+" || e.key === "=") {
        change({ size: clamp(c.size + SIZE.step, SIZE.min, SIZE.max) });
      } else if (e.key === "-") {
        change({ size: clamp(c.size - SIZE.step, SIZE.min, SIZE.max) });
      } else if (e.key === "m" || e.key === "M") {
        change({ mirror: !c.mirror });
      } else if (e.key === "p" || e.key === "P") {
        setMode((m) => (m === "full" ? "points" : "full"));
      } else if (e.key === "Home") {
        e.preventDefault();
        change({ action: "start" });
      } else if (e.key === "PageDown" || e.key === "n" || e.key === "N") {
        e.preventDefault();
        step("next");
      } else if (e.key === "PageUp" || e.key === "b" || e.key === "B") {
        e.preventDefault();
        step("prev");
      } else if (e.key === "r" || e.key === "R") {
        step("repeat");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [change, step]);

  if (!source) {
    return (
      <div className="pr-state" role="alert">
        This page needs the link from Crewcut. Open the episode, click Teleprompter and scan the code.
      </div>
    );
  }
  if (error) {
    return (
      <div className="pr-state" role="alert">
        <span>Couldn't load the script. {error}</span>
        <button type="button" className="pr-btn play" onClick={loadScript}>
          Try again
        </button>
      </div>
    );
  }
  if (!script) {
    return (
      <div className="pr-state" role="status" aria-label="Loading the script">
        <LoaderCircle size={24} className="spin" aria-hidden="true" />
      </div>
    );
  }

  const dim = ctl.playing && !remote;
  const dock = (
    <div className="pr-dock">
      <BlockBar blocks={blocks} current={current} step={step} dim={dim} />
      <Panel ctl={ctl} mode={mode} change={change} setMode={setMode} dim={dim} />
    </div>
  );
  const blockClass = (i: number, base: string) =>
    [base, i === current ? "current" : i < current ? "past" : "", flash?.block === i ? "cued" : ""].filter(Boolean).join(" ");
  const breakBefore = (i: number) => i > 0 && blocks[i]?.section !== blocks[i - 1]?.section;

  if (remote) {
    return (
      <div className="pr-remote">
        <header className="pr-remote-head">
          <h1>{script.title}</h1>
          {script.note ? <p className="pr-value" role="note">{script.note}</p> : null}
          <p className="pr-value">Remote. Tap a block and every screen jumps to it.</p>
        </header>
        <ol className="pr-list" ref={list} aria-label="Speaking blocks"
          onTouchStart={() => { listTouched.current = performance.now(); }}
          onWheel={() => { listTouched.current = performance.now(); }}>
          {blocks.map((b, i) => (
            <li key={i} data-index={i} className={breakBefore(i) ? "pr-row break" : "pr-row"}>
              {b.heading ? (
                <p className="pr-row-heading">{b.text}</p>
              ) : (
                <button key={flash?.block === i ? `cue-${flash.cue}` : "row"} type="button" className={blockClass(i, "pr-row-btn")}
                  aria-current={i === current ? "true" : undefined} aria-label={`Block ${b.n}: ${b.text}`}
                  onClick={() => jumpTo(i)}>
                  <span className="pr-row-num" aria-hidden="true">{b.n}</span>
                  <span className="pr-row-text">{b.text}</span>
                </button>
              )}
            </li>
          ))}
        </ol>
        <section className="pr-guide-controls" aria-label="Reading line position">
          <h2>Reading line</h2>
          <div>
            <button type="button" className="pr-btn" aria-label="Move reading line up"
              disabled={guidePercent(ctl.guide) <= 10} onClick={() => change({ guide: guidePercent(guidePercent(ctl.guide) - 2) })}>
              <ArrowUp size={18} aria-hidden="true" />Higher
            </button>
            <span className="pr-value" aria-label="Reading line percent">{guidePercent(ctl.guide)} %</span>
            <button type="button" className="pr-btn" aria-label="Move reading line down"
              disabled={guidePercent(ctl.guide) >= 85} onClick={() => change({ guide: guidePercent(guidePercent(ctl.guide) + 2) })}>
              <ArrowDown size={18} aria-hidden="true" />Lower
            </button>
            <button type="button" className="pr-btn" onClick={() => change({ guide: 33 })}>Reset line</button>
          </div>
        </section>
        {offline ? <p className="pr-value">Not in sync. Trying again.</p> : null}
        {dock}
      </div>
    );
  }

  return (
    <div className="pr">
      <div
        ref={scroller}
        className="pr-scroll"
        onScroll={onScroll}
        onTouchStart={touchStart}
        onTouchEnd={touchEnd}
        onTouchCancel={touchEnd}
        onWheel={wheel}
        aria-label="Script. Tap a block to start there."
      >
        <div className={ctl.mirror ? "pr-text mirror" : "pr-text"} style={{ ["--size" as string]: ctl.size, ["--guide" as string]: guidePercent(ctl.guide) }}>
          <div className="pr-copy" ref={copy}>
            <div className="pr-heading">
              <p className="pr-title">{script.title}</p>
              {script.note ? <p className="pr-title" role="note">{script.note}</p> : null}
            </div>
            {blocks.map((b, i) => (
              <Fragment key={i}>
                {breakBefore(i) ? <div className="pr-break" aria-hidden="true" /> : null}
                <div key={flash?.block === i ? `cue-${flash.cue}` : "block"} className={blockClass(i, b.heading ? "pr-block heading" : "pr-block")}
                  data-index={i} aria-current={i === current ? "true" : undefined} onClick={() => jumpTo(i)}>
                  {b.n !== null ? <span className="pr-num" aria-hidden="true"><span>{b.n}</span></span> : null}
                  {mode === "full" || b.heading ? (
                    <p>{b.text}</p>
                  ) : (
                    <ul>
                      {(b.points.length ? b.points : [b.text]).map((p, j) => (
                        <li key={j}>{p}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </Fragment>
            ))}
          </div>
        </div>
      </div>
      <ReadingLine value={ctl.guide} onChange={(guide) => change({ guide })} />
      {offline ? <p className="pr-note">Not in sync. Trying again.</p> : null}
      {dock}
    </div>
  );
}
