// The window's title bar (DESIGN.md rule 2): three decorative dots, where you are, the search that opens the command
// palette, and the actions of the open view. 46 px, part of the glass window; the views scroll below it.
import { Kbd } from "@astryxdesign/core/Kbd";
import { Button } from "@astryxdesign/core/Button";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Menu, PanelRight, Plus, Search } from "lucide-react";
import { useState } from "react";
import { ONBOARDING } from "../api/types";
import { episodeNumber } from "../lib/format";
import { ariaKeys, keyText } from "../lib/platform";
import { api } from "../api/client";
import { messageOf, navigate, refreshState, setMenu, setPalette, toggleCrew } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { PrompterButton } from "./PrompterPopover";

/** What the title bar says after "Make a Short" started one. */
export const SHORT_STARTED = "Short started. The Scout looks for passages.";

function Crumbs() {
  const view = useUi((s) => s.view);
  const title = useUi((s) => (s.view.kind === "episode" ? s.state?.episodes.find((e) => e.id === (s.view as { id: string }).id)?.title : undefined));
  const here: Record<string, string> = {
    episodes: "Episodes",
    new: "New episode",
    profile: "Style pack",
    crew: "Crew",
    renders: "GPU and renders",
    job: "Job log",
  };
  let current: string;
  if (view.kind === "episode") current = view.id === ONBOARDING ? "Set up your style" : episodeNumber(view.id) ?? title ?? view.id;
  else current = here[view.kind] ?? "";
  const top = view.kind === "episodes";
  return (
    <nav className="crumbs" aria-label="Where you are">
      {top ? null : (
        <>
          <a
            href="#/episodes"
            onClick={(e) => {
              e.preventDefault();
              navigate({ kind: "episodes" });
            }}
          >
            Episodes
          </a>
          <span aria-hidden="true">/</span>
        </>
      )}
      <b aria-current="page" className="one-line" title={view.kind === "episode" ? title : undefined}>
        {current}
      </b>
    </nav>
  );
}

function AtWork() {
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  const n = activity.filter((a) => a.status === "running").length;
  if (!n) return null;
  return (
    <span className="tb-chip" role="status">
      <StatusDot variant="accent" label="Working" />
      {n} at work
    </span>
  );
}

/** "Make a Short": a Short in clip mode from this episode; the Scout's job appears in Working now. */
function MakeShort({ episode }: { episode: string }) {
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState<string | null>(null);
  return (
    <>
      {error ? (
        <span className="tb-error" role="alert">
          {error}
        </span>
      ) : null}
      {started ? (
        <button type="button" className="tb-done" role="status" onClick={() => navigate({ kind: "episode", id: started })}>
          {SHORT_STARTED}
        </button>
      ) : null}
      <Button
        label="Make a Short"
        variant="secondary"
        size="sm"
        icon={<Plus size={16} aria-hidden="true" />}
        tooltip="Starts a Short from this episode; the Scout picks the passages"
        clickAction={async () => {
          setError(null);
          try {
            const r = await api.makeShort(episode);
            setStarted(r.episode);
            refreshState();
          } catch (e) {
            setError(`Couldn't start it. ${messageOf(e)}`);
          }
        }}
      />
    </>
  );
}

export function TitleBar({ quiet }: { quiet: boolean }) {
  const view = useUi((s) => s.view);
  const menuOpen = useUi((s) => s.menuOpen);
  const crewHidden = useUi((s) => s.crewHidden);
  const isShort = useUi((s) =>
    s.view.kind === "episode" ? s.state?.episodes.find((e) => e.id === (s.view as { id: string }).id)?.kind === "short" : false,
  );
  const episode = view.kind === "episode" && view.id !== ONBOARDING ? view.id : null;
  const panelLabel = episode ? "Crew chat" : "Working now";

  return (
    <header className="titlebar">
      <span className="lights" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      {quiet ? null : (
        <>
          <button
            type="button"
            className="icon-button menu-button"
            aria-label="Menu"
            aria-expanded={menuOpen}
            aria-controls="side"
            onClick={() => setMenu(!menuOpen)}
          >
            <Menu size={16} aria-hidden="true" />
          </button>
          <Crumbs />
          <div className="tb-center">
            <button
              type="button"
              className="search"
              aria-keyshortcuts={ariaKeys(["mod", "K"])}
              onClick={() => setPalette(true)}
            >
              <Search size={16} aria-hidden="true" />
              <span className="one-line">Search episodes and actions</span>
              <Kbd keys="mod+k" className="search-keys" />
            </button>
          </div>
          <div className="tb-right">
            {episode ? null : <AtWork />}
            {episode && !isShort ? <MakeShort episode={episode} /> : null}
            {episode ? <PrompterButton /> : null}
            <button
              type="button"
              className="icon-button tip tip-end tb-panel"
              aria-label={panelLabel}
              aria-pressed={!crewHidden}
              aria-keyshortcuts={ariaKeys(["mod", "alt", "B"])}
              data-tip={`${crewHidden ? "Show" : "Hide"} ${panelLabel.toLowerCase()}  ${keyText(["mod", "alt", "B"])}`}
              onClick={toggleCrew}
            >
              <PanelRight size={16} aria-hidden="true" />
            </button>
          </div>
        </>
      )}
    </header>
  );
}
