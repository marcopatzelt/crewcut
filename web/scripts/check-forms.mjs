// DESIGN.md rule 1.2, 3, 15 and 16: the app has two text fields, the composer and the search field of the command
// palette (which only picks from a list), and no <form> with more than one field.
import { lineOf, read, rel, report, srcRoot, walk } from "./lib.mjs";

const TEXT_TYPES = new Set(["text", "search", "email", "url", "number", "password", "tel", "date", "time", ""]);
// One text field in each of these files, and nowhere else.
const ALLOWED = new Map([
  ["src/components/Composer.tsx", "the composer"],
  ["src/components/Palette.tsx", "the palette's search field"],
]);

const problems = [];
const textFields = [];

function fieldsIn(text) {
  const found = [];
  for (const m of text.matchAll(/<(input|textarea|select)\b([^>]*)>/g)) {
    const [, tag, attrs] = m;
    if (tag === "input") {
      const type = (attrs.match(/\btype\s*=\s*["{']?([\w-]+)/) ?? [, ""])[1].toLowerCase();
      if (type === "hidden") continue;
      found.push({ index: m.index, tag, type, text: TEXT_TYPES.has(type) });
    } else {
      found.push({ index: m.index, tag, type: tag, text: true });
    }
  }
  for (const m of text.matchAll(/contentEditable|role\s*=\s*["']textbox["']/g)) {
    found.push({ index: m.index, tag: "editable", type: "editable", text: true });
  }
  return found;
}

for (const file of walk(srcRoot, [".tsx", ".ts", ".html"])) {
  if (/\.test\.tsx?$/.test(file) || file.includes("/test/")) continue;
  const text = read(file);
  for (const f of fieldsIn(text)) {
    const what = f.tag === "input" ? `<input type="${f.type || "text"}">` : `<${f.tag}>`;
    if (f.text) textFields.push(`${rel(file)}:${lineOf(text, f.index)} ${what}`);
    if (f.text && !ALLOWED.has(rel(file))) {
      problems.push(`${rel(file)}:${lineOf(text, f.index)} text field outside the composer and the palette (<${f.tag}>)`);
    }
  }
  for (const m of text.matchAll(/<form\b[\s\S]*?<\/form>/g)) {
    const n = fieldsIn(m[0]).length;
    if (n > 1) problems.push(`${rel(file)}:${lineOf(text, m.index)} <form> with ${n} fields`);
  }
}

for (const [file, what] of ALLOWED) {
  const here = textFields.filter((f) => f.startsWith(`${file}:`));
  if (here.length !== 1) problems.push(`expected exactly one text field in ${file} (${what}), found ${here.length}`);
}
if (textFields.length !== ALLOWED.size) {
  problems.push(`expected ${ALLOWED.size} text fields (composer and palette), found ${textFields.length}: ${textFields.join(", ") || "none"}`);
}

report("check:forms", problems, `two text fields (${textFields.join(", ") || "none"}), no multi-field forms`);
