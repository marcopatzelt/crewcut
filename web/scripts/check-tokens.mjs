// DESIGN.md rules 4, 6, 9 and 16: no raw colour values in src/ outside src/styles/tokens.css, and in the style sheets
// radii, shadows, durations and easing curves only from tokens. Components use var(--token). Test files are skipped.
import { cssRules, lineOf, read, rel, report, srcRoot, walk } from "./lib.mjs";

const NAMED = [
  "white", "black", "red", "green", "blue", "yellow", "orange", "purple", "pink", "gray", "grey", "silver",
  "maroon", "navy", "teal", "olive", "lime", "aqua", "fuchsia", "brown", "gold", "beige", "ivory", "tan",
];
const patterns = [
  { re: /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])/g, what: "hex colour" },
  { re: /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/g, what: "colour function" },
];
const namedInCss = new RegExp(
  `(?:color|background(?:-color)?|border(?:-[a-z]+)?(?:-color)?|fill|stroke|outline(?:-color)?|box-shadow|text-shadow)\\s*:[^;{}]*\\b(${NAMED.join("|")})\\b`,
  "gi",
);

const problems = [];
for (const file of walk(srcRoot, [".ts", ".tsx", ".css", ".html"])) {
  if (file.endsWith("styles/tokens.css") || /\.test\.tsx?$/.test(file) || file.includes("/test/")) continue;
  const text = read(file);
  for (const { re, what } of patterns) {
    for (const m of text.matchAll(re)) {
      // "#/profile" style hash routes and "#1" style labels are not colours; the pattern needs 3+ hex digits.
      problems.push(`${rel(file)}:${lineOf(text, m.index)} raw ${what} "${m[0]}"`);
    }
  }
  if (file.endsWith(".css") || file.endsWith(".tsx")) {
    for (const m of text.matchAll(namedInCss)) {
      problems.push(`${rel(file)}:${lineOf(text, m.index)} named colour "${m[1]}"`);
    }
  }
}

// Radii, shadows, durations and curves (rules 6 and 9).
const RADIUS_OK = /^(var\(--r-[\w-]+\)|0|inherit|50%)$/;
const TIME_PROPS = new Set(["transition", "transition-duration", "transition-delay", "animation", "animation-duration", "animation-delay"]);
for (const file of walk(srcRoot, [".css"])) {
  if (file.endsWith("styles/tokens.css")) continue;
  const text = read(file);
  for (const r of cssRules(text).rules) {
    const where = `${rel(file)}:${lineOf(text, r.index)}`;
    for (const d of r.decls) {
      const v = d.value.replace(/!important/, "").trim();
      if (/^border(-[a-z]+)*-radius$/.test(d.prop)) {
        for (const part of v.split(/\s+(?![^(]*\))/)) {
          if (!RADIUS_OK.test(part)) problems.push(`${where} raw radius "${part}" (use a --r-* token)`);
        }
      }
      if (d.prop === "box-shadow" && v !== "none" && !/var\(--/.test(v)) {
        problems.push(`${where} box-shadow without a token`);
      }
      if (TIME_PROPS.has(d.prop)) {
        for (const m of v.matchAll(/(?<![\w-])(\d*\.?\d+)(ms|s)\b/g)) {
          if (Number(m[1]) !== 0) problems.push(`${where} raw duration "${m[0]}" (use a --t-* token)`);
        }
      }
      if (/^(transition|animation)(-timing-function)?$/.test(d.prop) && /(cubic-bezier|linear)\(/.test(v)) {
        problems.push(`${where} raw easing curve (use --spring-* or --ease-out)`);
      }
    }
  }
}

report("check:tokens", problems, "no raw colours outside tokens.css; radii, shadows, durations and curves from tokens");
