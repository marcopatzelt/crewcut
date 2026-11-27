// A cue sheet on the teleprompter: fixed lines (said word for word) and bullets (said freely) in pages, one page per
// part of the sheet. Hook, punch line and the opening's first line are full size, the other fixed lines a little
// smaller, the ask and the bridge medium, the bullets about two thirds, dimmed, with their tag in small grey capitals.
// Numbers are bold everywhere. Previous, Repeat and Next move by page; each page start is a new take.
import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import { pageAt, type Block, type Page } from "./timeline";

const NUMBER = /\d+(?:[.,:]\d+)*/g;

/** The text with every run of digits in bold ("1,5" and "12:30" stay one number). */
export function withNumbers(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(NUMBER)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    out.push(<strong key={at}>{m[0]}</strong>);
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function takesText(n: number): string {
  if (n <= 0) return "No take yet";
  return n === 1 ? "1 take" : `${n} takes`;
}

/** The class of a cue sheet block: its kind, a fixed line's role and its size. */
export function cueClass(b: Block): string {
  if (b.kind === "bullet") return "pr-block cue bullet";
  return ["pr-block cue fixed", b.role ? `role-${b.role}` : "", b.big ? "big" : ""].filter(Boolean).join(" ");
}

/** One block's words: a fixed line as written (the picture cue as a small tag after it), a bullet as one list item. */
export function CueText({ block }: { block: Block }) {
  const picture = block.picture ? <span className="pr-pic">{block.picture}</span> : null;
  if (block.kind !== "bullet") {
    return <p>{withNumbers(block.text)}{picture ? <>{" "}{picture}</> : null}</p>;
  }
  const groups = block.groups?.length ? block.groups : block.question ? [] : [block.text];
  const parts: ReactNode[] = [];
  if (block.role) parts.push(<span key="role" className="pr-role">{block.role}</span>);
  if (picture) parts.push(<Fragment key="picture">{picture}</Fragment>);
  if (block.question) parts.push(<span key="question" className="pr-question">{withNumbers(block.question)}</span>);
  groups.forEach((g, j) => parts.push(<span key={`g${j}`} className="pr-group">{withNumbers(g)}</span>));
  return (
    <ul>
      <li>{parts.map((part, j) => <Fragment key={j}>{j ? " " : null}{part}</Fragment>)}</li>
    </ul>
  );
}

/** The head of a page on the reading screen: its name, the take in progress and a Short tag. */
export function PageHead({ page, takes, first }: { page: Page; takes: number; first: boolean }) {
  return (
    <div className={first ? "pr-page" : "pr-page break"}>
      <span>{page.label}</span>
      {takes > 0 ? <span>{`Take ${takes}`}</span> : null}
      {page.short ? <span className="pr-pic">Short</span> : null}
    </div>
  );
}

/** Previous, Repeat and Next for pages: Repeat starts a new take of the page on the reading line. */
export function PageBar({ pages, current, takes, step, dim }: {
  pages: Page[];
  current: number;
  takes: Record<string, number> | undefined;
  step: (kind: "prev" | "next" | "repeat") => void;
  dim: boolean;
}) {
  const k = pageAt(pages, current);
  const page = k >= 0 ? pages[k] : undefined;
  const name = page ? (page.unit !== null ? String(page.unit) : page.label) : "";
  const next = page ? (takes?.[page.page] ?? 0) + 1 : 1;
  return (
    <div className={dim ? "pr-panel pr-blocks dim" : "pr-panel pr-blocks"} role="toolbar" aria-label="Pages">
      <button type="button" className="pr-btn pr-step" aria-label="Previous page" disabled={k <= 0}
        onClick={() => step("prev")}>
        <ChevronLeft size={20} aria-hidden="true" />
        Previous
      </button>
      <button type="button" className="pr-btn pr-step repeat"
        aria-label={page ? `Repeat ${page.label}, take ${next}` : "Repeat page"} disabled={!page}
        onClick={() => step("repeat")}>
        <RotateCcw size={20} aria-hidden="true" />
        {page ? `Repeat ${name}` : "Repeat"}
      </button>
      <button type="button" className="pr-btn pr-step" aria-label="Next page" disabled={k < 0 || k >= pages.length - 1}
        onClick={() => step("next")}>
        Next
        <ChevronRight size={20} aria-hidden="true" />
      </button>
    </div>
  );
}
