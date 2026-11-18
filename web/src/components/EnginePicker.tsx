import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EngineLogin } from "../api/types";
import { messageOf, refreshState } from "../store/actions";
import { ConnectEngine } from "./ConnectEngine";

export function EnginePicker() {
  const [login, setLogin] = useState<EngineLogin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    const load = () => api.engineLogin().then((value) => {
      if (live) setLogin(value);
    }).catch((reason) => { if (live) setError(messageOf(reason)); });
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => { live = false; clearInterval(timer); };
  }, []);

  async function choose(name: "claude" | "codex") {
    setBusy(true);
    setError(null);
    try {
      setLogin(await api.useEngine(name));
      refreshState();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="connect" aria-label="Chat engine">
      <h2>Who runs your chats</h2>
      <p className="meta">Use your own subscription. Switching keeps both sign-ins and your chat history.</p>
      {error ? <p role="alert" className="connect-error">{error}</p> : null}
      {!login ? <p>Checking connections…</p> : (["claude", "codex"] as const).map((name) => (
        <div key={name}>
          <p>{name === "claude" ? "Claude Code" : "Codex"}: {login[name].connected ? "connected" : "not connected"}</p>
          {login[name].connected ? (
            <button type="button" className="text-button" disabled={busy || login.chosen === name}
              onClick={() => void choose(name)}>
              {login.chosen === name ? `Using ${name === "claude" ? "Claude Code" : "Codex"}` : `Use ${name === "claude" ? "Claude Code" : "Codex"}`}
            </button>
          ) : <ConnectEngine only={name} />}
        </div>
      ))}
      <p className="meta">The choice applies to new work. Running work keeps its current engine.</p>
    </section>
  );
}
