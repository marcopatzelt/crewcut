---
name: upload
description: "Builds the YouTube upload package of an episode (export/upload.json: title, description with chapters, tags, captions, thumbnail, settings, schedule, A/B variants), checks it with skills/upload/scripts/package_check.py, asks for the publish card, uploads through the YouTube Data API (crewcut youtube upload), guides the user to YouTube Studio where no API exists (A/B test, end screen), and runs the 48-hour check. Use when: \"upload\", \"publish\", \"put it on YouTube\", \"schedule the video\", \"description\", \"tags\", \"captions\", \"chapters\", \"A/B test\", \"48 hours\", \"how is the video doing\". Not for title rules (skills/title) or the thumbnail image (skills/thumbnail)."
---

# Upload

The Publisher turns the finished episode into an upload package, checks it, gets the yes, uploads it through the API and
measures it after 48 hours. Before this step: the final cut is approved (`skills/edit/`), the title is chosen
(`skills/title/`), the thumbnail is chosen (`skills/thumbnail/`).

## Hard limits

- **Publishing needs a `publish` card for exactly this video, every time.** A yes for one video never carries over.
  Without a yes the video stays private.
- **The upload goes through the YouTube Data API** (`crewcut youtube upload`), never through clicks in a browser. Only
  the Publisher (`may_publish: true`) uploads.
- Posting or pinning a comment, changing channel settings, swapping a thumbnail after the upload: a card each time.
- Music or clips with unclear rights: name them on the publish card.

## The package

`export/upload.json` in the episode folder; the format is in `references/package.md`. Paths are relative to the episode.

- **Title:** the approved one, passes `title_check.py`.
- **Description:** under 5,000 bytes, no `<` or `>` (YouTube rejects them). The first two lines carry the hook with
  the number and, when the channel has one, the main link (`channel.json` `upload.main_link`); YouTube shows about 150
  characters before "more". Then the test in one sentence, the results as short points, chapters, links to the tool
  and sources, the channel's fixed lines (`upload.required_text`), then the channel footer word for word (the file named
  in `upload.description_footer`, in the style pack folder: who makes the channel and the company), at most
  `upload.hashtags_max` hashtags. Never rewrite the footer in the description; change the file.
- **Chapters:** measured from the final cut, never estimated. YouTube needs: first chapter at 0:00, at least 3, each at
  least 10 seconds.
- **Tags:** the tool's name and its spellings first, then the topic words people search, the channel name last. At most
  500 characters by YouTube's count. Tags help little, mostly for misspelled searches.
- **Captions:** own captions from the final cut's word times (`crewcut cut srt …`), names spelled exactly as in the
  title. Delete blocks that speech-to-text invented in silence or music (the check knows common ones).
- **Thumbnail:** from the Designer, 1280x720, under 2 MB.
- **Settings:** category and language from `channel.json`; `made_for_kids` declared; `paid_promotion` declared;
  `contains_synthetic_media`: answer the altered-or-synthetic question yourself from what is in the video, with one
  sentence why in `synthetic_reason`. The publish card shows the answer; the user confirms it with the card.
- **Schedule:** a fixed time helps viewers come back. When `channel.json` has `upload.publish_time`, schedule the next
  free day at that time in `upload.timezone`. A scheduled video is uploaded as private with `publish_at`.
- **A/B variants:** three titles from the title step, the thumbnails from the Designer (`ab_test` in the package).
- **End screen:** one specific own video that viewers click for the same reason (same topic or format), never an
  automatic choice. Write its id into `endscreen_video`.

## Steps

1. Build the package and run `python3 skills/upload/scripts/package_check.py <id>` until 0 errors. Read every warning.
   The description goes through the Humanizer pass first (skills/script, "Humanizer pass"): draft in
   `work/description-draft-vNNN.md`, result in `export/description-vNNN.md` and in the package, then
   `crewcut humanize record --draft work/description-draft-vNNN.md --final export/description-vNNN.md`. Chapters, links,
   the AI disclosure and the channel footer stay word for word.
2. Card: `crewcut card propose --episode <id> --step upload --kind publish --title "Publish <day> <time>" --file
   export/upload.json --body "<title> · <visibility> · AI question: <answer>, <why>"`, then `crewcut card wait`.
   Declined: change what the user says, check again, new card.
3. Upload: `crewcut youtube upload --episode <id> [--schedule <ISO time>]`. Not connected yet (`crewcut youtube
   status`): `crewcut youtube connect --episode <id>`. It posts one card; on the user's yes Claude in Chrome sets up the
   API on their computer and the chat gets the sign-in link. Uploads always go through the API, never the browser. Then `crewcut youtube status` and tell the
   user the link in one message.
4. **Where YouTube has no API**, build everything and send the user to the right page with one sentence of what to
   click: the A/B test ("Test & compare": upload the variants under "A/B Testing" on the video's details page in
   YouTube Studio), the end screen (the video's editor in Studio). The agent never clicks there.
5. The upload writes `export/upload-result.json` (video id, link, notes such as a thumbnail that could not be set).
   Never change `export/upload.json` after the card: its checksum is what the user approved. Run
   `crewcut youtube verify <id>` and review `review/publication-check.json`. Differences need review, not automatic
   changes on YouTube. This checks metadata and caption track readiness, not video content or caption text.
   Only after review: `crewcut episode step <id> upload done`.
6. Between two episodes: write a community post (a poll, a picture from the test, a question). There is no API for
   community posts; the user posts it.

## 48-hour check

1. After 48 hours: views, likes and comments of the video. Compare views per hour with the user's other videos.
2. The early signal after 3 days: `python3 skills/idea/scripts/idea.py channel <own channel>` lists the own outliers
   with `x last 5` (views against the average of the five uploads before). Above 1 is a good sign.
3. Run `crewcut youtube results <id> --start YYYY-MM-DD --end YYYY-MM-DD` for views, watch time, average view
   duration/percentage and engagement. The report names its calendar-day period; never label it an exact rolling
   48-hour window. Missing data stays missing, not zero. Impressions, click rate and unique viewers require separate
   YouTube Studio evidence, not invented API fields. Views per unique viewer only makes sense for matching periods.
4. A finished A/B test: the user drops a screenshot of the result into the chat; the agent reads it. The user never
   types numbers.
5. Write `review/results-48h.json` and tell the user the result in two sentences: how the video does against the
   others, and what that means for title and thumbnail. A rule changes only through `crewcut rule propose`.

## Planned

- Importing YouTube Studio evidence for thumbnail impressions, click rate and unique viewers.
- A visual and listening check beyond the implemented metadata check (`crewcut youtube verify`).
- Adding the video to a playlist (`channel.json` `upload.playlist`) through the API.
- Opening the A/B test and end screen pages for the user by computer use, as an option.

## Sources

- Vexian in Grant Owen's podcast, "The Crazy Genius Who Solved The Youtube Algorithm":
  https://www.youtube.com/watch?v=41HMFGbENj4. Taken: the end screen with the same reason to click, a fixed upload time,
  a community post between episodes, views per unique viewer, the early signal against the last five uploads.
