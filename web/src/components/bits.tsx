// Small shared pieces: identity mark, delayed spinner, inline error, step bar, keycaps, facts table, file preview.
import { AlertCircle, ImageOff, LoaderCircle } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import { ONBOARDING, type Fact, type Identity, type Step } from "../api/types";
import { mediaKind } from "../lib/format";
import { keyLabels } from "../lib/platform";

/**
 * A two-letter mark on a neutral plate, a rounded square like a small app icon (DESIGN.md rule 13).
 * "working" adds a small accent dot at the bottom right, "waiting" a ring in --warn. No colours per identity.
 */
export function Mark({
  mark,
  big,
  small,
  state,
}: {
  mark: string;
  big?: boolean;
  small?: boolean;
  state?: "working" | "waiting";
}) {
  const cls = ["mark", big ? "big" : small ? "small" : null, state ? `is-${state}` : null].filter(Boolean).join(" ");
  return (
    <span className={cls} aria-hidden="true">
      {mark}
    </span>
  );
}

/** Keeps the layout; shows a spinner only after 300 ms (DESIGN.md rule 11). */
export function Loading({ label = "Loading" }: { label?: string }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setShow(true), 300);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="center-state" role="status" aria-label={label} data-testid="loading">
      {show ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : null}
    </div>
  );
}

export function ErrorLine({ text, onRetry, children }: { text: string; onRetry?: () => void; children?: ReactNode }) {
  return (
    <div className="error-line" role="alert">
      <AlertCircle size={14} aria-hidden="true" />
      <span>{text}</span>
      {children}
      {onRetry ? (
        <button type="button" className="link-button" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

/** The ten strokes of an episode row: done in --ink-3, the current one in --accent, open ones in --line-strong. */
export function StepBar({ steps, label }: { steps: Step[]; label?: string }) {
  return (
    <span className="bar" role="img" aria-label={label}>
      {steps.map((s) => (
        <i key={s.id} className={s.status} />
      ))}
    </span>
  );
}

/** Shortcut keycaps: ⌘ on Apple devices, Ctrl elsewhere (rule 15). Decorative: the action has its own name. */
export function Keys({ keys, className }: { keys: string[]; className?: string }) {
  return (
    <span className={className ? `keys ${className}` : "keys"} aria-hidden="true">
      {keyLabels(keys).map((k, i) => (
        <kbd key={`${i}-${k}`}>{k}</kbd>
      ))}
    </span>
  );
}

export function Facts({ facts }: { facts: Fact[] }) {
  return (
    <dl className="facts">
      {facts.map((f) => (
        <div key={f.label}>
          <dt>{f.label}</dt>
          <dd>{f.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Where a preview file lives, in the words of the studio folder. */
function whereIs(episode: string, path: string): string {
  if (path.startsWith("/") || episode === ONBOARDING) return path;
  return `episodes/${episode}/${path}`;
}

/**
 * A video or image from the episode folder, through /api/files. While it loads, a placeholder of the same size shows
 * the run shimmer, but only after 300 ms (rule 11). A broken file says where it is and offers to try again.
 */
export function Media({ episode, path, label }: { episode: string; path: string; label: string }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [slow, setSlow] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const url = api.fileUrl(episode, path);

  useEffect(() => {
    setFailed(false);
    setLoaded(false);
    setSlow(false);
    const t = setTimeout(() => setSlow(true), 300);
    return () => clearTimeout(t);
  }, [url, attempt]);

  if (failed) {
    return (
      <div className="media media-error" role="note">
        <ImageOff size={16} aria-hidden="true" />
        <span>Couldn't load the preview. The file is at {whereIs(episode, path)}.</span>
        <button type="button" className="link-button" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }
  // Decide by the address the browser loads (the demo maps videos to still images).
  const kind = mediaKind(url) === "other" ? mediaKind(path) : mediaKind(url);
  const state = loaded ? "ready" : slow ? "loading" : "waiting";
  if (kind === "video") {
    return (
      <div className="media-box" data-state={state} data-testid="media">
        <video
          key={attempt}
          className="media"
          src={url}
          controls
          preload="metadata"
          playsInline
          aria-label={label}
          onLoadedMetadata={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
      </div>
    );
  }
  if (kind === "image") {
    return (
      <div className="media-box" data-state={state} data-testid="media">
        <img
          key={attempt}
          className="media"
          src={url}
          alt={label}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
      </div>
    );
  }
  return (
    <a className="file-row" href={url} target="_blank" rel="noreferrer">
      {path}
    </a>
  );
}

export function identityOf(team: Identity[] | undefined, id: string | null | undefined): Identity {
  const found = team?.find((t) => t.id === id);
  if (found) return found;
  const name = id ? id.charAt(0).toUpperCase() + id.slice(1) : "Crewcut";
  return { id: id ?? "", name, role: "", mark: name.slice(0, 2).toUpperCase(), skills: [], may_spend: false, may_publish: false };
}
