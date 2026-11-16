// The teleprompter link in the episode header: a QR code and the address for a phone in the same network.
import { Copy, ExternalLink } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { PrompterLink } from "../api/types";
import { messageOf } from "../store/actions";
import { ErrorLine, Loading } from "./bits";

function safeSvg(svg: string): string | null {
  const s = svg.trim();
  if (!s.startsWith("<svg") || /<script|on\w+\s*=|javascript:/i.test(s)) return null;
  return s;
}

export function PrompterButton({ episode }: { episode: string }) {
  const [open, setOpen] = useState(false);
  const [link, setLink] = useState<PrompterLink | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  async function load() {
    setError(null);
    try {
      setLink(await api.prompter(episode));
    } catch (e) {
      setError(`Couldn't get the teleprompter link. ${messageOf(e)}`);
    }
  }

  useEffect(() => {
    setLink(null);
    setOpen(false);
  }, [episode]);

  useEffect(() => {
    if (!open) return;
    if (!link) void load();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!box.current?.contains(t) && !button.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  const svg = link ? safeSvg(link.qr_svg) : null;
  const remote = link ? `${link.url}${link.url.includes("?") ? "&" : "?"}remote=1` : "";

  return (
    <>
      <button
        type="button"
        ref={button}
        className="text-button"
        aria-expanded={open}
        aria-controls="prompter-popover"
        onClick={() => setOpen((o) => !o)}
      >
        Teleprompter
      </button>
      {open ? (
        <div className="popover" id="prompter-popover" ref={box} role="dialog" aria-label="Teleprompter on your phone">
          <h2>Teleprompter on your phone</h2>
          <p className="meta">Scan the code with a phone in the same network. The script opens in big letters.</p>
          {error ? <ErrorLine text={error} onRetry={() => void load()} /> : null}
          {!link && !error ? <Loading label="Loading the teleprompter link" /> : null}
          {link ? (
            <>
              {svg ? <div className="qr" dangerouslySetInnerHTML={{ __html: svg }} /> : null}
              <div className="url-line">
                <code title={link.url}>{link.url}</code>
              </div>
              <div className="actions">
                <button type="button" className="pill" onClick={() => void copy()}>
                  <Copy size={16} aria-hidden="true" />
                  {copied ? "Copied" : "Copy link"}
                </button>
                <a className="pill" href={remote} target="_blank" rel="noreferrer">
                  <ExternalLink size={16} aria-hidden="true" />
                  Open the remote
                </a>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
