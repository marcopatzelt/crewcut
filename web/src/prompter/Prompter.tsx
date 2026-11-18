// The teleprompter: the script in big letters on a phone. Tap or Space plays and pauses.
// It follows /p/<token>/control every 500 ms, so the desktop or a second phone (?remote=1) can drive it.
import {
  FlipHorizontal2,
  List,
  LoaderCircle,
  Minus,
  Pause,
  Play,
  Plus,
  RotateCcw,
  AlignLeft,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { PrompterControl, PrompterScript } from "../api/types";
import { guidePercent, ReadingLine } from "./ReadingLine";

export const DEFAULT_CONTROL: PrompterControl = { playing: false, speed: 1, position: 0, mirror: false, size: 1 };
const POLL_MS = 500;
const SPEED = { min: 0.3, max: 3, step: 0.1 };
const SIZE = { min: 0.6, max: 2, step: 0.1 };

export interface PrompterSource {
  script(): Promise<PrompterScript>;
  getControl(): Promise<PrompterControl>;
  setControl(c: PrompterControl): Promise<void>;
  /** false when nothing else follows this screen (a source without a server, as in the tests). */
  shared: boolean;
}

/** Reads the token from /p/<token> (or ?token= during development). */
export function tokenFromLocation(loc: Pick<Location, "pathname" | "search">): string | null {
  const m = loc.pathname.match(/\/p\/([^/]+)\/?$/);
  if (m?.[1]) return decodeURIComponent(m[1]);
  return new URLSearchParams(loc.search).get("token");
}

export function httpSource(token: string): PrompterSource {
  const base = `/p/${encodeURIComponent(token)}`;
  const json = async <T,>(res: Response): Promise<T> => {
    if (!res.ok) throw new Error(`The server answered ${res.status}.`);
    return (await res.json()) as T;
  };
  return {
    shared: true,
    script: () => fetch(`${base}/script`).then((r) => json<PrompterScript>(r)),
    getControl: () => fetch(`${base}/control`, { cache: "no-store" }).then((r) => json<PrompterControl>(r)),
    setControl: async (c) => {
      const res = await fetch(`${base}/control`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(c),
      });
      if (!res.ok) throw new Error(`The server answered ${res.status}.`);
    },
  };
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(v * 10) / 10));

function differs(a: PrompterControl, b: PrompterControl): boolean {
  return (
    a.playing !== b.playing ||
    a.mirror !== b.mirror ||
    Math.abs(a.speed - b.speed) > 0.001 ||
    Math.abs(a.size - b.size) > 0.001 ||
    (a.guide ?? 33) !== (b.guide ?? 33) ||
    Math.abs(a.position - b.position) > 0.005
  );
}

function Panel({
  ctl,
  mode,
  change,
  setMode,
  dim,
}: {
  ctl: PrompterControl;
  mode: "full" | "points";
  change: (patch: Partial<PrompterControl>) => void;
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
      <button type="button" className="pr-btn" aria-label="Back to the start" onClick={() => change({ position: 0, playing: false })}>
        <RotateCcw size={16} aria-hidden="true" />
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
  const scroller = useRef<HTMLDivElement>(null);
  const ctlRef = useRef(ctl);
  const lastSent = useRef<PrompterControl | null>(null);
  const localAt = useRef(0);
  const failures = useRef(0);
  ctlRef.current = ctl;
  const modeRef = useRef(mode);
  modeRef.current = mode;

  const loadScript = useCallback(() => {
    if (!source) return;
    setError(null);
    source
      .script()
      .then((s) => {
        setScript(s);
        setMode(s.mode === "points" ? "points" : "full");
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Something went wrong."));
  }, [source]);

  useEffect(loadScript, [loadScript]);

  // Switching between full text and key points keeps the reader at the same place.
  const modePos = useRef<number | null>(null);
  const switchMode = useCallback((m: "full" | "points") => {
    const el = scroller.current;
    if (el) {
      const max = el.scrollHeight - el.clientHeight;
      modePos.current = max > 0 ? el.scrollTop / max : 0;
    }
    setMode(m);
  }, []);

  const position = useCallback((): number => {
    const el = scroller.current;
    if (!el) return ctlRef.current.position;
    const max = el.scrollHeight - el.clientHeight;
    return max > 0 ? el.scrollTop / max : 0;
  }, []);

  const jump = useCallback((p: number) => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = p * Math.max(0, el.scrollHeight - el.clientHeight);
  }, []);

  useLayoutEffect(() => {
    if (modePos.current === null) return;
    jump(modePos.current);
    modePos.current = null;
  }, [mode, jump]);

  /** A change made on this device: apply it here and tell the others. */
  const change = useCallback(
    (patch: Partial<PrompterControl>) => {
      const next = { ...ctlRef.current, position: remote ? ctlRef.current.position : position(), ...patch };
      setCtl(next);
      if ("position" in patch && !remote) jump(next.position);
      localAt.current = Date.now();
      if (source?.shared) {
        lastSent.current = next;
        source.setControl(next).catch(() => setOffline(true));
      }
    },
    [jump, position, remote, source],
  );

  // Follow the shared control.
  useEffect(() => {
    if (!source?.shared) return;
    let stop = false;
    const tick = async () => {
      try {
        const theirs = await source.getControl();
        failures.current = 0;
        setOffline(false);
        if (stop) return;
        const mine = ctlRef.current;
        const sent = lastSent.current;
        const settling = Date.now() - localAt.current < 800;
        if (!settling && (!sent || differs(theirs, sent))) {
          const jumped = !sent || Math.abs(theirs.position - sent.position) > 0.005;
          setCtl({ ...theirs, position: jumped ? theirs.position : mine.position });
          if (jumped && !remote) jump(theirs.position);
          lastSent.current = theirs;
        } else if (!remote && mine.playing && !settling) {
          // The playing screen reports where it is, so a remote shows the right place.
          const report = { ...mine, position: position() };
          if (!sent || Math.abs(report.position - sent.position) > 0.005) {
            lastSent.current = report;
            await source.setControl(report);
          }
        }
      } catch {
        failures.current += 1;
        if (failures.current >= 3) setOffline(true);
      }
    };
    void tick();
    const t = setInterval(() => void tick(), POLL_MS);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [jump, position, remote, source]);

  // Scroll while playing.
  useEffect(() => {
    if (remote || !ctl.playing) return;
    let frame = 0;
    let last = performance.now();
    let carry = 0;
    const step = (now: number) => {
      const el = scroller.current;
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (el) {
        const fontPx = parseFloat(getComputedStyle(el.firstElementChild ?? el).fontSize) || 40;
        carry += ctlRef.current.speed * fontPx * 0.75 * dt;
        const whole = Math.floor(carry);
        if (whole >= 1) {
          el.scrollTop += whole;
          carry -= whole;
        }
        if (el.scrollTop >= el.scrollHeight - el.clientHeight - 1) {
          setCtl((c) => ({ ...c, playing: false }));
          return;
        }
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [ctl.playing, remote]);

  // Keep the screen on while it plays, where the browser allows it.
  useEffect(() => {
    if (!ctl.playing || remote) return;
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
  }, [ctl.playing, remote]);

  // Keys: Space plays and pauses, arrows change the speed, +/- the size, M mirrors, P switches the mode.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const c = ctlRef.current;
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
        switchMode(modeRef.current === "full" ? "points" : "full");
      } else if (e.key === "Home") {
        change({ position: 0, playing: false });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [change, switchMode]);

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

  if (remote) {
    return (
      <div className="pr-remote">
        <h1>{script.title}</h1>
        {script.note ? <p className="pr-value" role="note">{script.note}</p> : null}
        <p className="pr-value">Remote. The screen with the text follows these buttons.</p>
        <Panel ctl={ctl} mode={mode} change={change} setMode={switchMode} dim={false} />
        <section className="pr-guide-controls" aria-label="Reading line position">
          <h2>Reading line</h2>
          <p className="pr-value">Move the line on your teleprompter screen.</p>
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
      </div>
    );
  }

  return (
    <div className="pr">
      <div
        ref={scroller}
        className="pr-scroll"
        onClick={() => change({ playing: !ctlRef.current.playing })}
        aria-label="Script. Tap to play or pause."
      >
        <div className={ctl.mirror ? "pr-text mirror" : "pr-text"} style={{ ["--size" as string]: ctl.size }}>
          <p className="pr-title">{script.title}</p>
          {script.note ? <p className="pr-title" role="note">{script.note}</p> : null}
          {mode === "full"
            ? script.blocks.map((b, i) => <p key={i}>{b.text}</p>)
            : script.blocks.map((b, i) => (
                <ul key={i}>
                  {(b.points.length ? b.points : [b.text]).map((p, j) => (
                    <li key={j}>{p}</li>
                  ))}
                </ul>
              ))}
        </div>
      </div>
      <ReadingLine value={ctl.guide} onChange={guide => change({ guide })} />
      {offline ? <p className="pr-note">Not in sync with the remote. Trying again.</p> : null}
      <Panel ctl={ctl} mode={mode} change={change} setMode={switchMode} dim={ctl.playing} />
    </div>
  );
}
