// One card asks for one yes (DESIGN.md rules 1.4 and 12). Declining or changing is a sentence in the chat.
import { Check, FileText, X } from "lucide-react";
import { useState } from "react";
import type { Card, CardKind, Identity, Step } from "../api/types";
import { api } from "../api/client";
import { about, usd, versionOf, when } from "../lib/format";
import { accept, messageOf } from "../store/actions";
import { ErrorLine, Facts, identityOf, Media } from "./bits";

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
};

export function acceptLabel(card: Card): string {
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
      const amount = spendOf(card).amount;
      return typeof amount === "number" ? `Rent a GPU for ${usd(amount)}` : "Rent a GPU";
    }
    case "rule":
      return "Keep this rule";
    case "profile":
      return "Use this profile";
    case "mix":
      return "Use this mix";
    default:
      return "Approve this";
  }
}

/** One line for a decided card: "Title approved · I ran five local AI models". */
export function foldedText(card: Card): string {
  const noun = NOUN[card.kind] ?? "Card";
  const chosen =
    typeof card.choice === "number" && card.options ? card.options[card.choice] ?? null : null;
  const detail = chosen ?? versionOf(card.file) ?? card.title;
  const verb = card.status === "accepted" ? "approved" : card.status === "declined" ? "not taken" : "expired";
  return `${noun} ${verb} · ${detail}`;
}

export function FoldedCard({ card }: { card: Card }) {
  const text = foldedText(card);
  return (
    <div className="folded" title={text}>
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
  return (
    <div className="file-row">
      <FileText size={14} aria-hidden="true" />
      <a className="one-line" href={api.fileUrl(card.episode, card.file)} target="_blank" rel="noreferrer">
        {card.file}
      </a>
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
  };
}

function SpendWays({ card }: { card: Card }) {
  const s = spendOf(card);
  const gpu = [s.gpus ? `${s.gpus} ×` : null, s.gpuName].filter(Boolean).join(" ");
  const rentedBits = [
    typeof s.amount === "number" ? `About ${usd(s.amount)}` : null,
    typeof s.cap === "number" ? `cap ${usd(s.cap)}` : null,
    "deleted when done",
  ].filter(Boolean);
  return (
    <div className="ways">
      <div className="way">
        <div className="k">On this machine</div>
        <div className="v">{about(s.localSeconds)}</div>
        <div className="m">{[s.localNote, usd(0)].filter(Boolean).join(" · ")}</div>
      </div>
      <div className="way rec">
        <div className="k">{gpu ? `Rented GPU · ${gpu}` : "Rented GPU"}</div>
        <div className="v">{about(s.rentedSeconds)}</div>
        <div className="m">{rentedBits.join(", ")}</div>
      </div>
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
}: {
  card: Card;
  chosen: number;
  onChoose: (i: number) => void;
}) {
  const facts = card.data?.facts;
  const parts = [];
  if (card.kind === "spend") parts.push(<SpendWays key="ways" card={card} />);
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

export function OpenCard({ card, team, steps }: { card: Card; team: Identity[] | undefined; steps: Step[] | undefined }) {
  const who = identityOf(team, card.identity);
  const step = steps?.find((s) => s.id === card.step);
  const [chosen, setChosen] = useState(typeof card.choice === "number" ? card.choice : 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const referral = card.kind === "spend" ? spendOf(card).referral : null;

  async function onAccept() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await accept(card, card.options?.length ? chosen : undefined);
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

  return (
    <section className="card" role="group" aria-label={card.title} data-open-card={card.id}>
      <div className="who">
        <b>{who.name}</b>
        {step ? `${step.label} · ` : ""}needs your yes
      </div>
      <h3>{card.title}</h3>
      {card.body && card.kind !== "rule" ? <p className="card-body">{card.body}</p> : null}
      <CardPreview card={card} chosen={chosen} onChoose={setChosen} />
      <div className="card-actions">
        <button type="button" className="primary" onClick={() => void onAccept()} disabled={busy} data-accept>
          {acceptLabel(card)}
        </button>
        <span className="quiet">
          Or say what to change.{card.kind === "spend" ? " “Local is fine” works too." : ""}
        </span>
      </div>
      {error ? <ErrorLine text={error} onRetry={() => void onAccept()} /> : null}
      {referral?.note ? (
        <p className="ref">
          {referral.note}
          {host ? (
            <>
              {" "}
              <a href={referral.url} target="_blank" rel="noreferrer">
                {host}
              </a>
            </>
          ) : null}
        </p>
      ) : null}
    </section>
  );
}

export function CardItem({ card, team, steps }: { card: Card; team: Identity[] | undefined; steps: Step[] | undefined }) {
  if (card.status === "open") return <OpenCard card={card} team={team} steps={steps} />;
  return <FoldedCard card={card} />;
}
