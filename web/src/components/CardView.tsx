// One card asks for one yes (DESIGN.md rules 1.4 and 12). Declining or changing is a sentence in the chat.
import { Check, FileText, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Card, CardKind, Identity, Step } from "../api/types";
import { api } from "../api/client";
import { about, episodeNumber, usd, versionOf, when } from "../lib/format";
import { reducedMotion } from "../lib/platform";
import { accept, decline, messageOf } from "../store/actions";
import { ErrorLine, Facts, identityOf, Keys, Media } from "./bits";
import { Avatar } from "../slate/Slate";
import { Humanized } from "./Humanized";
import { DocumentLink, documentTarget } from "./DocumentLink";
import { FormattedText } from "./FormattedText";
import { baselineOf, styleFrameOf, templateOf } from "./Motion";
import { BaselinePreview, MotionPlanPreview, StyleFramePreview, TemplatePreview } from "./MotionCards";

const NOUN: Record<CardKind, string> = {
  topic: "Topic",
  title: "Title",
  proof: "Facts",
  script: "Script",
  preview: "Cut",
  final: "Final video",
  thumbnail: "Thumbnail",
  publish: "Publishing",
  spend: "GPU rental",
  rule: "Rule",
  profile: "Profile",
  mix: "Mix",
  other: "Request",
  "motion-plan": "Motion plan",
  "style-frame": "Style frame",
  template: "Motion template",
  baseline: "Motion bar",
};

/** Kinds whose body only repeats what their preview shows (the rule text; the plan's lines; the better list). */
const BODY_IN_PREVIEW = new Set<CardKind>(["rule", "motion-plan", "baseline"]);

/** The two ways of a spend card. Accepting a spend card means "rent"; the local way never calls accept. */
export type Way = "local" | "rented";

/** The words the local way sends with its decline, so the crew knows what the user chose. */
export const LOCAL_REASON = "Local is fine. Render on this machine.";

export function acceptLabel(card: Card, way: Way = "rented"): string {
  // a card may name its one action ("This really happened", "Set it up in my Chrome"); money cards never do
  if (card.kind !== "spend" && typeof card.data?.button === "string" && card.data.button) return card.data.button;
  switch (card.kind) {
    case "topic":
      return "Use this topic";
    case "title":
      return "Use this title";
    case "proof":
      return "Use these facts";
    case "script":
      return "Use this script";
    case "preview":
      return "Go on with this cut";
    case "final":
      return "Approve the final video";
    case "thumbnail":
      return "Use this thumbnail";
    case "publish":
      return card.data?.schedule ? `Publish on ${when(card.data.schedule)}` : "Publish now";
    case "spend": {
      if (way === "local") return "Render on this machine";
      const amount = spendOf(card).amount;
      return typeof amount === "number" ? `Rent a GPU for ${usd(amount)}` : "Rent a GPU";
    }
    case "rule":
      return "Keep this rule";
    case "profile":
      return "Use this profile";
    case "mix":
      return "Use this mix";
    case "motion-plan":
      return "Build this motion plan";
    case "style-frame":
      return "Build from this frame";
    case "template":
      return "Keep it in the library";
    case "baseline": {
      const b = baselineOf(card);
      const n = b ? episodeNumber(b.new.episode) ?? b.new.episode : null;
      if (!n) return "Raise the bar";
      return b?.old ? `Raise the bar to ${n}` : `Make ${n} the bar`;
    }
    default:
      return "Approve this";
  }
}

/** One line for a decided card: "Title approved · I ran five local AI models". */
export function foldedText(card: Card): string {
  const noun = NOUN[card.kind] ?? "Card";
  const verb = card.status === "accepted" ? "approved" : card.status === "declined" ? "not taken" : "expired";
  if (card.kind === "spend") {
    const s = spendOf(card);
    if (card.status === "declined") return `${noun} ${verb} · this machine renders`;
    const bits = [
      typeof s.rentedSeconds === "number" ? about(s.rentedSeconds).toLowerCase() : null,
      typeof s.amount === "number" ? `for about ${usd(s.amount)}` : null,
    ].filter(Boolean);
    return `${noun} ${verb} · ${bits.length ? bits.join(" ") : card.title}`;
  }
  const chosen =
    typeof card.choice === "number" && card.options ? card.options[card.choice] ?? null : null;
  const detail = chosen ?? motionDetail(card) ?? versionOf(card.file) ?? card.title;
  return `${noun} ${verb} · ${detail}`;
}

/** What a decided motion card was about: "dial, round 1", "Board build, version 2", "from 011 to 013". */
function motionDetail(card: Card): string | null {
  if (card.kind === "style-frame") {
    const sf = styleFrameOf(card);
    return sf?.insert ? `${sf.insert}, round ${sf.round}` : null;
  }
  if (card.kind === "template") {
    const t = templateOf(card);
    return t ? `${t.title}, version ${t.version}` : null;
  }
  if (card.kind === "baseline") {
    const b = baselineOf(card);
    if (!b) return null;
    const n = (id: string) => episodeNumber(id) ?? id;
    return b.old ? `from ${n(b.old.episode)} to ${n(b.new.episode)}` : `${n(b.new.episode)} is the bar`;
  }
  return null;
}

export function FoldedCard({ card, fresh }: { card: Card; fresh?: boolean }) {
  const text = foldedText(card);
  return (
    <div className={fresh ? "folded is-new" : "folded"} title={text} data-card-step={card.step}>
      {card.status === "accepted" ? (
        <Check size={14} className="ok" aria-hidden="true" />
      ) : (
        <X size={14} aria-hidden="true" />
      )}
      <span className="one-line">{text}</span>
    </div>
  );
}

function FileLine({ card }: { card: Card }) {
  if (!card.file || !card.episode) return null;
  const target = documentTarget(card.file, card.episode);
  return (
    <div className="file-row">
      <FileText size={14} aria-hidden="true" />
      {target ? <DocumentLink {...target} className="document-link one-line">
        {card.file}
      </DocumentLink> : <a className="one-line" href={api.fileUrl(card.episode, card.file)} target="_blank" rel="noreferrer">
        {card.file}
      </a>}
      {card.sha256 ? <span className="meta" title={`sha256 ${card.sha256}`}>{`sha256 ${card.sha256.slice(0, 8)}`}</span> : null}
    </div>
  );
}

/** The numbers of a spend card, whether the estimate is nested (server) or flat. */
export function spendOf(card: Card) {
  const d = card.data ?? {};
  const est = { ...d, ...(d.estimate ?? {}) };
  const amount = card.amount_usd ?? d.amount_usd ?? est.rented_usd;
  const cap = typeof d.cap_usd === "number" ? d.cap_usd : typeof d.budget_usd === "number" ? d.budget_usd : est.rented_usd_worst;
  const localNote =
    est.local_source ?? (est.local_measured === false ? "not measured on this machine yet" : undefined);
  return {
    amount: typeof amount === "number" ? amount : undefined,
    cap: typeof cap === "number" ? cap : undefined,
    localSeconds: est.local_seconds,
    rentedSeconds: est.rented_seconds,
    gpus: est.gpus,
    gpuName: est.gpu_name,
    localNote,
    referral: d.referral ?? est.referral ?? null,
    idleNote: typeof est.idle_note === "string" ? est.idle_note : undefined,
  };
}

/**
 * The honest first choice (DESIGN.md rule 12): the rented GPU only when it saves at least an hour.
 * If the times are not known, this machine, because it costs nothing.
 */
export function suggestedWay(card: Card): Way {
  const s = spendOf(card);
  if (typeof s.localSeconds !== "number" || typeof s.rentedSeconds !== "number") return "local";
  return s.localSeconds - s.rentedSeconds >= 3600 ? "rented" : "local";
}

function SpendWays({ card, way, onWay }: { card: Card; way: Way; onWay: (w: Way) => void }) {
  const s = spendOf(card);
  const gpu = [s.gpus ? `${s.gpus} ×` : null, s.gpuName].filter(Boolean).join(" ");
  const rentedBits = [
    typeof s.amount === "number" ? `About ${usd(s.amount)}` : null,
    typeof s.cap === "number" ? `cap ${usd(s.cap)}` : null,
    "deleted when done",
  ].filter(Boolean);
  const ways: Array<{ id: Way; k: string; v: string; m: string }> = [
    { id: "local", k: "On this machine", v: about(s.localSeconds), m: [s.localNote, usd(0)].filter(Boolean).join(" · ") },
    { id: "rented", k: gpu ? `Rented GPU · ${gpu}` : "Rented GPU", v: about(s.rentedSeconds), m: rentedBits.join(", ") },
  ];
  return (
    <div className="ways" role="radiogroup" aria-label="Where to render">
      {ways.map((w) => (
        <button
          type="button"
          key={w.id}
          role="radio"
          aria-checked={way === w.id}
          className="way"
          data-way={w.id}
          onClick={() => onWay(w.id)}
        >
          <span className="k">{w.k}</span>
          <span className="v">{w.v}</span>
          <span className="m">{w.m}</span>
        </button>
      ))}
    </div>
  );
}

function Options({
  options,
  chosen,
  onChoose,
  label,
}: {
  options: string[];
  chosen: number;
  onChoose: (i: number) => void;
  label: string;
}) {
  return (
    <div className="options" role="radiogroup" aria-label={label}>
      {options.map((o, i) => (
        <button
          type="button"
          key={`${i}-${o}`}
          role="radio"
          aria-checked={chosen === i}
          className="option"
          onClick={() => onChoose(i)}
        >
          <span className="tick" aria-hidden="true">
            {chosen === i ? <Check size={12} /> : null}
          </span>
          <span className="one-line" title={o}>
            {o}
          </span>
        </button>
      ))}
    </div>
  );
}

function ProfilePreview({ card }: { card: Card }) {
  const profile = card.data?.profile;
  const rows = profile?.rows?.slice(0, 6) ?? [];
  const video = card.preview ?? profile?.preview ?? null;
  return (
    <>
      {rows.length ? (
        <div className="rows">
          {rows.map((r) => (
            <div className="prow" key={r.label}>
              <span className="label">{r.label}</span>
              <span className="value">
                {r.kind === "color" ? <span className="swatch" style={{ background: r.value }} aria-hidden="true" /> : null}
                <span className="one-line">{r.value}</span>
              </span>
              <span className="source one-line">{r.source}</span>
            </div>
          ))}
        </div>
      ) : null}
      {video && card.episode ? (
        <div className="preview solo">
          <Media episode={card.episode} path={video} label="10-second preview in your style" />
        </div>
      ) : null}
    </>
  );
}

function CardPreview({
  card,
  chosen,
  onChoose,
  way,
  onWay,
  folding,
}: {
  card: Card;
  chosen: number;
  onChoose: (i: number) => void;
  way: Way;
  onWay: (w: Way) => void;
  folding: boolean;
}) {
  const facts = card.data?.facts;
  const parts = [];
  if (card.kind === "spend") parts.push(<SpendWays key="ways" card={card} way={way} onWay={onWay} />);
  if (card.kind === "motion-plan") parts.push(<MotionPlanPreview key="motion-plan" card={card} folding={folding} />);
  if (card.kind === "style-frame") parts.push(<StyleFramePreview key="style-frame" card={card} />);
  if (card.kind === "template") parts.push(<TemplatePreview key="template" card={card} />);
  if (card.kind === "baseline") parts.push(<BaselinePreview key="baseline" card={card} />);
  if (card.kind === "rule") {
    parts.push(
      <div key="rule">
        <p className="rule-text">{card.data?.rule ?? card.body}</p>
        {card.data?.source ? <p className="meta">Source: {card.data.source}</p> : null}
      </div>,
    );
  }
  if (card.kind === "profile") parts.push(<ProfilePreview key="profile" card={card} />);
  if (card.options?.length) {
    parts.push(<Options key="options" options={card.options} chosen={chosen} onChoose={onChoose} label={card.title} />);
  }
  if (card.preview && card.episode && card.kind !== "profile") {
    parts.push(
      <div key="media" className={facts?.length ? "preview" : "preview solo"}>
        <Media episode={card.episode} path={card.preview} label={`Preview: ${card.title}`} />
        {facts?.length ? <Facts facts={facts} /> : null}
      </div>,
    );
  } else if (facts?.length) {
    parts.push(<Facts key="facts" facts={facts} />);
  }
  if (card.file && card.episode && card.kind !== "spend" && card.kind !== "profile") {
    parts.push(<FileLine key="file" card={card} />);
  }
  if (!parts.length) return null;
  return <div className="card-preview">{parts}</div>;
}

export function OpenCard({
  card,
  team,
  steps,
  fresh,
  folding,
  initialWay,
}: {
  card: Card;
  team: Identity[] | undefined;
  steps: Step[] | undefined;
  fresh?: boolean;
  /** A copy of a card that was just decided, folding away: not interactive, hidden from assistive tech. */
  folding?: boolean;
  initialWay?: Way;
}) {
  const who = identityOf(team, card.identity);
  const step = steps?.find((s) => s.id === card.step);
  const [chosen, setChosen] = useState(typeof card.choice === "number" ? card.choice : 0);
  const [way, setWay] = useState<Way>(() => initialWay ?? suggestedWay(card));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const spend = card.kind === "spend";
  const referral = spend ? spendOf(card).referral : null;

  async function onAccept(standing = false) {
    if (busy || folding) return;
    setBusy(true);
    setError(null);
    try {
      if (spend && way === "local") await decline(card, LOCAL_REASON);
      else if (standing) await accept(card, 1);
      else await accept(card, card.options?.length ? chosen : undefined);
    } catch (e) {
      setError(`Couldn't send your yes. ${messageOf(e)}`);
      setBusy(false);
    }
  }

  let host = "";
  try {
    host = referral?.url ? new URL(referral.url).hostname : "";
  } catch {
    host = "";
  }

  const cls = ["card", fresh ? "is-new" : null].filter(Boolean).join(" ");
  return (
    <section
      className={cls}
      role={folding ? undefined : "group"}
      aria-label={folding ? undefined : card.title}
      data-open-card={folding ? undefined : card.id}
      data-card-step={card.step}
    >
      <div className="card-head">
        <Avatar who={who} size="small" />
        <b>{who.name}</b>
        {step ? <span className="one-line">{step.label}</span> : null}
        <span className="card-ask">needs your yes</span>
      </div>
      <h2 className="card-title">{card.title}</h2>
      {card.body && !BODY_IN_PREVIEW.has(card.kind) ? <div className="card-body"><FormattedText text={card.body} episode={card.episode ?? undefined} /></div> : null}
      <CardPreview card={card} chosen={chosen} onChoose={setChosen} way={way} onWay={setWay} folding={Boolean(folding)} />
      <Humanized card={card} folding={Boolean(folding)} />
      <div className="card-actions">
        <button
          type="button"
          className="primary"
          onClick={() => void onAccept()}
          disabled={busy || folding}
          data-accept
          tabIndex={folding ? -1 : undefined}
        >
          {acceptLabel(card, way)}
        </button>
        {card.kind === "publish" && card.data?.standing_offer ? (
          <button
            type="button"
            className="quiet-action"
            onClick={() => void onAccept(true)}
            disabled={busy || folding}
            tabIndex={folding ? -1 : undefined}
          >
            Publish this and all future Shorts without asking
          </button>
        ) : (
          <span className="quiet">Or say what to change.</span>
        )}
        <Keys keys={["mod", "enter"]} className="card-keys" />
      </div>
      {error ? <ErrorLine text={error} onRetry={() => void onAccept()} /> : null}
      {spend && spendOf(card).idleNote ? <p className="ref">{spendOf(card).idleNote}</p> : null}
      {referral?.note ? (
        <p className="ref">
          {referral.note}
          {host ? (
            <>
              {" "}
              <a href={referral.url} target="_blank" rel="noreferrer" tabIndex={folding ? -1 : undefined}>
                {host}
              </a>
            </>
          ) : null}
        </p>
      ) : null}
    </section>
  );
}

/**
 * An open card, or the one line it folds to once decided. When a card is decided while it is on screen, the open card
 * folds away (grid rows 1fr to 0fr, --spring-snappy) while the line fades in (rule 9).
 */
export function CardItem({
  card,
  team,
  steps,
  fresh,
}: {
  card: Card;
  team: Identity[] | undefined;
  steps: Step[] | undefined;
  fresh?: boolean;
}) {
  const open = card.status === "open";
  const [wasOpen, setWasOpen] = useState(open);
  const [folding, setFolding] = useState(false);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (wasOpen && !open && !reducedMotion()) setFolding(true);
  }
  useEffect(() => {
    if (!folding) return;
    const t = setTimeout(() => setFolding(false), 300);
    return () => clearTimeout(t);
  }, [folding]);

  if (open) return <OpenCard card={card} team={team} steps={steps} fresh={fresh} />;
  return (
    <>
      {folding ? (
        <div className="fold-out" aria-hidden="true">
          <div>
            <OpenCard
              card={{ ...card, status: "open" }}
              team={team}
              steps={steps}
              folding
              initialWay={card.status === "accepted" ? "rented" : "local"}
            />
          </div>
        </div>
      ) : null}
      <FoldedCard card={card} fresh={fresh || folding} />
    </>
  );
}
