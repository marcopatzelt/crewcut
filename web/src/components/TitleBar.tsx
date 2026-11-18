// The top bar (DESIGN.md rule 2): where you are, the search that opens the command palette, and the actions of the
// open view. 46 px on the glass; the views scroll below it. In an app window it is also the window's title bar: its
// empty parts move the window (window.css), and the document title names the open view.
import { Kbd } from "@astryxdesign/core/Kbd";
import { Button } from "@astryxdesign/core/Button";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Menu, PanelRight, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { ONBOARDING } from "../api/types";
import { episodeNumber } from "../lib/format";
import { ariaKeys, keyText } from "../lib/platform";
import { api } from "../api/client";
import { messageOf, navigate, refreshState, setMenu, setPalette, toggleCrew } from "../store/actions";
import { EMPTY, useUi, type View } from "../store/store";
import { PrompterButton } from "./PrompterPopover";

/** What the title bar says after "Make a Short" started one. */
export const SHORT_STARTED = "Short started. The Scout looks for passages.";

const HERE: Record<string, string> = {
  channel: "Channel",
  episodes: "Episodes",
  new: "New episode",
  profile: "Style pack",
  crew: "Crew",
  renders: "GPU and renders",
  job: "Job log",
};

/** The open view's name: the crumb shows the episode's number, the window title its title. */
function viewName(view: View, title: string | undefined, short: boolean): string {
  if (view.kind !== "episode") return HERE[view.kind] ?? "";
  const id = view.id;
  if (id === ONBOARDING) return "Set up your style";
  return short ? episodeNumber(id) ?? title ?? id : title ?? episodeNumber(id) ?? id;
}

/** The document title: "Crewcut" and the open view, for the app window's title, the task bar and the tab. */
export function documentTitle(view: View, title?: string): string {
  const name = viewName(view, title, false);
  return name ? `Crewcut · ${name}` : "Crewcut";
}

function useEpisodeTitle(): string | undefined {
  return useUi((s) => (s.view.kind === "episode" ? s.state?.episodes.find((e) => e.id === (s.view as { id: string }).id)?.title : undefined));
}

/** Keeps document.title on "Crewcut · <view>". */
export function useDocumentTitle(): void {
  const view = useUi((s) => s.view);
  const title = useEpisodeTitle();
  const text = documentTitle(view, title);
  useEffect(() => {
    document.title = text;
  }, [text]);
}

function Crumbs() {
  const view = useUi((s) => s.view);
  const title = useEpisodeTitle();
  const current = viewName(view, title, true);
  const top = view.kind === "channel";
  return (
    <nav className="crumbs" aria-label="Where you are">
      {top ? null : (
        <>
          <a
            href="#/channel"
            onClick={(e) => {
              e.preventDefault();
              navigate({ kind: "channel" });
            }}
          >
            Channel
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
