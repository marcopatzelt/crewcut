// DESIGN.md rule 1.2, 3 and 16: the app has one text input (the composer) and no <form> with more than one field.
import { lineOf, read, rel, report, srcRoot, walk } from "./lib.mjs";

const TEXT_TYPES = new Set(["text", "search", "email", "url", "number", "password", "tel", "date", "time", ""]);
const ALLOWED_FILE = "src/components/Composer.tsx";

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
    if (f.text && rel(file) !== ALLOWED_FILE) {
      problems.push(`${rel(file)}:${lineOf(text, f.index)} text field outside the composer (<${f.tag}>)`);
    }
  }
  for (const m of text.matchAll(/<form\b[\s\S]*?<\/form>/g)) {
    const n = fieldsIn(m[0]).length;
    if (n > 1) problems.push(`${rel(file)}:${lineOf(text, m.index)} <form> with ${n} fields`);
  }
}

if (textFields.length !== 1) {
  problems.push(`expected exactly one text field (the composer), found ${textFields.length}: ${textFields.join(", ") || "none"}`);
}

report("check:forms", problems, `one text field (${textFields[0] ?? "none"}), no multi-field forms`);
