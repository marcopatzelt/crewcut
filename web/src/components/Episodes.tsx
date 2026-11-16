// The left place: the brand and "New episode", one row per episode, then Profile and Crew (DESIGN.md rule 2).
// A floating panel with material (rule 18). Arrow up and down move between episodes, Enter opens one (rule 15).
import { Palette, Plus, Users } from "lucide-react";
import type { KeyboardEvent } from "react";
import type { Episode } from "../api/types";
import { ariaKeys, keyText } from "../lib/platform";
import { navigate, newEpisode } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { StepBar } from "./bits";

export function Logo({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
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

/** Arrow up and down move the focus between the episode rows. */
function moveFocus(e: KeyboardEvent<HTMLElement>) {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const rows = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>("button.ep"));
  if (!rows.length) return;
  const i = rows.indexOf(document.activeElement as HTMLButtonElement);
  const next = e.key === "ArrowDown" ? Math.min(rows.length - 1, i + 1) : Math.max(0, i < 0 ? 0 : i - 1);
  rows[next]?.focus();
  e.preventDefault();
}

export function Episodes() {
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const view = useUi((s) => s.view);
  const demo = useUi((s) => s.demo);
  const boot = useUi((s) => s.boot);
  const menuOpen = useUi((s) => s.menuOpen);

  return (
    <aside className={menuOpen ? "side open" : "side"} aria-label="Episodes" id="episodes">
      <div className="side-head">
        <div className="wordmark">
          <Logo />
          Crewcut
        </div>
        <button
          type="button"
          className="icon-button tip tip-end"
          aria-label="New episode"
          aria-keyshortcuts={ariaKeys(["mod", "N"])}
          data-tip={`New episode  ${keyText(["mod", "N"])}`}
          onClick={newEpisode}
        >
          <Plus size={16} aria-hidden="true" />
        </button>
      </div>
      <div className="group-label" id="episodes-label">
        Episodes
      </div>
      <nav className="ep-list" aria-labelledby="episodes-label" onKeyDown={moveFocus}>
        {episodes.map((e) => (
          <EpisodeRow key={e.id} episode={e} current={view.kind === "episode" && view.id === e.id} />
        ))}
        {boot === "ready" && episodes.length === 0 ? <p className="side-empty">No episodes yet.</p> : null}
      </nav>
      <div className="side-foot">
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
      </div>
    </aside>
  );
}
