// A finished exchange between two crew members (docs/crew-talk.md, DESIGN.md rule 13): one quiet, collapsed line
// in the chat. Opened, it lists the messages: who to whom, the file it is about, the text. No bubbles between agents.
import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import type { Exchange, Identity, Message } from "../api/types";
import { identityOf } from "./bits";

export function ExchangeLine({ m, exchange, team }: { m: Message; exchange: Exchange; team: Identity[] | undefined }) {
  const [open, setOpen] = useState(false);
  const list = useId();
  const first = exchange.messages[0];
  const name = (id: string) => identityOf(team, id).name;
  const count = exchange.messages.length;
  return (
    <div className="exchange" data-step={m.step ?? undefined}>
      <button type="button" className="exchange-line" aria-expanded={open} aria-controls={list} onClick={() => setOpen((o) => !o)}>
        <ChevronRight size={14} aria-hidden="true" className="exchange-chev" />
        {first ? (
          <span className="one-line">
            {name(first.sender)} and {name(first.recipient)} · {first.kind} about <code>{first.about}</code> ·{" "}
            {count === 1 ? "1 message" : `${count} messages`}
          </span>
        ) : (
          <span className="one-line">{m.text}</span>
        )}
      </button>
      {open ? (
        <ol className="exchange-list" id={list} aria-label="Messages between the crew">
          {exchange.messages.map((x) => (
            <li key={x.id}>
              <div className="exchange-who">
                <b>{name(x.sender)}</b> to <b>{name(x.recipient)}</b> · <code>{x.about}</code>
              </div>
              <p>{x.text}</p>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
