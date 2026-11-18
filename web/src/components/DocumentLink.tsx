import { useState, type ReactNode } from "react";
import { api } from "../api/client";
import { DocumentPreview } from "./DocumentPreview";

export function documentTarget(href: string, episode?: string): { episode: string; file: string } | null {
  let path: string;
  try { path = decodeURIComponent(href); } catch { return null; }
  const absolute = path.match(/^\/api\/files\/([^/]+)\/(.+)$/);
  if (absolute) { episode = absolute[1]; path = absolute[2]!; }
  else path = path.replace(/^\.\//, "");
  if (!episode || episode === "_channel" || /[\\?#\u0000-\u001f]/.test(path) || path.startsWith("/")) return null;
  if (!/^[\w-]+$/.test(episode) || path.split("/").some(part => !part || part === "." || part === "..")) return null;
  if (!/\.(md|markdown|txt|json|csv|log|ya?ml|toml)$/i.test(path) || /^[a-z][a-z\d+.-]*:/i.test(path)) return null;
  return { episode, file: path };
}

export function DocumentLink({ episode, file, children, className }: {
  episode: string; file: string; children: ReactNode; className?: string;
}) {
  const [open, setOpen] = useState(false);
  return <>
    <a href={api.fileUrl(episode, file)} className={className} onClick={event => { event.preventDefault(); setOpen(true); }}>{children}</a>
    {open ? <DocumentPreview episode={episode} file={file} onClose={() => setOpen(false)} /> : null}
  </>;
}
