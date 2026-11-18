// The left side of the window (DESIGN.md rule 2): the places with their counts, the channel, and the crew dock with
// Slate's faces at the bottom. In the episode view it shrinks to an icon rail, so the media have room.
// Arrow up and down move between the places (rule 15).
import { Clapperboard, Cpu, MessageCircle, Palette, RectangleVertical, Users } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import type { Activity, Identity } from "../api/types";
import { countWord } from "../lib/format";
import { navigate } from "../store/actions";
import { EMPTY, useUi, type View } from "../store/store";
import { AppIcon, Avatar } from "../slate/Slate";
import { identityOf } from "./bits";

interface Place {
  id: string;
  label: string;
  icon: ReactNode;
  count?: number;
  to: View;
  on: (v: View) => boolean;
}

/** "Editor, Designer and Critic" */
export function names(list: string[]): string {
  if (list.length <= 1) return list[0] ?? "";
  return `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`;
}

/** The line under the crew dock: who works, and that the rest waits until asked. */
export function dockLine(team: Identity[], activity: readonly Activity[]): { who: string; rest: string } {
  const busy = [...new Set(activity.filter((a) => a.status === "running").map((a) => a.identity))];
  const who = names(busy.map((id) => identityOf(team, id).name));
  const restN = Math.max(0, team.length - busy.length);
  if (!busy.length) return { who: "", rest: "Nobody is working. The crew rests until you ask." };
  const rest = restN === 0 ? "" : restN === 1 ? "One rests until you ask." : `${countWord(restN)} rest until you ask.`;
  return { who, rest: `${busy.length === 1 ? "is" : "are"} working.${rest ? ` ${rest}` : ""}` };
}

function moveFocus(e: KeyboardEvent<HTMLElement>) {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const rows = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>("button.place"));
  if (!rows.length) return;
  const i = rows.indexOf(document.activeElement as HTMLButtonElement);
  const next = e.key === "ArrowDown" ? Math.min(rows.length - 1, i + 1) : Math.max(0, i < 0 ? 0 : i - 1);
  rows[next]?.focus();
  e.preventDefault();
}

function CrewDock() {
  const team = useUi((s) => s.state?.team ?? EMPTY);
  const activity = useUi((s) => s.state?.activity ?? EMPTY);
  if (!team.length) return null;
  const busy = new Set(activity.filter((a) => a.status === "running").map((a) => a.identity));
  const line = dockLine(team, activity);
  return (
    <div className="crewdock">
      <span className="dock-faces" aria-hidden="true">
        {team.map((t) => (
          <span key={t.id} className={busy.has(t.id) ? "dock-face busy" : "dock-face"}>
            <Avatar who={t} size="dock" />
          </span>
        ))}
      </span>
      <p>
        {line.who ? <b>{line.who}</b> : null} {line.rest}
      </p>
    </div>
  );
}

export function Sidebar({ compact }: { compact: boolean }) {
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const team = useUi((s) => s.state?.team ?? EMPTY);
  const view = useUi((s) => s.view);
  const menuOpen = useUi((s) => s.menuOpen);
  const channel = useUi((s) => s.channel);
  const boot = useUi((s) => s.boot);
  const ready = boot === "ready";
  const shorts = episodes.filter((e) => e.kind === "short").length;
  const filter = view.kind === "episodes" ? view.filter ?? "all" : null;

  const places: Place[] = [
    { id: "channel", label: "Channel", icon: <MessageCircle size={18} aria-hidden="true" />, to: { kind: "channel" }, on: (view) => view.kind === "channel" },
    {
      id: "episodes",
      label: "Episodes",
      icon: <Clapperboard size={18} aria-hidden="true" />,
      count: ready ? episodes.length - shorts : undefined,
      to: { kind: "episodes" },
      on: (v) => (v.kind === "episodes" && filter !== "shorts") || v.kind === "episode" || v.kind === "new",
    },
    {
      id: "shorts",
      label: "Shorts",
      icon: <RectangleVertical size={18} aria-hidden="true" />,
      count: ready ? shorts : undefined,
      to: { kind: "episodes", filter: "shorts" },
      on: () => filter === "shorts",
    },
    {
      id: "crew",
      label: "Crew",
      icon: <Users size={18} aria-hidden="true" />,
      count: ready && team.length ? team.length : undefined,
      to: { kind: "crew" },
      on: (v) => v.kind === "crew" || v.kind === "job",
    },
    { id: "style", label: "Style pack", icon: <Palette size={18} aria-hidden="true" />, to: { kind: "profile" }, on: (v) => v.kind === "profile" },
    { id: "renders", label: "GPU and renders", icon: <Cpu size={18} aria-hidden="true" />, to: { kind: "renders" }, on: (v) => v.kind === "renders" },
  ];

  const cls = ["side", compact ? "is-rail" : null, menuOpen ? "open" : null].filter(Boolean).join(" ");
  return (
    <nav className={cls} id="side" aria-label="Places">
      <div className="brand">
        <AppIcon size={30} />
        <span className="brand-name">Crewcut</span>
      </div>
      <div className="places" onKeyDown={moveFocus}>
        {places.map((p) => {
          const on = p.on(view);
          const count = typeof p.count === "number" ? p.count : null;
          return (
            <button
              key={p.id}
              type="button"
              className={compact ? "place tip tip-right" : "place"}
              aria-current={on ? "page" : undefined}
              aria-label={compact ? (count !== null ? `${p.label}, ${count}` : p.label) : undefined}
              data-tip={compact ? p.label : undefined}
              onClick={() => navigate(p.to)}
            >
              {p.icon}
              <span className="place-label">{p.label}</span>{" "}
              {count !== null ? <span className="place-count">{count}</span> : null}
            </button>
          );
        })}
      </div>
      {channel && !compact ? (
        <div className="channel">
          <h2 className="side-label">Channel</h2>
          <div className="channel-row">
            {channel.avatar ? <img src={channel.avatar} alt="" className="channel-pic" /> : null}
            <span className="one-line">{channel.name}</span>
          </div>
        </div>
      ) : null}
      {compact ? null : <CrewDock />}
    </nav>
  );
}
