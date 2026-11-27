import { Check, ChevronDown, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { EngineLogin } from "../api/types";
import { messageOf, refreshState } from "../store/actions";
import { ClaudeAuth } from "./ClaudeAuth";
import { ConnectEngine } from "./ConnectEngine";
import { useUi } from "../store/store";
import "../styles/engine-picker.css";

export function EnginePicker() {
  const chosen = useUi((state) => state.state?.app.engine);
  const connected = useUi((state) => state.state?.app.engine_ok);
  const [open, setOpen] = useState(false);
  const [connecting, setConnecting] = useState<"claude" | "codex" | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [login, setLogin] = useState<EngineLogin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    let live = true;
    const load = () => api.engineLogin().then((value) => {
      if (live) { setLogin(value); setError(null); }
    }).catch((reason) => { if (live) setError(messageOf(reason)); });
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => { live = false; clearInterval(timer); };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  async function choose(name: "claude" | "codex") {
    setBusy(true);
    setError(null);
    try {
      setLogin(await api.useEngine(name));
      refreshState();
      setConnecting(null);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  const current = chosen ?? login?.chosen;
  const label = current === "claude" ? "Claude Code" : current === "codex" ? "Codex" : "Choose AI";
  return (
    <div className="engine-picker" ref={root}>
      <button type="button" className="engine-trigger" ref={trigger} aria-expanded={open}
        aria-label={`Chat AI: ${label}. Change AI`} onClick={() => setOpen(!open)}>
        <span>{label}</span>{connected === false ? <span className="engine-offline">Connect</span> : null}
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open ? <section className="engine-popover" aria-label="Choose chat AI">
      <div className="engine-heading"><strong>Chat with</strong>
        <button type="button" className="icon-button" aria-label="Close AI chooser" onClick={() => { setOpen(false); trigger.current?.focus(); }}><X size={16} /></button>
      </div>
      {error ? <p role="alert" className="connect-error">{error}</p> : null}
      {!login ? <p className="meta">Checking connections…</p> : (["claude", "codex"] as const).map((name) => {
        const active = login.chosen === name && login[name].connected;
        const title = name === "claude" ? "Claude Code" : "Codex";
        return <button key={name} type="button" className="engine-option" aria-pressed={active}
          disabled={busy || active} aria-label={`${active ? "Using" : login[name].connected ? "Use" : "Connect"} ${title}`}
          onClick={() => login[name].connected ? void choose(name) : setConnecting(name)}>
          <span><strong>{title}</strong><small>{active ? "Selected" : login[name].connected ? "Ready to use" : "Sign in once"}</small></span>
          {active ? <Check size={18} aria-hidden="true" /> : <span>{login[name].connected ? "Use" : "Connect"}</span>}
        </button>;
      })}
      {connecting && !login?.[connecting].connected ? <ConnectEngine only={connecting} /> : null}
      {login?.claude_auth && login.chosen === "claude" ? (
        <ClaudeAuth auth={login.claude_auth}
          onChange={(auth) => setLogin((prev) => prev ? { ...prev, claude_auth: auth,
            claude: { ...prev.claude, connected: auth.mode === "api_key" ? auth.api_key.present : auth.subscription.connected } } : prev)} />
      ) : null}
      <p className="meta">For new work in all chats. Running work stays unchanged.</p>
      </section> : null}
    </div>
  );
}
