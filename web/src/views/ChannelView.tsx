import { CHANNEL } from "../api/types";
import { ChatPane } from "../components/ChatPane";
import { Composer } from "../components/Composer";
import { identityOf } from "../components/bits";
import { Avatar } from "../slate/Slate";
import { EMPTY, useUi } from "../store/store";
import { newEpisode, viewToHash } from "../store/actions";

export function ChannelView() {
  const episodes = useUi((state) => state.state?.episodes ?? EMPTY);
  const team = useUi((state) => state.state?.team);
  const lead = identityOf(team, "showrunner");
  const needs = episodes.filter((episode) => episode.open_cards > 0).slice(0, 3);
  return (
    <main className="main chat-main channel-main" aria-label="Channel">
      <ChatPane id={CHANNEL} empty="Ask what is ready, what is scheduled, or what to make next." head={
        <div className="page-head channel-head">
          <div className="channel-lead">
            <Avatar who={lead} size="big" />
            <div>
              <p className="channel-label">Channel</p>
              <h1>{lead.name}</h1>
              <p>Your channel lead. Plans with you and coordinates the crew.</p>
            </div>
          </div>
          <div className="channel-links">
            <button type="button" onClick={newEpisode}>New episode</button>
            <a href="#/episodes">All episodes</a>
          </div>
          {needs.length ? <nav className="channel-links" aria-label="Needs your approval">
            {needs.map((episode) => <a key={episode.id} href={viewToHash({ kind: "episode", id: episode.id })}>
              {episode.title}<span>{episode.open_cards} awaiting approval</span>
            </a>)}
          </nav> : null}
        </div>
      } />
      <div className="dock"><Composer /></div>
    </main>
  );
}
