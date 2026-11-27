// Which Claude login new work uses: the Claude subscription or an Anthropic API key (billed per token). The key is
// pasted once into the one password field here (DESIGN.md: a value only the user can copy) and goes to the server,
// which keeps it in the engine volume; the page never gets it back, only "saved" or "none".
import { Button } from "@astryxdesign/core/Button";
import { useState } from "react";
import { api } from "../api/client";
import type { EngineLogin } from "../api/types";
import { messageOf, refreshState } from "../store/actions";

type Auth = NonNullable<EngineLogin["claude_auth"]>;

export function ClaudeAuth({ auth, onChange }: { auth: Auth; onChange: (next: Auth) => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(call: () => Promise<Auth>) {
    setBusy(true);
    setError(null);
    try {
      onChange(await call());
      refreshState();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const value = key.trim();
    if (!value) return;
    await act(() => api.saveClaudeApiKey(value, true));
    setKey("");
  }

  const sub = auth.subscription.connected;
  const present = auth.api_key.present;
  return (
    <div className="claude-auth" role="group" aria-label="Claude login">
      <div className="claude-auth-switch" role="group" aria-label="Claude login for new work">
        <button type="button" aria-pressed={auth.mode === "subscription"} disabled={busy || !sub}
          title={sub ? undefined : "Connect Claude first"}
          onClick={() => void act(() => api.setClaudeAuth("subscription"))}>Subscription</button>
        <button type="button" aria-pressed={auth.mode === "api_key"} disabled={busy || !present}
          title={present ? undefined : "Save an API key first"}
          onClick={() => void act(() => api.setClaudeAuth("api_key"))}>API key</button>
      </div>
      {present ? (
        <p className="connect-note">
          {auth.api_key.source === "environment" ? "API key from the environment (.env)." : "API key saved."}
          {auth.api_key.source === "stored" ? (
            <button type="button" className="link-button" disabled={busy}
              onClick={() => void act(() => api.forgetClaudeApiKey())}>Remove key</button>
          ) : null}
        </p>
      ) : (
        <div className="connect-row">
          <input
            type="password"
            className="connect-field"
            aria-label="Anthropic API key"
            placeholder="Anthropic API key"
            autoComplete="off"
            spellCheck={false}
            value={key}
            disabled={busy}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void save();
            }}
          />
          <Button label="Save key" variant="secondary" clickAction={() => void save()} />
        </div>
      )}
      <p className="meta">The API key is billed per token by Anthropic. New work uses the choice; running work keeps its login.</p>
      {error ? (
        <p className="connect-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
