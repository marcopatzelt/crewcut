// Small shared pieces: identity mark, delayed spinner, inline error, step bar, facts table, file preview.
import { AlertCircle, LoaderCircle } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Fact, Identity, Step } from "../api/types";
import { mediaKind } from "../lib/format";

export function Mark({ mark, big }: { mark: string; big?: boolean }) {
  return (
    <span className={big ? "mark big" : "mark"} aria-hidden="true">
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

export function StepBar({ steps, label }: { steps: Step[]; label?: string }) {
  return (
    <span className="bar" role="img" aria-label={label}>
      {steps.map((s) => (
        <i key={s.id} className={s.status} />
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

/** A video or image from the episode folder, through /api/files. */
export function Media({ episode, path, label }: { episode: string; path: string; label: string }) {
  const [failed, setFailed] = useState(false);
  const url = api.fileUrl(episode, path);
  useEffect(() => setFailed(false), [url]);
  if (failed) {
    return (
      <div className="media media-error" role="note">
        Couldn't load {path}. It is still in the episode folder.
      </div>
    );
  }
  // Decide by the address the browser loads (the demo maps videos to still images).
  const kind = mediaKind(url) === "other" ? mediaKind(path) : mediaKind(url);
  if (kind === "video") {
    return (
      <video
        className="media"
        src={url}
        controls
        preload="metadata"
        playsInline
        aria-label={label}
        onError={() => setFailed(true)}
      />
    );
  }
  if (kind === "image") {
    return <img className="media" src={url} alt={label} loading="lazy" onError={() => setFailed(true)} />;
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
