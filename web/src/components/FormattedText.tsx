import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "../styles/formatted-text.css";

export function FormattedText({ text }: { text: string }) {
  return <div className="formatted-text">
    <Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
      a: ({ href, children }) => href && /^https?:\/\//i.test(href)
        ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
        : <span>{children}</span>,
      img: ({ alt }) => <span>{alt || "Image"}</span>,
      table: ({ children }) => <div className="text-table" role="region" aria-label="Table" tabIndex={0}><table>{children}</table></div>,
      input: ({ checked }) => <span className="text-task" aria-label={checked ? "Done" : "Not done"}>{checked ? "[x]" : "[ ]"}</span>,
    }}>{text}</Markdown>
  </div>;
}
