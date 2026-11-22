// The interview before the first script draft (crewcut/interview.py). While the episode waits for the creator's
// answers it says so above the media, with "Skip interview" and, after answers in several messages, "Done answering".
// The answers themselves go into the chat composer, typed or dictated.
import { useState } from "react";
import { api } from "../api/client";
import type { EpisodeInterview } from "../api/types";
import { messageOf } from "../store/actions";

export function InterviewBar({ episode, interview }: { episode: string; interview?: EpisodeInterview | null }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [closed, setClosed] = useState(false);
  const now = interview;
  if (!now || closed || (now.status !== "waiting" && now.status !== "asking")) return null;
  async function act(action: "skip" | "done") {
    setBusy(true);
    setError("");
    try {
      const next = await api.interview(episode, action);
      if (next && next.status !== "waiting" && next.status !== "asking") setClosed(true);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="interview-bar" aria-label="Interview">
      <p role="status">
        <b>{now.label}</b>
        {now.status === "waiting"
          ? now.answers
            ? ` · ${now.answers} ${now.answers === 1 ? "answer" : "answers"} so far. Say “done” or press Done answering.`
            : " · Answer the questions in the chat, typed or spoken."
          : null}
      </p>
      <div className="actions">
        {now.status === "waiting" && now.answers > 0 ? (
          <button type="button" className="pill" disabled={busy} onClick={() => void act("done")}>
            Done answering
          </button>
        ) : null}
        <button type="button" className="pill" disabled={busy} onClick={() => void act("skip")}>
          Skip interview
        </button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
