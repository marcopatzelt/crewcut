// DESIGN.md rule 4 and 16: every text token clears 4.5:1 on the surfaces it sits on, in both themes.
// Reads src/styles/tokens.css, resolves the light and the dark set, and checks each pair below.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const file = fileURLToPath(new URL("../src/styles/tokens.css", import.meta.url));
const css = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function block(re, name) {
  const m = css.match(re);
  if (!m) throw new Error(`tokens.css: missing the ${name} block`);
  const vars = {};
  for (const d of m[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[d[1]] = d[2].trim();
  return vars;
}

const light = block(/:root\s*,\s*:root\[data-theme="light"\]\s*\{([^}]*)\}/, "light (:root, :root[data-theme=\"light\"])");
const darkAttr = block(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/, "dark (:root[data-theme=\"dark\"])");
const darkMedia = block(
  /@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{([^}]*)\}/,
  "dark media query",
);

let failures = 0;
const fail = (msg) => {
  failures += 1;
  console.error(`FAIL ${msg}`);
};

// The two dark blocks must be identical, or one theme drifts.
for (const k of new Set([...Object.keys(darkAttr), ...Object.keys(darkMedia)])) {
  if (darkAttr[k] !== darkMedia[k]) fail(`dark blocks differ at ${k}: "${darkAttr[k]}" vs "${darkMedia[k]}"`);
}

function parse(value) {
  const v = value.trim();
  let m = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (m) {
    let h = m[1];
    if (h.length === 3) h = [...h].map((c) => c + c).join("");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1];
  }
  m = v.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/i);
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3]), m[4] === undefined ? 1 : Number(m[4])];
  return null;
}

function over(top, base) {
  const a = top[3];
  return [0, 1, 2].map((i) => top[i] * a + base[i] * (1 - a)).concat(1);
}

function lum(c) {
  const ch = c.slice(0, 3).map((x) => {
    const s = x / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

function ratio(a, b) {
  const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// A surface may be a translucent overlay on another surface: "--hover@--panel", also nested:
// "--selected@--material-sidebar@--window". Material is checked twice: as its opaque fallback (--panel) and as
// the translucent colour over the window behind it (rule 18).
function color(vars, spec) {
  const at = spec.indexOf("@");
  const name = at < 0 ? spec : spec.slice(0, at);
  const base = at < 0 ? "" : spec.slice(at + 1);
  const raw = vars[name];
  if (raw === undefined) throw new Error(`unknown token ${name}`);
  const c = parse(raw);
  if (!c) throw new Error(`cannot read ${name}: ${raw}`);
  if (c[3] < 1) {
    if (!base) throw new Error(`${name} is translucent; name the surface below it`);
    return over(c, color(vars, base));
  }
  return c;
}

// A translucent text or ring token is drawn over the surface it is checked against.
function ink(vars, text, surface) {
  const c = parse(vars[text] ?? "");
  if (c && c[3] < 1) return color(vars, `${text}@${surface}`);
  return color(vars, text);
}

// The window is glass over a wallpaper (rule 18): text on it is checked over the brightest and the darkest blurred
// sample of the wallpaper (--desk-hi, --desk-lo) and over the opaque stand-in (--panel). Tiles, chips and row states
// sit on that glass.
const GLASS = ["--material-window@--desk-hi", "--material-window@--desk-lo"];
const onGlass = (layer) => GLASS.map((g) => `${layer}@${g}`);
const surfaces = [
  "--bg",
  "--panel",
  "--card",
  "--sunken",
  "--selected@--panel",
  "--hover@--panel",
  "--hover@--card",
  ...GLASS,
  ...onGlass("--tile"),
  ...onGlass("--chip"),
  ...onGlass("--selected"),
  ...onGlass("--hover"),
  "--tile@--panel",
  "--material-float@--bg",
];
const pairs = [
  // [text, surfaces, minimum]
  ["--ink", surfaces, 4.5],
  ["--ink-2", surfaces, 4.5],
  ["--ink-3", surfaces, 4.5],
  ["--accent", ["--bg", "--panel", "--card", "--selected@--panel", ...GLASS, ...onGlass("--tile")], 4.5],
  ["--accent-ink", ["--accent"], 4.5],
  ["--accent-fill-ink", ["--accent-fill"], 4.5],
  ["--chip-on-ink", ["--chip-on"], 4.5],
  ["--ok", ["--bg", "--panel", "--card", ...onGlass("--tile")], 4.5],
  ["--warn", ["--bg", "--panel", "--card", ...GLASS, ...onGlass("--tile")], 4.5],
  ["--danger", ["--bg", "--panel", "--card", "--sunken", "--material-float@--bg", ...onGlass("--tile")], 4.5],
  // Words on pictures: the tag's opaque stand-in and the tag over a white picture (the worst case).
  ["--tag-ink", ["--tag-solid", "--material-tag@--gpu-base", "--media-fade@--gpu-base"], 4.5],
  ["--gpu-ink", ["--gpu-top@--gpu-base", "--gpu-bottom@--gpu-base"], 4.5],
  ["--gpu-ink-2", ["--gpu-top@--gpu-base", "--gpu-bottom@--gpu-base"], 4.5],
  ["--qr-ink", ["--qr-plate"], 4.5],
  ["--prompter-ink", ["--prompter-bg", "--prompter-panel", "--prompter-material@--prompter-bg"], 4.5],
  ["--prompter-ink-2", ["--prompter-bg", "--prompter-panel", "--prompter-material@--prompter-bg"], 4.5],
  // Focus ring, reading line and the accent dot are not text: 3:1 is the bar (WCAG 1.4.11).
  ["--focus", ["--bg", "--panel", "--card", "--sunken", "--material-float@--bg", ...GLASS], 3],
  ["--prompter-line", ["--prompter-bg"], 3],
];

for (const [theme, vars] of [["light", light], ["dark", darkAttr]]) {
  for (const [text, list, min] of pairs) {
    for (const s of list) {
      const r = ratio(ink(vars, text, s), color(vars, s));
      const line = `${theme.padEnd(5)} ${text} on ${s}: ${r.toFixed(2)}:1`;
      if (r < min) fail(`${line} (needs ${min}:1)`);
      else if (process.argv.includes("--verbose")) console.log(`ok   ${line}`);
    }
  }
}

if (failures) {
  console.error(`check:contrast: ${failures} problem(s)`);
  process.exit(1);
}
console.log("check:contrast: every text token clears its bar in light and dark");
