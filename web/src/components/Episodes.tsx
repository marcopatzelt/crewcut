// The left place: "New episode", one row per episode, then Profile and Crew (DESIGN.md rule 2).
import { Palette, Plus, Users } from "lucide-react";
import type { Episode } from "../api/types";
import { navigate } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { StepBar } from "./bits";

export function Logo() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M11.5 2.6A6.5 6.5 0 1 0 14.2 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function stepOf(e: Episode) {
  return e.steps.find((s) => s.id === e.step) ?? e.steps.find((s) => s.status === "working" || s.status === "waiting");
}

function EpisodeRow({ episode, current }: { episode: Episode; current: boolean }) {
  const step = stepOf(episode);
  const needsYou = episode.open_cards > 0;
  return (
    <button
      type="button"
      className="ep"
      aria-current={current ? "page" : undefined}
      title={episode.title}
      onClick={() => navigate({ kind: "episode", id: episode.id })}
    >
      {needsYou ? <span className="ep-dot" aria-hidden="true" /> : null}
      <span className="ep-title one-line">{episode.title}</span>
      <span className="ep-step">
        {step ? `${step.n} ${step.label}` : episode.step}
        {needsYou ? <span className="sr-only">, needs your yes</span> : null}
      </span>
      <StepBar steps={episode.steps} />
    </button>
  );
}

export function Episodes() {
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const view = useUi((s) => s.view);
  const demo = useUi((s) => s.demo);
  const boot = useUi((s) => s.boot);
  const menuOpen = useUi((s) => s.menuOpen);

  return (
    <aside className={menuOpen ? "side open" : "side"} aria-label="Episodes" id="episodes">
      <div className="wordmark">
        <Logo />
        Crewcut
      </div>
      <button type="button" className="pill" onClick={() => navigate({ kind: "new" })}>
        <Plus size={16} aria-hidden="true" />
        New episode
      </button>
      <div className="group-label" id="episodes-label">
        Episodes
      </div>
      <nav className="ep-list" aria-labelledby="episodes-label">
        {episodes.map((e) => (
          <EpisodeRow key={e.id} episode={e} current={view.kind === "episode" && view.id === e.id} />
        ))}
        {boot === "ready" && episodes.length === 0 ? <p className="side-empty">No episodes yet.</p> : null}
      </nav>
      <button
        type="button"
        className="nav"
        aria-current={view.kind === "profile" ? "page" : undefined}
        onClick={() => navigate({ kind: "profile" })}
      >
        <Palette size={16} aria-hidden="true" />
        Profile
      </button>
      <button
        type="button"
        className="nav"
        aria-current={view.kind === "crew" ? "page" : undefined}
        onClick={() => navigate({ kind: "crew" })}
      >
        <Users size={16} aria-hidden="true" />
        Crew
      </button>
      {demo ? (
        <p className="side-note">
          {demo === "auto" ? "Demo data. Crewcut is not running at this address." : "Demo data. Nothing here is real."}
        </p>
      ) : null}
    </aside>
  );
}
