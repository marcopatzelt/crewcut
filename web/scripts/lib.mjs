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
