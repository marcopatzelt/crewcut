// Where a place of the shared timeline is on this screen. Phones and the prompter glass wrap the text differently, so
// the place is a block and the share of it, never a share of the whole page: block 12 at 40 % is the same words on
// every screen. Offset 0 puts the block's first line on the reading line; offset 1 is the next block's first line.

export interface Layout {
  /** Top of each block, in the coordinates of the text column. */
  tops: number[];
  /** From each block's top to the next block's top (the last: its height). */
  slots: number[];
  /** Half a line: the reading line sits on the middle of a line. */
  half: number;
  /** The reading point in the text column is scrollTop + offsetY. */
  offsetY: number;
  /** The largest scrollTop. */
  max: number;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Reads the layout of the blocks (direct children of `copy` with data-index) under the reading line. */
export function measure(scroller: HTMLElement, copy: HTMLElement, line: HTMLElement | null, guide: number): Layout | null {
  const items = Array.from(copy.children).filter((el): el is HTMLElement => el instanceof HTMLElement && "index" in el.dataset);
  if (!items.length) return null;
  const tops = items.map((el) => el.offsetTop);
  const slots = items.map((el, i) => Math.max(1, (tops[i + 1] ?? el.offsetTop + el.offsetHeight) - el.offsetTop));
  const scrollerRect = scroller.getBoundingClientRect();
  const lineRect = line?.getBoundingClientRect();
  const lineY = lineRect && lineRect.height > 0 ? lineRect.top + lineRect.height / 2
    : scrollerRect.top + (scroller.clientHeight * guide) / 100;
  const style = getComputedStyle(items[0] as HTMLElement);
  const lineHeight = parseFloat(style.lineHeight) || (parseFloat(style.fontSize) || 0) * 1.35;
  return {
    tops,
    slots,
    half: lineHeight / 2,
    offsetY: lineY - copy.getBoundingClientRect().top - scroller.scrollTop,
    max: Math.max(0, scroller.scrollHeight - scroller.clientHeight),
  };
}

/** The scrollTop that puts (block, offset) on the reading line. */
export function scrollFor(layout: Layout, block: number, offset: number): number {
  const i = clamp(Math.trunc(block) || 0, 0, layout.tops.length - 1);
  const y = (layout.tops[i] ?? 0) + layout.half + clamp(offset, 0, 1) * (layout.slots[i] ?? 1);
  return clamp(y - layout.offsetY, 0, layout.max);
}

/** The place on the reading line at this scrollTop. */
export function placeOn(layout: Layout, scrollTop: number): { block: number; offset: number } {
  const y = scrollTop + layout.offsetY - layout.half;
  if (y <= (layout.tops[0] ?? 0)) return { block: 0, offset: 0 };
  let i = layout.tops.length - 1;
  while (i > 0 && (layout.tops[i] ?? 0) > y) i -= 1;
  return { block: i, offset: clamp((y - (layout.tops[i] ?? 0)) / (layout.slots[i] ?? 1), 0, 1) };
}
