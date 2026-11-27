// The teleprompter's shared timeline. The server keeps one anchor (a block and the offset in it), the server time `at`
// the anchor was set, and the speed (crewcut/prompter.py has the same rules). Every screen computes where the text is
// from these and its own estimate of the server clock, so no screen reports a scroll position back, and a screen that
// slept or opened late is at the right place at once.
import type { PrompterBlock, PrompterControl, PrompterPage } from "../api/types";

export const DEFAULT_CPS = 17;
export const PAUSE_CHARS = 8;
export const SECTION_PAUSE_CHARS = 24;
export const JUMP_HOLD_MS = 1500;

export type JumpAction = "jump" | "next" | "prev" | "repeat" | "start";
export type Action = JumpAction | "scroll" | "scrolled" | "end";
export type ControlPatch = Partial<Pick<PrompterControl, "playing" | "speed" | "mirror" | "size" | "guide">> & {
  action?: Action;
  block?: number;
  offset?: number;
};

export interface Block {
  text: string;
  points: string[];
  heading: boolean;
  n: number | null;
  section: number;
  weight: number;
  /** Cue sheets only (see PrompterBlock). */
  kind?: "fixed" | "bullet";
  role?: string;
  page?: string;
  unit?: number | null;
  picture?: string | null;
  question?: string | null;
  groups?: string[];
  big?: boolean;
}

/** A page of a cue sheet, with the unit's number (null outside the units). */
export interface Page extends PrompterPage {
  unit: number | null;
}

export interface Place {
  block: number;
  offset: number;
  end: boolean;
}

/** Blocks with number, section and weight; a server or sample data without them gets the same rules here. */
export function normalizeBlocks(raw: PrompterBlock[]): Block[] {
  let n = 0;
  const blocks = raw.map((b) => {
    const heading = Boolean(b.heading);
    if (!heading) n += 1;
    const block: Block = { text: b.text, points: b.points ?? [], heading, n: b.n === undefined ? (heading ? null : n) : b.n,
      section: b.section ?? 1, weight: b.weight ?? 0 };
    if (b.kind) {
      Object.assign(block, { kind: b.kind, role: b.role ?? "", page: b.page, unit: b.unit ?? null,
        picture: b.picture ?? null, question: b.question ?? null, groups: b.groups ?? [], big: Boolean(b.big) });
    }
    return block;
  });
  blocks.forEach((b, i) => {
    if (b.weight > 0) return;
    const next = blocks[i + 1];
    b.weight = Math.max(1, b.text.length) + (next && next.section !== b.section ? SECTION_PAUSE_CHARS : PAUSE_CHARS);
  });
  return blocks;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Moves `units` characters forward from (block, offset). */
export function advance(weights: number[], block: number, offset: number, units: number): Place {
  if (!weights.length) return { block: 0, offset: 0, end: true };
  let i = clamp(Math.trunc(block) || 0, 0, weights.length - 1);
  let f = clamp(Number.isFinite(offset) ? offset : 0, 0, 1);
  let left = Math.max(0, units);
  for (;;) {
    const weight = Math.max(1, weights[i] ?? 1);
    const rest = (1 - f) * weight;
    if (left < rest) return { block: i, offset: f + left / weight, end: false };
    if (i === weights.length - 1) return { block: i, offset: 1, end: true };
    left -= rest;
    i += 1;
    f = 0;
  }
}

/** Where the shared timeline is at server time `serverNow` (ms). */
export function placeAt(c: PrompterControl, weights: number[], cps: number, serverNow: number): Place {
  const units = c.playing ? (Math.max(0, serverNow - (c.at ?? serverNow)) / 1000) * cps * c.speed : 0;
  return advance(weights, c.block ?? 0, c.offset ?? 0, units);
}

/** The next or previous spoken block (headings are skipped), or null at either end. */
export function stepTarget(blocks: Block[], from: number, step: 1 | -1): number | null {
  for (let i = from + step; i >= 0 && i < blocks.length; i += step) {
    if (!blocks[i]?.heading) return i;
  }
  return null;
}

/** A cue sheet's pages: the server's list (pages that start inside the script, in order), or else one page for each
 * run of blocks with the same `page`. */
export function normalizePages(raw: PrompterPage[] | undefined, blocks: Block[]): Page[] {
  const unit = (first: number) => blocks[first]?.unit ?? null;
  if (raw?.length) {
    return raw
      .filter((p, i) => Number.isInteger(p.first) && p.first >= 0 && p.first < blocks.length && (i === 0 || p.first > raw[i - 1]!.first))
      .map((p) => ({ page: p.page, label: p.label || p.page, first: p.first, short: Boolean(p.short), unit: unit(p.first) }));
  }
  const pages: Page[] = [];
  blocks.forEach((b, i) => {
    if (b.page && b.page !== blocks[i - 1]?.page) pages.push({ page: b.page, label: b.page, first: i, short: false, unit: unit(i) });
  });
  return pages;
}

/** The index of the page that holds `block` (-1 without pages). */
export function pageAt(pages: Page[], block: number): number {
  let k = -1;
  pages.forEach((p, i) => {
    if (p.first <= block) k = i;
  });
  return pages.length ? Math.max(0, k) : -1;
}

/** Where Previous, Next and Repeat go on a cue sheet: the first block of the page before, after or of `from`. null at
 * either end (crewcut/prompter.py has the same rule). */
export function pageStep(pages: Page[], from: number, kind: "prev" | "next" | "repeat"): number | null {
  const k = pageAt(pages, from);
  if (k < 0) return null;
  const target = pages[kind === "next" ? k + 1 : kind === "prev" ? k - 1 : k];
  return target ? target.first : null;
}

/** The same change the server makes, so this screen shows a command at once (and a screen without a server works). */
export function reduce(c: PrompterControl, patch: ControlPatch, weights: number[], cps: number, now: number): PrompterControl {
  const here = placeAt(c, weights, cps, now);
  const next: PrompterControl = { ...c };
  for (const key of ["playing", "mirror"] as const) if (patch[key] !== undefined) next[key] = Boolean(patch[key]);
  if (patch.speed !== undefined && Number.isFinite(patch.speed)) next.speed = clamp(patch.speed, 0.2, 4);
  if (patch.size !== undefined && Number.isFinite(patch.size)) next.size = clamp(patch.size, 0.5, 3);
  if (patch.guide !== undefined && Number.isFinite(patch.guide)) next.guide = clamp(patch.guide, 10, 85);
  let block = here.block;
  let offset = here.offset;
  let moved = false;
  let hold = false;
  const last = Math.max(0, weights.length - 1);
  if (patch.action === "start" || (patch.action && ["jump", "next", "prev", "repeat"].includes(patch.action) &&
      Number.isFinite(patch.block))) {
    block = patch.action === "start" ? 0 : clamp(Math.trunc(patch.block!), 0, last);
    offset = 0;
    moved = true;
    if (patch.action === "start") next.playing = false;
    next.cue = (c.cue ?? 0) + 1;
    hold = next.playing;
  } else if ((patch.action === "scroll" || patch.action === "scrolled") && Number.isFinite(patch.block) &&
      Number.isFinite(patch.offset)) {
    block = clamp(Math.trunc(patch.block!), 0, last);
    offset = clamp(patch.offset!, 0, 1);
    moved = true;
  } else if (patch.action === "end") {
    if (!(here.end && c.playing)) return c;
    next.playing = false;
  }
  next.block = block;
  next.offset = offset;
  if (hold) next.at = now + JUMP_HOLD_MS;
  else if (moved || !next.playing || !c.playing) next.at = now;
  else next.at = Math.max(now, c.at ?? now);
  return next;
}

/** An estimate of the server clock. Each answer carries the server time; the network time is the round trip minus the
 * time the server waited, and the answer with the shortest round trip of the last eight wins. */
export class ClockSync {
  private samples: Array<{ rtt: number; offset: number }> = [];
  private best = 0;

  constructor(private local: () => number = () => Date.now()) {}

  sample(sent: number, received: number, serverNow: number | undefined, waited = 0): void {
    if (serverNow === undefined || !Number.isFinite(serverNow)) return;
    const rtt = Math.max(0, received - sent - (Number.isFinite(waited) ? waited : 0));
    this.samples = [...this.samples.slice(-7), { rtt, offset: serverNow + rtt / 2 - received }];
    this.best = this.samples.reduce((a, b) => (b.rtt < a.rtt ? b : a)).offset;
  }

  /** After the phone slept its clock may have jumped: forget the old answers. */
  reset(): void {
    this.samples = [];
  }

  now(): number {
    return this.local() + this.best;
  }
}
