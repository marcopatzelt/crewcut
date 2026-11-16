// DESIGN.md rule 18 and 16: material (a blurred, translucent surface) only on the allowed surfaces, and each one
// in the five steps of the rule: an opaque background first, the blur only inside @supports, opaque again under
// prefers-reduced-transparency and under prefers-contrast: more.
import { cssRules, lineOf, read, rel, report, srcRoot, walk } from "./lib.mjs";

// The surfaces that may use material: the window (one sheet of glass on the desk), the tags on pictures, the palette,
// the teleprompter dialog, and the control capsule of the teleprompter page.
const ALLOWED = new Set([".window", ".glass-tag", ".palette", ".popover", ".pr-panel"]);
const OPAQUE = /^var\(--(panel|card|bg|tag-solid|prompter-panel|prompter-bg)\)$/;
const TRANSLUCENT = /^var\(--(material-[\w-]+|prompter-material)\)$/;

const problems = [];
let surfaces = 0;

const isBlur = (d) => (d.prop === "backdrop-filter" || d.prop === "-webkit-backdrop-filter") && d.value.trim() !== "none";
const background = (r) => r.decls.find((d) => d.prop === "background" || d.prop === "background-color");

for (const file of walk(srcRoot, [".css"])) {
  if (file.endsWith("styles/tokens.css")) continue;
  const text = read(file);
  const { rules } = cssRules(text);
  const where = (r) => `${rel(file)}:${lineOf(text, r.index)}`;

  const material = new Set();
  for (const r of rules) {
    if (!r.decls.some(isBlur)) continue;
    const inSupports = r.context.some((c) => /^@supports\b.*backdrop-filter/.test(c));
    if (!inSupports) problems.push(`${where(r)} backdrop-filter outside @supports (${r.selectors.join(", ")})`);
    const bg = background(r);
    if (!bg || !TRANSLUCENT.test(bg.value.trim())) {
      problems.push(`${where(r)} material without a --material-* background (${r.selectors.join(", ")})`);
    }
    for (const sel of r.selectors) {
      if (!ALLOWED.has(sel)) problems.push(`${where(r)} material on ${sel}, which is not an allowed surface (rule 18)`);
      material.add(sel);
    }
  }
  surfaces += material.size;

  for (const sel of material) {
    // 1. an opaque base before the @supports block, outside any at-rule
    const blurAt = Math.min(...rules.filter((r) => r.selectors.includes(sel) && r.decls.some(isBlur)).map((r) => r.index));
    const base = rules.find(
      (r) => r.context.length === 0 && r.selectors.includes(sel) && r.index < blurAt && OPAQUE.test(background(r)?.value.trim() ?? ""),
    );
    if (!base) problems.push(`${rel(file)}: ${sel} has no opaque background (--panel or --card) before its material`);
    // 4 and 5: opaque again for reduced transparency and for more contrast
    for (const [media, name] of [
      [/prefers-reduced-transparency:\s*reduce/, "prefers-reduced-transparency: reduce"],
      [/prefers-contrast:\s*more/, "prefers-contrast: more"],
    ]) {
      const fallback = rules.find(
        (r) =>
          r.selectors.includes(sel) &&
          r.context.some((c) => media.test(c)) &&
          OPAQUE.test(background(r)?.value.trim() ?? "") &&
          r.decls.some((d) => d.prop === "backdrop-filter" && d.value.trim() === "none"),
      );
      if (!fallback) problems.push(`${rel(file)}: ${sel} has no opaque fallback under ${name}`);
    }
  }
}

// Inline styles in components may not add material behind the checks' back.
for (const file of walk(srcRoot, [".tsx", ".ts"])) {
  if (/\.test\.tsx?$/.test(file) || file.includes("/test/")) continue;
  const text = read(file);
  for (const m of text.matchAll(/backdropFilter|backdrop-filter/g)) {
    problems.push(`${rel(file)}:${lineOf(text, m.index)} backdrop-filter in a component; use the CSS surfaces`);
  }
}

report("check:materials", problems, `${surfaces} material surfaces, each opaque first, in @supports, with both fallbacks`);
