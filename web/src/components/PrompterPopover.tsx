// The teleprompter: an icon in the toolbar and a dialog with a QR code and the address for a phone in the same network.
// The dialog opens from the icon (rule 9) and floats with material (rule 18). It sits next to the toolbar, not inside
// it, so its own blur sees the chat behind it.
import { Copy, ExternalLink, ScrollText } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { PrompterLink } from "../api/types";
import { messageOf, setPrompter } from "../store/actions";
import { useUi } from "../store/store";
import { ErrorLine, Loading } from "./bits";
import { desktop } from "../lib/desktop";

export function DesktopScreens({ episode }: { episode: string }) {
  const bridge = desktop();
  const [screens, setScreens] = useState<Array<{ id: number; label: string; width: number; height: number }>>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    void bridge?.prompterDisplays?.().then(result => {
      if (current) { setScreens(result.displays); setSelected(result.selected); }
    }).catch(error => { if (current) setNote(messageOf(error)); });
    return () => { current = false; };
  }, []);
  if (!bridge?.prompterDisplays || !bridge.prompterSelectDisplay || !bridge.prompterOpen) return null;
  async function choose(id: number) {
    try { await bridge!.prompterSelectDisplay!(id); setSelected(id); setNote("Screen saved. The crew can open the approved script here."); }
    catch (error) { setNote(messageOf(error)); }
  }
  async function openScreen() {
    setBusy(true);
    try { setNote((await bridge!.prompterOpen!(episode)).message); }
    catch (error) { setNote(messageOf(error)); }
    finally { setBusy(false); }
  }
  return <section className="prompter-screens" aria-label="Teleprompter screen">
    <h3>Open on a screen</h3>
    <p className="meta">Choose once. The crew can open approved scripts here without controlling your mouse.</p>
    <div className="actions">
      {screens.map(item => <button type="button" className="pill" key={item.id} aria-pressed={selected === item.id}
        onClick={() => void choose(item.id)}>{item.label} · {item.width} × {item.height}</button>)}
    </div>
    <button type="button" className="pill" disabled={busy || !screens.some(item => item.id === selected)}
      onClick={() => void openScreen()}>{busy ? "Opening…" : "Open approved script full screen"}</button>
    {note ? <p className="meta" role="status">{note}</p> : null}
  </section>;
}

function safeSvg(svg: string): string | null {
  const s = svg.trim();
  if (!s.startsWith("<svg") || /<script|on\w+\s*=|javascript:/i.test(s)) return null;
  return s;
}

export function PrompterButton() {
  const open = useUi((s) => s.prompterOpen);
  return (
    <button
      type="button"
      id="prompter-button"
      className="icon-button tip tip-end"
      aria-label="Teleprompter"
      aria-expanded={open}
      aria-controls="prompter-popover"
      data-tip="Teleprompter on your phone"
      onClick={() => setPrompter(!open)}
    >
      <ScrollText size={16} aria-hidden="true" />
    </button>
  );
}

export function PrompterPopover({ episode }: { episode: string }) {
  const open = useUi((s) => s.prompterOpen);
  const [link, setLink] = useState<PrompterLink | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const box = useRef<HTMLDivElement>(null);

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
    setPrompter(false);
  }, [episode]);

  useEffect(() => {
    if (!open) return;
    void load();
    const button = () => document.getElementById("prompter-button");
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPrompter(false);
        button()?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!box.current?.contains(t) && !button()?.contains(t)) setPrompter(false);
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

  if (!open) return null;
  const svg = link ? safeSvg(link.qr_svg) : null;
  const remote = link ? `${link.url}${link.url.includes("?") ? "&" : "?"}remote=1` : "";

  return (
    <div className="popover" id="prompter-popover" ref={box} role="dialog" aria-label="Teleprompter on your phone">
      <DesktopScreens episode={episode} />
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
  );
}
