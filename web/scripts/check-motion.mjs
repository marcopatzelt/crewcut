// DESIGN.md rule 9 and 16: every animation has a prefers-reduced-motion branch; nothing loops except the run shimmer
// (work running) and the loading spinner; transitions and keyframes move only transform, opacity and grid tracks.
import { cssRules, lineOf, read, rel, report, srcRoot, walk } from "./lib.mjs";

const LOOPS = new Set(["run", "spin"]);
const KEYFRAME_PROPS = new Set(["opacity", "transform", "grid-template-rows", "grid-template-columns", "visibility"]);
// Layout properties: animating them makes the page reflow on every frame.
const LAYOUT = /^(all|width|height|min-width|min-height|max-width|max-height|top|right|bottom|left|inset|margin(-[\w-]+)?|padding(-[\w-]+)?|flex(-basis)?|font-size|line-height|border(-[\w-]+)?-width)$/;

const problems = [];
let animated = 0;

const reduced = (r) => r.context.some((c) => /prefers-reduced-motion:\s*reduce/.test(c));
const animates = (d) =>
  (d.prop === "animation" && !/^none\b/.test(d.value.trim())) ||
  (d.prop === "animation-name" && d.value.trim() !== "none");

function animationNames(value) {
  // The keyframe names in an animation shorthand: words that are not timing keywords or functions.
  const keywords = /^(infinite|linear|ease|ease-in|ease-out|ease-in-out|both|forwards|backwards|none|normal|reverse|alternate|alternate-reverse|running|paused|step-start|step-end)$/;
  return value
    .split(",")
    .map((part) =>
      part
        .replace(/[\w-]+\([^)]*\)/g, " ")
        .trim()
        .split(/\s+/)
        .find((w) => w && !keywords.test(w) && !/^[\d.]+m?s$/.test(w) && !/^\d+$/.test(w)),
    )
    .filter(Boolean);
}

for (const file of walk(srcRoot, [".css"])) {
  if (file.endsWith("styles/tokens.css")) continue;
  const text = read(file);
  const { rules, keyframes } = cssRules(text);
  const where = (i) => `${rel(file)}:${lineOf(text, i)}`;

  const covered = new Set();
  for (const r of rules.filter(reduced)) {
    if (r.decls.some((d) => d.prop === "animation" || d.prop === "animation-name")) {
      for (const s of r.selectors) covered.add(s);
    }
  }
  const coversAll = covered.has("*");

  for (const r of rules) {
    for (const d of r.decls) {
      if (animates(d) && !reduced(r)) {
        animated += 1;
        for (const s of r.selectors) {
          if (!coversAll && !covered.has(s)) {
            problems.push(`${where(r.index)} ${s} animates without a prefers-reduced-motion branch`);
          }
        }
        const loops = /\binfinite\b/.test(d.value);
        for (const name of animationNames(d.value)) {
          if (loops && !LOOPS.has(name)) problems.push(`${where(r.index)} infinite animation "${name}" (only run and spin may loop)`);
        }
      }
      if (d.prop === "animation-iteration-count" && /infinite/.test(d.value)) {
        problems.push(`${where(r.index)} animation-iteration-count: infinite; name the loop in the shorthand instead`);
      }
      if (d.prop === "transition" || d.prop === "transition-property") {
        if (reduced(r)) continue;
        for (const part of d.value.split(",")) {
          const prop = part.trim().split(/\s+/)[0];
          if (prop && LAYOUT.test(prop)) problems.push(`${where(r.index)} transition of ${prop}; move transform or opacity`);
        }
      }
    }
  }

  for (const k of keyframes) {
    for (const m of k.body.matchAll(/([-\w]+)\s*:/g)) {
      const prop = m[1].toLowerCase();
      if (!KEYFRAME_PROPS.has(prop)) problems.push(`${where(k.index)} @keyframes ${k.name} animates ${prop}`);
    }
  }
}

// Components may not start animations of their own in inline styles.
for (const file of walk(srcRoot, [".tsx", ".ts"])) {
  if (/\.test\.tsx?$/.test(file) || file.includes("/test/")) continue;
  const text = read(file);
  for (const m of text.matchAll(/\banimation(Name|IterationCount)?\s*:|\binfinite\b/g)) {
    problems.push(`${rel(file)}:${lineOf(text, m.index)} animation in a component; put it in CSS with its reduced-motion branch`);
  }
}

report("check:motion", problems, `${animated} animations, all with a reduced-motion branch; only run and spin loop`);
