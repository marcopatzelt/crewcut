import { useEffect, useState } from "react";
import { api } from "../api/client";
import { messageOf } from "../store/actions";

type Policy = { mode: string; blocked?: string; complete?: boolean };
const choices = [
  ["ready", "Finish, stop before upload"],
  ["private", "Finish and upload privately"],
  ["publish", "Finish and publish automatically"],
] as const;

export function FullAuto({ episode }: { episode: string }) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    const read = () => { void api.fullAuto(episode).then(p => { if (live) setPolicy(p); }).catch(() => undefined); };
    read(); const timer = setInterval(read, 5000);
    return () => { live = false; clearInterval(timer); };
  }, [episode]);
  async function change(mode: string) {
    setBusy(true); setError("");
    try { setPolicy(await api.setFullAuto(episode, mode)); }
    catch (e) { setError(messageOf(e)); }
    finally { setBusy(false); }
  }
  if (!policy) return null;
  return <details className="full-auto">
    <summary>Full auto · {policy.blocked ? "Needs attention" : policy.complete ? "Finished" : policy.mode === "off" ? "Off" : "On"}</summary>
    <p>After recording, the crew edits, checks the final cut, makes thumbnails and prepares the upload.</p>
    <p>The Critic handles production decisions. New paid work needs your budget. Choose where this episode stops.</p>
    <div className="actions">
      {choices.map(([mode, label]) => <button key={mode} type="button" className="pill" disabled={busy}
        aria-pressed={policy.mode === mode} onClick={() => void change(mode)}>{label}</button>)}
      {policy.mode !== "off" ? <button type="button" className="pill" disabled={busy} onClick={() => void change("off")}>Turn off</button> : null}
    </div>
    {policy.mode === "publish" ? <p>Public or scheduled publishing is allowed for this episode.</p> : null}
    {policy.blocked ? <p role="status">{policy.blocked}</p> : null}
    {error ? <p role="alert">{error}</p> : null}
  </details>;
}
