// The app fills the page from edge to edge (DESIGN.md rules 2, 7 and 18): one sheet of glass over the wallpaper, the
// top bar, the places on the left, the open view in the middle, and on the right either the crew rail (Working now
// and Spend) or, in an episode, the slim crew chat. No frame and no fake window around it.
import { Button } from "@astryxdesign/core/Button";
import { LoaderCircle, WifiOff } from "lucide-react";
import { useEffect } from "react";
import { ONBOARDING } from "./api/types";
import { ErrorLine, Loading } from "./components/bits";
import { useFirstStart } from "./components/ChatPane";
import { CrewRail } from "./components/Crew";
import { Palette } from "./components/Palette";
import { PrompterPopover } from "./components/PrompterPopover";
import { Sidebar } from "./components/Sidebar";
import { TitleBar, useDocumentTitle } from "./components/TitleBar";
import {
  boot,
  focusComposer,
  newEpisode,
  onHashChange,
  openEpisodeAt,
  setMenu,
  setPalette,
  setPrompter,
  toggleCrew,
  toggleSide,
} from "./store/actions";
import { getUi, useUi } from "./store/store";
import { Dock, EpisodeView, NewEpisodeView, OnboardingView } from "./views/EpisodeView";
import { SlateFigure } from "./slate/Slate";
import { Home } from "./views/Home";
import { ChannelView } from "./views/ChannelView";
import { JobLogView, ProfileView, RendersView, TeamView } from "./views/ReadOnlyViews";

/** Ctrl/Cmd+Enter accepts the open card in view (rule 15): the lowest open card visible in the chat. */
function acceptCardInView(): boolean {
  const scroller = document.querySelector<HTMLElement>("[data-testid='chat-scroll']");
  if (!scroller) return false;
  const cards = Array.from(scroller.querySelectorAll<HTMLElement>("[data-open-card]"));
  if (!cards.length) return false;
  const box = scroller.getBoundingClientRect();
  const visible = cards.filter((c) => {
    const r = c.getBoundingClientRect();
    return r.bottom > box.top && r.top < box.bottom;
  });
  const card = visible[visible.length - 1] ?? cards[cards.length - 1];
  const button = card?.querySelector<HTMLButtonElement>("[data-accept]");
  if (!button || button.disabled) return false;
  button.click();
  return true;
}

function inTextField(el: EventTarget | null): boolean {
  return (
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLInputElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  );
}

/** The shortcuts of rule 15. Cmd on Apple devices, Ctrl elsewhere; both work everywhere. */
function onShortcut(e: KeyboardEvent): void {
  if (e.isComposing) return;
  const mod = e.metaKey || e.ctrlKey;
  const ui = getUi();
  if (e.key === "Enter" && mod) {
    if (acceptCardInView()) e.preventDefault();
    return;
  }
  if (e.key === "Escape") {
    if (ui.paletteOpen) setPalette(false);
    else if (ui.prompterOpen) setPrompter(false);
    else if (ui.menuOpen) setMenu(false);
    return;
  }
  if (mod && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
    setPalette(!ui.paletteOpen);
    e.preventDefault();
    return;
  }
  if (ui.paletteOpen) return; // the palette owns the keys while it is open
  if (mod && e.code === "KeyB") {
    if (e.altKey) toggleCrew();
    else toggleSide();
    e.preventDefault();
    return;
  }
  if (mod && !e.altKey && e.key.toLowerCase() === "n") {
    newEpisode();
    e.preventDefault();
    return;
  }
  if (mod && !e.altKey && /^[1-9]$/.test(e.key)) {
    if (openEpisodeAt(Number(e.key) - 1)) e.preventDefault();
    return;
  }
  if (e.key === "/" && !mod && !e.altKey && !inTextField(e.target)) {
    focusComposer();
    e.preventDefault();
  }
}

function Notices() {
  const live = useUi((s) => s.live);
  if (live !== "retrying") return null;
  return (
    <div className="notice" role="status">
      <span className="dot warn" aria-hidden="true" />
      <WifiOff size={14} aria-hidden="true" />
      <span>Lost the connection to the container. Retrying…</span>
    </div>
  );
}

/**
 * No Crewcut answers at this address: first "Crewcut is starting…" while the app keeps asking, then the honest
 * "Can't reach the Crewcut engine" with what to check and a retry. Never made-up content.
 */
function EngineState({ status }: { status: "starting" | "unreachable" }) {
  const starting = status === "starting";
  return (
    <main className="main engine-main" aria-label="Crewcut">
      <div className="engine-state" role={starting ? "status" : "alert"} data-testid="engine-state">
        <SlateFigure state={starting ? "working" : "waiting"} size={104} />
        <h1>{starting ? "Crewcut is starting…" : "Can't reach the Crewcut engine"}</h1>
        {starting ? (
          <p>
            <LoaderCircle size={14} className="spin" aria-hidden="true" />
            Waiting for the engine at this address. The first start takes a few minutes.
          </p>
        ) : (
          <>
            <p>Check that Docker is running and Crewcut is started (the Crewcut app, or ./start.sh), then try again.</p>
            <Button label="Try again" variant="primary" clickAction={() => void boot()} />
          </>
        )}
      </div>
    </main>
  );
}

/** The middle and the right of the window for the open view. */
function Body() {
  const view = useUi((s) => s.view);
  const status = useUi((s) => s.boot);
  const error = useUi((s) => s.bootError);
  if (status === "starting" || status === "unreachable") return <EngineState status={status} />;
  if (status === "loading" || status === "error") {
    return (
      <>
        <main className="main chat-main" aria-label="Crewcut">
          {status === "loading" ? (
            <Loading label="Loading Crewcut" />
          ) : (
            <div className="center-state danger">
              <ErrorLine text={`Couldn't load Crewcut. ${error ?? ""}`} onRetry={() => void boot()} />
            </div>
          )}
          <Dock />
        </main>
        <CrewRail />
      </>
    );
  }
  if (view.kind === "episode" && view.id !== ONBOARDING) return <EpisodeView key={view.id} id={view.id} />;
  let middle;
  switch (view.kind) {
    case "channel":
      middle = <ChannelView />;
      break;
    case "episode":
      middle = <OnboardingView />;
      break;
    case "episodes":
      middle = <Home />;
      break;
    case "profile":
      middle = <ProfileView />;
      break;
    case "crew":
      middle = <TeamView />;
      break;
    case "renders":
      middle = <RendersView />;
      break;
    case "job":
      middle = <JobLogView key={view.id} id={view.id} />;
      break;
    default:
      middle = <NewEpisodeView />;
  }
  return (
    <>
      {middle}
      <CrewRail />
    </>
  );
}

export function App() {
  const menuOpen = useUi((s) => s.menuOpen);
  const sideHidden = useUi((s) => s.sideHidden);
  const crewHidden = useUi((s) => s.crewHidden);
  const episodeId = useUi((s) => (s.view.kind === "episode" && s.view.id !== ONBOARDING ? s.view.id : null));
  const onboarding = useUi((s) => s.view.kind === "episode" && s.view.id === ONBOARDING);
  const firstStart = useFirstStart(onboarding ? ONBOARDING : "");
  const engineDown = useUi((s) => s.boot === "starting" || s.boot === "unreachable");
  useDocumentTitle();

  useEffect(() => {
    void boot();
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("popstate", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      window.removeEventListener("popstate", onHashChange);
    };
  }, []);

  // A file dropped outside the chat must not replace the app with the file.
  useEffect(() => {
    const stop = (e: DragEvent) => {
      if (e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files")) e.preventDefault();
    };
    window.addEventListener("dragover", stop);
    window.addEventListener("drop", stop);
    return () => {
      window.removeEventListener("dragover", stop);
      window.removeEventListener("drop", stop);
    };
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  const cls = [
    "app",
    episodeId ? "in-episode" : "in-home",
    sideHidden || engineDown ? "side-hidden" : null,
    crewHidden ? "crew-hidden" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      <div className="window">
        <TitleBar quiet={firstStart || engineDown} />
        {episodeId ? <PrompterPopover episode={episodeId} /> : null}
        <div className="win-body">
          {engineDown ? null : <Sidebar compact={Boolean(episodeId)} />}
          {menuOpen ? <div className="scrim" aria-hidden="true" onClick={() => setMenu(false)} /> : null}
          <Body />
        </div>
        <Notices />
      </div>
      <Palette />
    </div>
  );
}
