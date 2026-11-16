// Slate, the Crewcut mascot: a clapperboard with a face. Its striped top bar is the "flat-top crew cut".
// Hand-built geometry, one source for the app (inline SVG with CSS colours and animations) and for the static brand
// files (tools/brand/build.mjs fills in hex colours). No colour values here: every colour comes from a palette.
//
// Coordinates: the figure lives in a 0..128 space. The bar turns around its hinge, the bottom-left corner of the bar
// (8, 47); open is -13.4 degrees, shut is 0. The state marks (Zzz, motion lines, "?" sign, check) sit top right.

export type SlateState = "plain" | "idle" | "working" | "waiting" | "done" | "wave";
export type SlateProp = "headset" | "magnifier" | "pencil" | "scissors" | "clipboard" | "brush" | "plane" | "swatches";

export const PROPS: readonly SlateProp[] = [
  "headset",
  "magnifier",
  "pencil",
  "scissors",
  "clipboard",
  "brush",
  "plane",
  "swatches",
];

export interface Palette {
  body: string; // the board and the bar
  stripe: string; // the stripes of the bar
  face: string; // eyes and mouth
  tile: string; // the round or square tile behind an avatar or an icon
  paper: string; // white parts of the props
  red: string; // the Critic's check
  soft: string; // a pale accent inside props
}

/** The app's palette: CSS custom properties from tokens.css, so light and dark mode follow the theme. */
export const CSS_PALETTE: Palette = {
  body: "var(--slate-body)",
  stripe: "var(--slate-stripe)",
  face: "var(--slate-face)",
  tile: "var(--slate-tile)",
  paper: "var(--slate-paper)",
  red: "var(--slate-red)",
  soft: "var(--slate-soft)",
};

export const OPEN = -13.4;
const HINGE = "8 47";
/** The figure's bounds with the bar open (without marks, legs or props). */
export const BOUNDS = { x: 3.8, y: 6.8, w: 99.5, h: 91.9 };

const f = (n: number) => String(Math.round(n * 100) / 100);

function bar(p: Palette, angle: number): string {
  const stripes = [13, 42, 71]
    .map((b) => `<path d="M${f(b + 7.5)} 31.6H${f(b + 18.5)}L${f(b + 11)} 44.4H${b}Z" fill="${p.stripe}"/>`)
    .join("");
  return (
    `<g class="sl-bar" transform="rotate(${angle} ${HINGE})">` +
    `<rect x="8" y="29" width="98" height="18" rx="7" fill="${p.body}"/>${stripes}</g>`
  );
}

function face(p: Palette, state: SlateState): string {
  const smile = `<path d="M51.2 81Q58.3 81.9 65.4 81C65.4 86.6 62.2 90 58.3 90C54.4 90 51.2 86.6 51.2 81Z" fill="${p.face}"/>`;
  const small = `<path d="M53.5 82Q58.3 82.6 63.1 82C63.1 85.6 61 88 58.3 88C55.6 88 53.5 85.6 53.5 82Z" fill="${p.face}"/>`;
  const arc = (d: string) =>
    `<path d="${d}" fill="none" stroke="${p.face}" stroke-width="3.8" stroke-linecap="round"/>`;
  if (state === "idle") {
    return `<g class="sl-face">${arc("M33.5 71Q41.5 77.5 49.5 71")}${arc("M67 71Q75 77.5 83 71")}${small}</g>`;
  }
  if (state === "done") {
    return `<g class="sl-face">${arc("M33.5 74Q41.5 65.5 49.5 74")}${arc("M67 74Q75 65.5 83 74")}${smile}</g>`;
  }
  const eye = (x: number) =>
    `<ellipse cx="${x}" cy="70.5" rx="8.2" ry="11" fill="${p.face}"/>` +
    `<circle cx="${f(x + 4.2)}" cy="70.5" r="5.2" fill="${p.body}"/>`;
  return `<g class="sl-face">${eye(41.5)}${eye(75)}${smile}</g>`;
}

function legs(p: Palette): string {
  return (
    `<g class="sl-legs" fill="${p.body}">` +
    `<rect x="35" y="96" width="9" height="15" rx="4"/><rect x="66" y="96" width="9" height="15" rx="4"/>` +
    `<ellipse cx="38" cy="111.5" rx="7.5" ry="4.5"/><ellipse cx="72" cy="111.5" rx="7.5" ry="4.5"/></g>`
  );
}

function arm(p: Palette): string {
  // A raised arm that waves from the shoulder (bottom left of the group's box).
  return (
    `<g class="sl-arm">` +
    `<path d="M100 74C108 70 112 62 112 52" fill="none" stroke="${p.body}" stroke-width="8" stroke-linecap="round"/>` +
    `<circle cx="112.5" cy="46" r="7.5" fill="${p.body}"/>` +
    `<path d="M106.5 41.5Q105 37.5 108 36" fill="none" stroke="${p.body}" stroke-width="4.5" stroke-linecap="round"/>` +
    `</g>`
  );
}

/** The board, the bar and the face: the figure without props, legs or marks. */
export function figure(p: Palette, state: SlateState = "plain"): string {
  const angle = state === "done" ? 0 : OPEN;
  return (
    bar(p, angle) +
    `<rect class="sl-body" x="10" y="48" width="92" height="51" rx="9.5" fill="${p.body}"/>` +
    face(p, state)
  );
}

/** The state mark in a 30x30 box, placed by the caller. */
export function stateMark(p: Palette, state: SlateState): string {
  const line = (d: string, w = 3.2) =>
    `<path d="${d}" fill="none" stroke="${p.body}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  if (state === "idle") {
    return (
      `<g class="sl-z sl-z1">${line("M15 3H26L15 14H26", 3)}</g>` +
      `<g class="sl-z sl-z2">${line("M6 15H14L6 23H14", 2.6)}</g>` +
      `<g class="sl-z sl-z3">${line("M1 24.5H6.5L1 30H6.5", 2.2)}</g>`
    );
  }
  if (state === "working") {
    return `<g class="sl-mark">${line("M5 17L1.5 8")}${line("M10.5 21L19 14")}${line("M12 28.5H22")}</g>`;
  }
  if (state === "waiting") {
    return (
      `<g class="sl-mark">` +
      `<rect x="14" y="20" width="3.2" height="10" rx="1.6" fill="${p.body}"/>` +
      `<rect x="4" y="1.5" width="23" height="20" rx="4.5" fill="${p.paper}" stroke="${p.body}" stroke-width="2.6"/>` +
      line("M11.6 8.6Q11.6 5.4 15.5 5.4Q19.4 5.4 19.4 8.6Q19.4 10.8 15.5 12.2V13.6", 2.6) +
      `<circle cx="15.5" cy="17.4" r="1.7" fill="${p.body}"/></g>`
    );
  }
  if (state === "done") {
    return (
      `<g class="sl-mark"><circle cx="15" cy="15" r="12.5" fill="${p.paper}" stroke="${p.body}" stroke-width="2.6"/>` +
      `${line("M9.5 15.5L13.5 19.5L20.5 11", 3.2)}</g>`
    );
  }
  if (state === "wave") {
    return `<g class="sl-mark">${line("M6 10L2.5 3")}${line("M12 8.5L14 1")}${line("M17 13L23.5 9")}</g>`;
  }
  return "";
}

/** A tile-coloured outline under a prop's shapes: it separates the prop from the board where they overlap. */
function halo(p: Palette, inner: string, extra = 4.5): string {
  return inner.replace(/<(path|circle|rect|ellipse)\b([^>]*?)(\/?)>/g, (_m, tag: string, attrs: string, close: string) => {
    const stroked = /\sstroke="(?!none)/.test(attrs);
    const width = (stroked ? Number(/stroke-width="([\d.]+)"/.exec(attrs)?.[1] ?? 0) : 0) + extra;
    const rest = attrs
      .replace(/\s(stroke|stroke-width|stroke-linejoin|stroke-linecap)="[^"]*"/g, "")
      .replace(/fill="(?!none)[^"]*"/g, `fill="${p.tile}"`);
    return `<${tag}${rest} stroke="${p.tile}" stroke-width="${f(width)}" stroke-linejoin="round" stroke-linecap="round"${close}>`;
  });
}

/** One prop per crew member, drawn in avatar space (0..128), held on the right of the board. */
export function prop(p: Palette, which: SlateProp): string {
  const both = (inner: string) => `<g class="sl-halo">${halo(p, inner)}</g>${inner}`;
  const s = (d: string, w: number, color = p.body) =>
    `<path d="${d}" fill="none" stroke="${color}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  switch (which) {
    case "headset":
      return (
        `<g class="sl-prop">` +
        both(s("M14 62C12 30 84 26 86 60", 5.5)) +
        both(`<rect x="7" y="57" width="12" height="22" rx="5.5" fill="${p.body}"/>`) +
        both(`<rect x="80" y="55" width="13" height="24" rx="6" fill="${p.body}"/>`) +
        both(s("M86 78C86 90 76 95 66 95", 4)) +
        both(`<rect x="57" y="91" width="11" height="8" rx="4" fill="${p.body}"/>`) +
        `</g>`
      );
    case "magnifier":
      return (
        `<g class="sl-prop">` +
        both(s("M104 86L116 100", 8)) +
        both(`<circle cx="96" cy="76" r="13" fill="${p.paper}" stroke="${p.body}" stroke-width="5"/>`) +
        s("M89.5 72Q91 67.5 95.5 66.5", 2.6, p.soft) +
        `</g>`
      );
    case "pencil":
      return (
        `<g class="sl-prop"><g transform="rotate(26 98 80)">` +
        both(
          `<path d="M92 62H104V102H92Z" fill="${p.paper}" stroke="${p.body}" stroke-width="2.6" stroke-linejoin="round"/>` +
            `<path d="M92 62L98 48L104 62Z" fill="${p.soft}" stroke="${p.body}" stroke-width="2.6" stroke-linejoin="round"/>`,
        ) +
        `<path d="M96 53.4L98 48L100 53.4Z" fill="${p.body}"/>` +
        `<rect x="92" y="100" width="12" height="9" rx="2.5" fill="${p.body}"/>` +
        `<path d="M98 66V98" stroke="${p.soft}" stroke-width="2.4"/>` +
        `</g></g>`
      );
    case "scissors":
      return (
        `<g class="sl-prop">` +
        both(s("M93 92L106 54", 5)) +
        both(s("M106 92L96 56", 5)) +
        both(`<circle cx="91" cy="99" r="6.5" fill="none" stroke="${p.body}" stroke-width="4"/>`) +
        both(`<circle cx="108" cy="99" r="6.5" fill="none" stroke="${p.body}" stroke-width="4"/>`) +
        `<circle cx="99.5" cy="74" r="2.2" fill="${p.paper}"/>` +
        `</g>`
      );
    case "clipboard":
      return (
        `<g class="sl-prop">` +
        both(`<rect x="82" y="58" width="32" height="44" rx="5" fill="${p.paper}" stroke="${p.body}" stroke-width="3"/>`) +
        `<rect x="91" y="53" width="14" height="9" rx="2.5" fill="${p.body}"/>` +
        s("M89 81L96 88.5L107.5 72", 4.4, p.red) +
        `</g>`
      );
    case "brush":
      return (
        `<g class="sl-prop">` +
        both(s("M90 106L102 76", 6.5)) +
        both(`<path d="M99 79L104.5 66.5L111 69.5L105.5 82Z" fill="${p.paper}" stroke="${p.body}" stroke-width="2.4" stroke-linejoin="round"/>`) +
        both(`<path d="M105 67C104 58 108 51 114 47C116 54 114.5 62 111 69.5Z" fill="${p.body}"/>`) +
        `</g>`
      );
    case "plane":
      return (
        `<g class="sl-prop">` +
        both(`<path d="M80 80L120 56L102 100L95 85Z" fill="${p.paper}" stroke="${p.body}" stroke-width="3" stroke-linejoin="round"/>`) +
        s("M95 85L120 56", 2.6) +
        `</g>`
      );
    case "swatches":
      return (
        `<g class="sl-prop">` +
        both(
          `<g transform="rotate(-9 92 104)"><rect x="83" y="56" width="17" height="48" rx="3.5" fill="${p.paper}" stroke="${p.body}" stroke-width="2.6"/></g>`,
        ) +
        `<g transform="rotate(-9 92 104)"><rect x="86" y="59" width="11" height="12" rx="1.5" fill="${p.body}"/>` +
        `<rect x="86" y="73" width="11" height="12" rx="1.5" fill="${p.stripe}"/>` +
        `<rect x="86" y="87" width="11" height="12" rx="1.5" fill="${p.soft}"/></g>` +
        both(
          `<g transform="rotate(10 106 104)"><rect x="98" y="56" width="17" height="48" rx="3.5" fill="${p.paper}" stroke="${p.body}" stroke-width="2.6"/></g>`,
        ) +
        `<g transform="rotate(10 106 104)"><rect x="101" y="59" width="11" height="12" rx="1.5" fill="${p.stripe}"/>` +
        `<rect x="101" y="73" width="11" height="12" rx="1.5" fill="${p.soft}"/>` +
        `<rect x="101" y="87" width="11" height="12" rx="1.5" fill="${p.body}"/></g>` +
        `</g>`
      );
  }
}

function svg(viewBox: string, body: string, opts: { size?: number; title?: string; cls?: string } = {}): string {
  const size = opts.size ? ` width="${opts.size}" height="${opts.size}"` : "";
  const label = opts.title
    ? ` role="img" aria-label="${opts.title}"><title>${opts.title}</title>`
    : ` aria-hidden="true" focusable="false">`;
  const cls = opts.cls ? ` class="${opts.cls}"` : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}"${size}${cls}${label}${body}</svg>`;
}

/** A crew member: Slate with its prop on a round tile, and the state mark when it works, waits, sleeps or is done. */
export function avatar(
  p: Palette,
  which: SlateProp | null,
  state: SlateState = "plain",
  opts: { size?: number; title?: string; tile?: boolean } = {},
): string {
  const tile = opts.tile === false ? "" : `<circle class="sl-tile" cx="64" cy="64" r="64" fill="${p.tile}"/>`;
  const shift = which ? "translate(5 28) scale(0.77)" : "translate(17 26) scale(0.8)";
  const mark = stateMark(p, state);
  const marks = mark ? `<g transform="translate(87 1) scale(1.25)">${mark}</g>` : "";
  const body = `${tile}<g transform="${shift}">${figure(p, state)}</g>${which ? prop(p, which) : ""}${marks}`;
  return svg("0 0 128 128", body, { size: opts.size, title: opts.title });
}

/** Slate standing: legs, the state mark, and for "wave" a raised arm. Used in the empty states and the welcome. */
export function standing(p: Palette, state: SlateState = "plain", opts: { size?: number; title?: string } = {}): string {
  const mark = stateMark(p, state);
  const marks = mark ? `<g transform="${state === "wave" ? "translate(116 22)" : "translate(104 0)"}">${mark}</g>` : "";
  const body = `<g transform="translate(6 10)">${legs(p)}${figure(p, state)}${state === "wave" ? arm(p) : ""}</g>${marks}`;
  return svg("0 0 150 128", body, { size: opts.size, title: opts.title });
}

/** The logo mark: the figure alone, open and smiling, on a transparent background. */
export function mark(p: Palette, opts: { size?: number; title?: string } = {}): string {
  const pad = 3;
  const s = Math.max(BOUNDS.w, BOUNDS.h) + pad * 2;
  const x = BOUNDS.x + BOUNDS.w / 2 - s / 2;
  const y = BOUNDS.y + BOUNDS.h / 2 - s / 2;
  return svg(`${f(x)} ${f(y)} ${f(s)} ${f(s)}`, figure(p, "plain"), opts);
}

/** The app icon: the figure on a rounded square tile. Safe on light and dark backgrounds. */
export function appIcon(p: Palette, opts: { size?: number; title?: string } = {}): string {
  const scale = 0.86;
  const tx = 64 - (BOUNDS.x + BOUNDS.w / 2) * scale;
  const ty = 66 - (BOUNDS.y + BOUNDS.h / 2) * scale;
  const body =
    `<rect class="sl-tile" width="128" height="128" rx="29" fill="${p.tile}"/>` +
    `<g transform="translate(${f(tx)} ${f(ty)}) scale(${scale})">${figure(p, "plain")}</g>`;
  return svg("0 0 128 128", body, opts);
}

/** The small icon (16 and 32 px): fewer details, drawn on the pixel grid. */
export function smallIcon(p: Palette, opts: { size?: number } = {}): string {
  const body =
    `<rect width="16" height="16" rx="3.6" fill="${p.tile}"/>` +
    `<path d="M1.6 5.4L12.9 2.5Q14 2.2 14.3 3.3L14.6 4.6L2.3 7.7Q1.6 7.8 1.4 7.1Z" fill="${p.body}"/>` +
    `<path d="M3.6 6.9L5.6 4.4H7.3L5.3 6.5Z M7.6 5.9L9.6 3.5H11.2L9.2 5.5Z" fill="${p.stripe}"/>` +
    `<rect x="1.8" y="8" width="12.4" height="6.6" rx="1.8" fill="${p.body}"/>` +
    `<circle cx="6.1" cy="10.6" r="1.25" fill="${p.face}"/><circle cx="10.1" cy="10.6" r="1.25" fill="${p.face}"/>` +
    `<path d="M7.1 12.6H9.1Q9 13.6 8.1 13.6Q7.2 13.6 7.1 12.6Z" fill="${p.face}"/>`;
  return svg("0 0 16 16", body, opts);
}
