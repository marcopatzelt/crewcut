// DESIGN.md rule 8, 10 and 16: no emoji, no exclamation marks in user-facing text, and no "OK", "Submit" or "Yes"
// buttons in src/. Text means string literals, template text and JSX text, read with the TypeScript parser,
// so the "!" operator in code is not counted.
import ts from "typescript";
import { webRoot, lineOf, read, rel, report, srcRoot, walk } from "./lib.mjs";
import { join } from "node:path";

const EMOJI = /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}️]/u;
const BANNED_LABELS = new Set(["ok", "okay", "submit", "yes"]);

const problems = [];

// In JSX attributes only these carry words a person reads; class names, roles and ids are code.
const TEXT_ATTRIBUTES = new Set(["aria-label", "title", "placeholder", "alt", "label", "aria-description", "data-tip"]);

function attributeName(node) {
  const p = node.parent;
  if (p && ts.isJsxAttribute(p)) return p.name.getText();
  if (p && ts.isJsxExpression(p) && p.parent && ts.isJsxAttribute(p.parent)) return p.parent.name.getText();
  return null;
}

function checkText(file, source, node, value) {
  const attr = attributeName(node);
  if (attr !== null && !TEXT_ATTRIBUTES.has(attr)) return;
  const where = `${rel(file)}:${source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1}`;
  if (value.includes("!")) problems.push(`${where} exclamation mark in "${value.trim().slice(0, 60)}"`);
  if (BANNED_LABELS.has(value.trim().toLowerCase())) problems.push(`${where} banned label "${value.trim()}"`);
}

function visit(file, source, node) {
  if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) return;
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    checkText(file, source, node, node.text);
  } else if (ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
    checkText(file, source, node, node.text);
  } else if (ts.isJsxText(node)) {
    if (node.text.trim()) checkText(file, source, node, node.text);
  }
  ts.forEachChild(node, (child) => visit(file, source, child));
}

const files = walk(srcRoot, [".ts", ".tsx", ".css", ".html"]).concat(
  ["index.html", "prompter.html"].map((f) => join(webRoot, f)),
);
for (const file of files) {
  const text = read(file);
  const e = text.match(EMOJI);
  if (e) problems.push(`${rel(file)}:${lineOf(text, e.index)} emoji "${e[0]}"`);
  if (!/\.tsx?$/.test(file) || /\.test\.tsx?$/.test(file) || file.includes("/test/")) continue;
  const kind = file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  visit(file, source, source);
}

report("check:words", problems, `no emoji, exclamation marks or banned labels in ${files.length} files`);
