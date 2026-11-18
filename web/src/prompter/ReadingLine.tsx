import { GripVertical } from "lucide-react";
import { useRef, useState, type PointerEvent } from "react";

export function guidePercent(value: number | undefined): number {
  return Number.isFinite(value) ? Math.max(10, Math.min(85, Math.round(value!))) : 33;
}

export function ReadingLine({ value, onChange }: { value?: number; onChange: (value: number) => void }) {
  const [draft, setDraft] = useState<number | null>(null);
  const dragging = useRef<{ id: number; offset: number } | null>(null);
  const percent = draft ?? guidePercent(value);
  const at = (event: PointerEvent<HTMLDivElement>) => guidePercent((event.clientY - (dragging.current?.offset ?? 0)) / window.innerHeight * 100);
  return <div className={draft === null ? "pr-line" : "pr-line dragging"}
    style={{ top: `${percent}%` }} role="slider" tabIndex={0} aria-label="Reading line"
    aria-orientation="vertical" aria-valuemin={10} aria-valuemax={85} aria-valuenow={percent}
    aria-valuetext={`${percent} percent from the top`} title="Drag the reading line. Arrow keys move it too."
    onPointerDown={event => {
      if (event.button !== 0) return;
      event.preventDefault(); event.stopPropagation();
      dragging.current = { id: event.pointerId, offset: event.clientY - percent / 100 * window.innerHeight };
      event.currentTarget.setPointerCapture(event.pointerId);
      event.currentTarget.focus();
      setDraft(percent);
    }}
    onPointerMove={event => {
      if (dragging.current?.id !== event.pointerId) return;
      event.preventDefault(); event.stopPropagation(); setDraft(at(event));
    }}
    onPointerUp={event => {
      if (dragging.current?.id !== event.pointerId) return;
      event.preventDefault(); event.stopPropagation();
      const next = at(event);
      dragging.current = null; setDraft(null); onChange(next);
      event.currentTarget.releasePointerCapture(event.pointerId);
    }}
    onPointerCancel={() => { dragging.current = null; setDraft(null); }}
    onLostPointerCapture={() => { dragging.current = null; setDraft(null); }}
    onClick={event => event.stopPropagation()}
    onKeyDown={event => {
      const keys: Record<string, number> = { ArrowUp: percent - 1, ArrowDown: percent + 1, PageUp: percent - 10,
        PageDown: percent + 10, Home: 10, End: 85 };
      const next = keys[event.key];
      if (next === undefined) return;
      event.preventDefault(); event.stopPropagation(); onChange(guidePercent(next));
    }}><GripVertical size={20} aria-hidden="true" /></div>;
}
