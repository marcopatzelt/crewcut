// The Humanizer note on a script or title card (DESIGN.md rule 12): one quiet line that says the text went through
// Humanizer and how many sentences changed; opened, the changes as before and after. Collapsed by default.
import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import type { Card, HumanizerNote } from "../api/types";

export function humanizerLine(h: HumanizerNote): string {
  if (h.skipped) return `Not humanized: ${h.skipped}`;
  const n = h.count ?? h.changes?.length ?? 0;
  const what = n === 0 ? "nothing to change" : n === 1 ? "1 change" : `${n} changes`;
  const voice = h.voice && h.voice.length ? "with your voice" : "without a voice sample";
  return ["Humanized", what, h.version ? `Humanizer ${h.version}` : null, voice].filter(Boolean).join(" · ");
}

export function Humanized({ card, folding }: { card: Card; folding: boolean }) {
  const h = card.data?.humanizer as HumanizerNote | undefined;
  const [open, setOpen] = useState(false);
  const list = useId();
  if (!h) return null;
  const changes = h.changes ?? [];
  if (h.skipped || changes.length === 0) {
    return <p className="humanized quiet-line">{humanizerLine(h)}</p>;
  }
  return (
    <div className="humanized">
      <button
        type="button"
        className="exchange-line"
        aria-expanded={open}
        aria-controls={list}
        onClick={() => setOpen((o) => !o)}
        tabIndex={folding ? -1 : undefined}
      >
        <ChevronRight size={14} aria-hidden="true" className="exchange-chev" />
        <span className="one-line">{humanizerLine(h)}</span>
      </button>
      {open ? (
        <ol className="exchange-list humanized-list" id={list} aria-label="What the Humanizer changed">
          {h.why ? <li className="humanized-why">{h.why}</li> : null}
          {changes.map((c, i) => (
            <li key={i}>
              {c.before ? (
                <p className="was">
                  <span className="sr-only">Before: </span>
                  {c.before}
                </p>
              ) : null}
              {c.after ? (
                <p className="now">
                  <span className="sr-only">After: </span>
                  {c.after}
                </p>
              ) : (
                <p className="now">(removed)</p>
              )}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
