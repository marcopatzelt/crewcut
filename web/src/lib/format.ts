// Plain, exact words for times, sizes and money (DESIGN.md rule 10).

const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

/** "Three" for 3, "12" for 12. */
export function countWord(n: number): string {
  return WORDS[n] ?? String(n);
}

export function usd(n: number | null | undefined): string {
  const v = typeof n === "number" && Number.isFinite(n) ? n : 0;
  return `$${v.toFixed(2)}`;
}

/** "$20" for whole numbers, "$12.50" otherwise. */
export function usdShort(n: number): string {
  return Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`;
}

/** Elapsed time as a clock: "0:40", "4:12", "1:02:03". */
export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const ss = String(sec).padStart(2, "0");
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${ss}`;
  return `${m}:${ss}`;
}

/** A rough duration in words: "about 12 min", "about 3 h 10 min". */
export function about(seconds: number | null | undefined): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "Not known yet";
  if (seconds < 60) return `About ${Math.max(1, Math.round(seconds))} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `About ${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = Math.round((minutes % 60) / 5) * 5;
  if (m === 0 || m === 60) return `About ${m === 60 ? h + 1 : h} h`;
  return `About ${h} h ${m} min`;
}

/** "just now", "6 min ago", "2 h ago", "3 days ago", "12 Nov". */
export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 45) return "just now";
  const min = Math.round(s / 60);
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  if (d === 1) return "yesterday";
  if (d < 7) return `${d} days ago`;
  return day(iso);
}

/** "16 Nov 2026" (with the year only when it is not this year). */
export function day(iso: string, now = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const base = `${d.getDate()} ${months[d.getMonth()]}`;
  return d.getFullYear() === now.getFullYear() ? base : `${base} ${d.getFullYear()}`;
}

/** "17:05", local time. */
export function hm(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** "Friday 17:00" within a week, else "21 Nov 17:00". */
export function when(iso: string, now = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const diff = (d.getTime() - now.getTime()) / 86_400_000;
  if (diff >= 0 && diff < 6.5) return `${days[d.getDay()]} ${hm(iso)}`;
  return `${day(iso, now)} ${hm(iso)}`;
}

export function sameDay(iso: string | null | undefined, now = new Date()): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  return (
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  );
}

export function bytes(n: number): string {
  if (n < 1000) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = n;
  let i = -1;
  do {
    v /= 1000;
    i += 1;
  } while (v >= 1000 && i < units.length - 1);
  return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

/** "003" from "003-local-llms", or null. */
export function episodeNumber(id: string): string | null {
  const m = id.match(/^(\d+)/);
  return m ? (m[1] ?? null) : null;
}

/** "version 3" from "brief/SCRIPT-v003.md", or null. */
export function versionOf(path: string | null | undefined): string | null {
  if (!path) return null;
  const m = path.match(/-v(\d+)(?:-[a-z]+)?\.[a-z0-9]+$/i);
  return m ? `version ${Number(m[1])}` : null;
}

/** The text split into paragraphs on blank lines. */
export function paragraphs(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
}

const VIDEO = /\.(mp4|webm|mov|m4v|ogv)$/i;
const IMAGE = /\.(png|jpe?g|webp|gif|svg|avif)$/i;

export function mediaKind(path: string): "video" | "image" | "other" {
  const clean = path.split("?")[0] ?? path;
  if (VIDEO.test(clean)) return "video";
  if (IMAGE.test(clean)) return "image";
  return "other";
}

export function fileName(path: string): string {
  return path.split("/").pop() ?? path;
}

/** The ten steps of a long video, in order: id and the label the screen shows. */
export const STEP_LABELS: Array<[string, string]> = [
  ["idea", "Idea"],
  ["title", "Title"],
  ["proof", "Proof"],
  ["script", "Script"],
  ["record", "Record"],
  ["edit", "Edit"],
  ["thumbnail", "Thumbnail"],
  ["blog", "Blog"],
  ["upload", "Upload"],
  ["results", "Results"],
];
