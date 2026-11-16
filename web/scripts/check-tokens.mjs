// DESIGN.md rule 4 and 16: no raw colour values in src/ outside src/styles/tokens.css.
// Components use var(--token). Test files are skipped; they hold no styles.
import { lineOf, read, rel, report, srcRoot, walk } from "./lib.mjs";

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

report("check:tokens", problems, "no raw colour values outside tokens.css");
