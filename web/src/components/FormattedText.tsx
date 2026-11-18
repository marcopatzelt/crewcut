import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DocumentLink, documentTarget } from "./DocumentLink";
import { documentReferences } from "../lib/document-references";
import "../styles/formatted-text.css";

export function FormattedText({ text, episode }: { text: string; episode?: string }) {
  return <div className="formatted-text">
    <Markdown remarkPlugins={[remarkGfm, documentReferences]} skipHtml components={{
      a: ({ href, children }) => {
        const target = href ? documentTarget(href, episode) : null;
        if (target) return <DocumentLink {...target}>{children}</DocumentLink>;
        return href && /^https?:\/\//i.test(href)
          ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          : <span>{children}</span>;
      },
      code: ({ children, className, node }) => {
        const value = String(children);
        const target = !className && !value.includes("\n") && node?.position?.start.line === node?.position?.end.line
          ? documentTarget(value, episode) : null;
        return <code className={className}>{target ? <DocumentLink {...target}>{children}</DocumentLink> : children}</code>;
      },
      img: ({ alt }) => <span>{alt || "Image"}</span>,
      table: ({ children }) => <div className="text-table" role="region" aria-label="Table" tabIndex={0}><table>{children}</table></div>,
      input: ({ checked }) => <span className="text-task" aria-label={checked ? "Done" : "Not done"}>{checked ? "[x]" : "[ ]"}</span>,
    }}>{text}</Markdown>
  </div>;
}
