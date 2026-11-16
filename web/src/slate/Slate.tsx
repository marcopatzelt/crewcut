// Slate in the app: crew avatars with their prop and state, the app icon, and the standing figure of the empty states
// and the welcome. The SVG comes from art.ts (one source with the static brand files); colours are CSS tokens and the
// state animations live in app.css with their reduced-motion branch (DESIGN.md rule 9).
import { useMemo } from "react";
import { appIcon, avatar, CSS_PALETTE, PROPS, standing, type SlateProp, type SlateState } from "./art";

/** Fallback when an identity file has no `avatar` yet. */
const BY_ID: Record<string, SlateProp> = {
  showrunner: "headset",
  scout: "magnifier",
  writer: "pencil",
  editor: "scissors",
  critic: "clipboard",
  designer: "brush",
  publisher: "plane",
  brand: "swatches",
};

export function propOf(who: { id: string; avatar?: string | null }): SlateProp | null {
  const name = who.avatar || BY_ID[who.id];
  return name && (PROPS as readonly string[]).includes(name) ? (name as SlateProp) : null;
}

/** A crew member's face: decorative, the name always stands next to it. */
export function Avatar({
  who,
  size,
  state,
  still,
}: {
  who: { id: string; avatar?: string | null };
  size?: "small" | "big" | "crew";
  state?: SlateState;
  /** Show the state's end pose without playing it (e.g. jobs that were already done when the column opened). */
  still?: boolean;
}) {
  const which = propOf(who);
  const html = useMemo(() => avatar(CSS_PALETTE, which, state ?? "plain"), [which, state]);
  const cls = ["avatar", "slate", size ? `av-${size}` : null, state && state !== "plain" ? `is-${state}` : null, still ? "is-still" : null].filter(Boolean).join(" ");
  return <span className={cls} aria-hidden="true" dangerouslySetInnerHTML={{ __html: html }} />;
}

export function AppIcon({ size = 20 }: { size?: number }) {
  const html = useMemo(() => appIcon(CSS_PALETTE, { size }), [size]);
  return <span className="app-icon slate" aria-hidden="true" dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Slate standing, for the empty states ("idle", "plain") and the welcome ("wave"). */
export function SlateFigure({ state = "plain", size = 96 }: { state?: SlateState; size?: number }) {
  const html = useMemo(() => standing(CSS_PALETTE, state, { size }), [state, size]);
  const cls = ["slate-figure", "slate", state !== "plain" ? `is-${state}` : null].filter(Boolean).join(" ");
  return <span className={cls} aria-hidden="true" dangerouslySetInnerHTML={{ __html: html }} />;
}
