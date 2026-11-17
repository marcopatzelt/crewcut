// "Connect Claude" (and Codex, beta) without a terminal. The server runs the CLI's own sign-in (engines/connect.py):
// Claude's page opens in a new tab, the user signs in there and pastes the code it shows into the one field here.
// In the desktop app the app does the same itself and keeps the token in the system keychain.
import { Button } from "@astryxdesign/core/Button";
import { LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ClaudeAccount, EngineLogin } from "../api/types";
import { desktop } from "../lib/desktop";
import { messageOf, refreshState } from "../store/actions";

type Phase = "idle" | "opening" | "code" | "sending" | "done";

function who(account: ClaudeAccount | undefined): string {
  if (account?.email) return ` as ${account.email}`;
  if (account?.orgName) return ` (${account.orgName})`;
  return "";
}

function ConnectCodex() {
  const [login, setLogin] = useState<EngineLogin["codex"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const waiting = login?.status === "waiting" || login?.status === "starting" || login?.status === "installing";

  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(() => {
      api
        .engineLogin()
        .then((l) => {
          setLogin((prev) => ({
            ...prev,
            ...l.codex,
            url: l.codex.url ?? prev?.url,
            code: l.codex.code ?? prev?.code,
            status: l.codex.connected ? "connected" : (l.codex.status ?? prev?.status),
          }));
          if (l.codex.connected) refreshState();
        })
        .catch(() => undefined);
    }, 3000);
    return () => clearInterval(t);
  }, [waiting]);

  async function start() {
    setError(null);
    const bridge = desktop();
    try {
      if (bridge) {
        const r = await bridge.connect("codex");
        setLogin({ installed: true, connected: r.connected, status: r.connected ? "connected" : "failed", text: r.text });
        if (r.connected) refreshState();
        return;
      }
      setLogin({ installed: false, connected: false, status: "starting" });
      setLogin(await api.codexConnect());
    } catch (e) {
      setLogin(null);
      setError(`Couldn't start the Codex sign-in. ${messageOf(e)}`);
    }
  }

  if (login?.status === "connected" || login?.connected) return <p className="connect-done">Codex is connected.</p>;
  if (login?.status === "waiting" && login.url) {
    return (
      <p className="connect-note">
        Open{" "}
        <a href={login.url} target="_blank" rel="noreferrer">
          {login.url.replace(/^https:\/\//, "")}
        </a>{" "}
        and enter the code <code className="connect-code">{login.code ?? "shown there"}</code>. Device sign-in has to be on in
        your ChatGPT security settings.
      </p>
    );
  }
  return (
    <>
      {error ? (
        <p className="connect-error" role="alert">
          {error}
        </p>
      ) : null}
      {login?.status === "failed" ? (
        <p className="connect-error" role="alert">
          Codex is not connected. {login.text ?? ""}
        </p>
      ) : null}
      {waiting ? (
        <p className="connect-note">
          <LoaderCircle size={14} className="spin" aria-hidden="true" />
          {login?.status === "installing" ? "Installing Codex first…" : "Starting the Codex sign-in…"}
        </p>
      ) : (
        <button type="button" className="link-button" onClick={() => void start()}>
          Connect Codex (beta) instead
        </button>
      )}
    </>
  );
}

/** The card: one button, then one field for the code Claude's page shows. */
export function ConnectEngine() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [url, setUrl] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [account, setAccount] = useState<ClaudeAccount | undefined>(undefined);

  async function connect() {
    setError(null);
    const bridge = desktop();
    if (bridge) {
      setPhase("opening");
      try {
        const r = await bridge.connect("claude");
        if (r.connected) {
          setAccount(r.account);
          setPhase("done");
          refreshState();
        } else {
          setError(r.text ?? "Claude is not connected.");
          setPhase("idle");
        }
      } catch (e) {
        setError(messageOf(e));
        setPhase("idle");
      }
      return;
    }
    // A tab opened in the click itself is not blocked; it gets Claude's address once the server has it.
    const tab = window.open("about:blank", "_blank");
    setPhase("opening");
    try {
      const r = await api.claudeConnect();
      setUrl(r.url);
      if (tab) {
        tab.opener = null;
        tab.location.href = r.url;
      }
      setPhase("code");
    } catch (e) {
      tab?.close();
      setError(`Couldn't start the sign-in. ${messageOf(e)}`);
      setPhase("idle");
    }
  }

  async function send() {
    if (!code.trim()) return;
    setError(null);
    setPhase("sending");
    try {
      const r = await api.claudeCode(code.trim());
      setAccount(r.account);
      setCode("");
      setPhase("done");
      refreshState();
    } catch (e) {
      setError(messageOf(e));
      setPhase("code");
    }
  }

  if (phase === "done") {
    return (
      <div className="connect" role="status">
        <p className="connect-done">Claude is connected{who(account)}. Paste your links below.</p>
      </div>
    );
  }
  return (
    <div className="connect" aria-label="Connect Claude" role="group">
      {phase === "code" || phase === "sending" ? (
        <>
          <p className="connect-note">
            Sign in on Claude's page. It shows a code: paste it here.{" "}
            {url ? (
              <a href={url} target="_blank" rel="noreferrer">
                Open Claude's sign-in again
              </a>
            ) : null}
          </p>
          <div className="connect-row">
            <input
              type="text"
              className="connect-field"
              aria-label="Code from Claude's page"
              placeholder="Code from Claude's page"
              autoComplete="off"
              spellCheck={false}
              value={code}
              disabled={phase === "sending"}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void send();
              }}
            />
            <Button label="Connect" variant="primary" clickAction={() => void send()} />
          </div>
        </>
      ) : phase === "opening" ? (
        <p className="connect-note">
          <LoaderCircle size={14} className="spin" aria-hidden="true" />
          Opening Claude's sign-in…
        </p>
      ) : (
        <Button label="Connect Claude" variant="primary" clickAction={() => void connect()} />
      )}
      {error ? (
        <p className="connect-error" role="alert">
          {error}
        </p>
      ) : null}
      {phase === "idle" ? <ConnectCodex /> : null}
    </div>
  );
}
