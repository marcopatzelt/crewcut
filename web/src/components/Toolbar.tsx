// The toolbar of the center place (DESIGN.md rules 7 and 18): material, sticks to the top, the chat runs under it.
// The large title sits once at the top of the content; when it scrolls under the bar, the small title fades in here.
import { Menu, PanelRight, Search } from "lucide-react";
import { useCallback, useRef, useState, type ReactNode, type RefObject } from "react";
import { ariaKeys, keyText } from "../lib/platform";
import { setMenu, setPalette, toggleCrew } from "../store/actions";
import { useUi } from "../store/store";

const BAR = 52;

/** Scroll state for a view with a toolbar: is content under the bar, and has the large title gone under it. */
export function useScrollChrome() {
  const scroller = useRef<HTMLDivElement>(null);
  const large = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const [showTitle, setShowTitle] = useState(false);
  const update = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    setScrolled(el.scrollTop > 1);
    const lt = large.current;
    if (!lt) {
      setShowTitle(true);
      return;
    }
    setShowTitle(lt.getBoundingClientRect().bottom <= el.getBoundingClientRect().top + BAR + 1);
  }, []);
  return { scroller, large, scrolled, showTitle, update };
}

export function Toolbar({
  title,
  sub,
  showTitle,
  scrolled,
  children,
  actions,
}: {
  title: string;
  sub?: string;
  showTitle: boolean;
  scrolled: boolean;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  const menuOpen = useUi((s) => s.menuOpen);
  const crewHidden = useUi((s) => s.crewHidden);
  const crewLabel = crewHidden ? "Show the crew column" : "Hide the crew column";
  return (
    <header className={scrolled ? "toolbar scrolled" : "toolbar"}>
      <button
        type="button"
        className="icon-button menu-button"
        aria-label="Episodes"
        aria-expanded={menuOpen}
        aria-controls="episodes"
        onClick={() => setMenu(!menuOpen)}
      >
        <Menu size={16} aria-hidden="true" />
      </button>
      <div className={showTitle ? "tb-title shown" : "tb-title"} aria-hidden="true">
        <div className="tb-name one-line">{title}</div>
        {sub ? <div className="tb-sub one-line">{sub}</div> : null}
      </div>
      {children}
      <div className="tb-actions">
        {actions}
        <button
          type="button"
          className="icon-button tip tip-end tb-crew"
          aria-label="Crew column"
          aria-pressed={!crewHidden}
          aria-keyshortcuts={ariaKeys(["mod", "alt", "B"])}
          data-tip={`${crewLabel}  ${keyText(["mod", "alt", "B"])}`}
          onClick={toggleCrew}
        >
          <PanelRight size={16} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="icon-button tip tip-end"
          aria-label="Command palette"
          aria-keyshortcuts={ariaKeys(["mod", "K"])}
          data-tip={`Go to or do anything  ${keyText(["mod", "K"])}`}
          onClick={() => setPalette(true)}
        >
          <Search size={16} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}

/** The title block at the top of a view's content: 20 px, scrolls away under the toolbar. */
export function LargeTitle({
  innerRef,
  title,
  sub,
  lead,
}: {
  innerRef: RefObject<HTMLDivElement | null>;
  title: string;
  sub?: string;
  lead?: ReactNode;
}) {
  return (
    <div className="large-title" ref={innerRef}>
      {lead}
      <div className="large-text">
        <h1 className="one-line" title={title}>
          {title}
        </h1>
        {sub ? <p className="sub">{sub}</p> : null}
      </div>
    </div>
  );
}
