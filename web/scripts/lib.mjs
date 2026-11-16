// Shared helpers for the design checks in this folder.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

export const webRoot = fileURLToPath(new URL("..", import.meta.url));
export const srcRoot = join(webRoot, "src");

export function walk(dir, exts) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p, exts));
    else if (exts.some((e) => name.endsWith(e))) out.push(p);
  }
  return out.sort();
}

export const rel = (p) => relative(webRoot, p);
export const read = (p) => readFileSync(p, "utf8");

export function lineOf(text, index) {
  return text.slice(0, index).split("\n").length;
}

export function report(name, problems, okText) {
  if (problems.length) {
    for (const p of problems) console.error(`FAIL ${p}`);
    console.error(`${name}: ${problems.length} problem(s)`);
    process.exit(1);
  }
  console.log(`${name}: ${okText}`);
}

/**
 * A small CSS reader for the design checks: every style rule with its selector, its declarations and the at-rules
 * around it (for example ["@supports (backdrop-filter: blur(1px))"]). Keyframes come back with their name.
 */
export function cssRules(text) {
  const css = text.replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, " "));
  const rules = [];
  const keyframes = [];
  let i = 0;

  function readBlock(context) {
    let start = i;
    while (i < css.length) {
      const ch = css[i];
      if (ch === "}") {
        i += 1;
        return;
      }
      if (ch === ";") {
        i += 1;
        start = i;
        continue;
      }
      if (ch === "{") {
        const prelude = css.slice(start, i).trim();
        const at = start + css.slice(start, i).search(/\S/);
        i += 1;
        if (/^@(-webkit-)?keyframes\b/.test(prelude)) {
          const name = prelude.split(/\s+/)[1];
          const bodyStart = i;
          let depth = 1;
          while (i < css.length && depth > 0) {
            if (css[i] === "{") depth += 1;
            else if (css[i] === "}") depth -= 1;
            i += 1;
          }
          keyframes.push({ name, body: css.slice(bodyStart, i - 1), index: at, context });
        } else if (prelude.startsWith("@")) {
          readBlock([...context, prelude.replace(/\s+/g, " ")]);
        } else {
          const bodyStart = i;
          while (i < css.length && css[i] !== "}") i += 1;
          const body = css.slice(bodyStart, i);
          i += 1;
          const decls = [];
          for (const d of body.split(";")) {
            const m = d.match(/^\s*([-\w]+)\s*:\s*([\s\S]+?)\s*$/);
            if (m) decls.push({ prop: m[1].toLowerCase(), value: m[2] });
          }
          const selectors = prelude.split(",").map((x) => x.trim().replace(/\s+/g, " "));
          rules.push({ selectors, decls, index: at, context });
        }
        start = i;
        continue;
      }
      i += 1;
    }
  }

  readBlock([]);
  return { rules, keyframes };
}
