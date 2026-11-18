// A small store: one state object, setUi() to change it, useUi() to read a slice in a component.
import { useSyncExternalStore } from "react";
import type { Card, EpisodeDetail, Message, State } from "../api/types";

export type View =
  | { kind: "channel" }
  | { kind: "episode"; id: string } // a real episode or the onboarding chat
  | { kind: "new" } // no episode selected: the composer starts one
  | { kind: "episodes"; filter?: Filter } // the home: all episodes and Shorts as media cards
  | { kind: "renders" } // rented GPUs and render jobs
  | { kind: "profile" }
  | { kind: "crew" }
  | { kind: "job"; id: number };

/** The filter pills of the home (DESIGN.md rule 2). */
export type Filter = "all" | "needs" | "work" | "long" | "shorts" | "done";

export const FILTER_IDS: readonly Filter[] = ["all", "needs", "work", "long", "shorts", "done"];

export interface Thread {
  status: "loading" | "ready" | "error";
  error: string | null;
  messages: Message[];
}

export interface UploadLine {
  key: string;
  episode: string;
  name: string;
  size: number;
  status: "uploading" | "done" | "failed";
  error?: string;
}

export interface UiState {
  /** "starting": no Crewcut answers yet, the app asks again every 2 s; "unreachable": it gave up and offers a retry. */
  boot: "loading" | "starting" | "unreachable" | "ready" | "error";
  bootError: string | null;
  state: State | null;
  view: View;
  lastEpisode: null;
  drafts: Record<string, string>;
  sending: Record<string, boolean>;
  sendErrors: Record<string, string | null>;
  /** The channel name and picture from the style pack, when it has them (the sidebar's "Channel"). */
  channel: { name: string; avatar: string | null } | null;
  threads: Record<string, Thread>;
  cards: Record<number, Card>;
  details: Record<string, EpisodeDetail>;
  /** When each job's `seconds` arrived (ms), so running jobs can count up between events. */
  seen: Record<number, number>;
  live: "idle" | "open" | "retrying";
  uploads: UploadLine[];
  /** The Episodes list as a menu (below 760 px). */
  menuOpen: boolean;
  /** The command palette (Cmd+K). */
  paletteOpen: boolean;
  /** The teleprompter dialog of the open episode. */
  prompterOpen: boolean;
  /** Cmd+B folds the Episodes panel, Cmd+Alt+B the Crew panel. */
  sideHidden: boolean;
  crewHidden: boolean;
}

export function initialUi(): UiState {
  return {
    boot: "loading",
    bootError: null,
    state: null,
    view: { kind: "channel" },
    lastEpisode: null,
    drafts: {},
    sending: {},
    sendErrors: {},
    channel: null,
    threads: {},
    cards: {},
    details: {},
    seen: {},
    live: "idle",
    uploads: [],
    menuOpen: false,
    paletteOpen: false,
    prompterOpen: false,
    sideHidden: false,
    crewHidden: false,
  };
}

let ui: UiState = initialUi();
const listeners = new Set<() => void>();

export function getUi(): UiState {
  return ui;
}

export function setUi(patch: Partial<UiState> | ((s: UiState) => Partial<UiState>)): void {
  const next = typeof patch === "function" ? patch(ui) : patch;
  ui = { ...ui, ...next };
  for (const l of listeners) l();
}

export function resetUi(): void {
  ui = initialUi();
  for (const l of listeners) l();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Read a slice of the store. The selector must return stored values, not new objects. */
export function useUi<T>(select: (s: UiState) => T): T {
  return useSyncExternalStore(
    subscribe,
    () => select(ui),
    () => select(ui),
  );
}

/** A shared empty list, so selectors return the same value on every call. Never mutate it. */
export const EMPTY = Object.freeze([]) as unknown as never[];
