# The upload package: export/upload.json

One JSON file per episode. Paths are relative to the episode folder. `package_check.py` reads it; `crewcut youtube
upload` uploads it, and only when an accepted publish card carries this file's checksum (see `docs/youtube.md`). Every
change after the card needs a new card.

```json
{
  "title": "Five local models on one laptop",
  "description": "Hook with the number.\nMain link\n\n...",
  "tags": ["ToolName", "Tool Name", "local models", "ChannelName"],
  "video": "export/003-local-llms-v004-final.mp4",
  "captions": [{"file": "export/003-local-llms-en.srt", "language": "en"}],
  "thumbnail": "graphics/thumbnail/a.jpg",
  "category_id": 28,
  "default_language": "en",
  "default_audio_language": "en",
  "privacy": "private",
  "publish_at": "2026-11-20T08:00:00+01:00",
  "made_for_kids": false,
  "paid_promotion": false,
  "contains_synthetic_media": false,
  "synthetic_reason": "Real screen recordings and a real person; no generated people or places.",
  "playlist": null,
  "endscreen_video": null,
  "names": ["ToolName"],
  "ab_test": {"titles": ["…", "…", "…"], "thumbnails": ["graphics/thumbnail/a.jpg", "graphics/thumbnail/b.jpg"]}
}
```

| Key | Meaning |
|---|---|
| `title` | the approved title |
| `description` | the full description text (chapters inside, one per line: `0:00 Name`) |
| `tags` | list of tags |
| `video` | the approved final file (its checksum is on the `final` card) |
| `captions` | own caption files with their language |
| `thumbnail` | the approved thumbnail |
| `category_id` | YouTube category (default from `channel.json`; 28 is Science & Technology) |
| `default_language`, `default_audio_language` | language of title and description, and of the speech (from `channel.json` `language`) |
| `privacy` | `private`, `unlisted` or `public`; with `publish_at` the video is private until that time |
| `publish_at` | ISO time with time zone, or null to publish at once after the card |
| `made_for_kids`, `paid_promotion` | the declarations YouTube asks for |
| `contains_synthetic_media`, `synthetic_reason` | the answer to YouTube's altered-or-synthetic question, and one sentence why (shown on the card) |
| `playlist` | playlist id, or null |
| `endscreen_video` | the own video for the end screen (set by hand in Studio; no API) |
| `names` | names that must be spelled exactly in title, tags and captions |
| `ab_test` | the variants for "Test & compare" (started by the user in Studio; no API) |
| `related_url`, `related_comment` | Shorts: the long video, and the comment the upload posts (pin it in Studio) |
| `cta_keyword`, `cta_url` | a Short's comment word (one word in capitals) and the link a commenter gets as a reply; both or neither; the description and `related_comment` name the word and what viewers get; keep the link short (Shorts comments seldom make links clickable). See docs/youtube.md, comment word -> link reply |

## Description template (neutral)

```
<Hook: one or two sentences, the promise and the measured result with the title's number.>
<Main link, if the channel has one.>

The test: <one sentence: what, with what, how often measured>.

What came out:
• <result 1 with a number>
• <result 2 with a number>
• Limit: <what did not work>

Chapters
0:00 <tool and promise>
0:25 <part>
1:40 <part>
3:05 <verdict>

Links
<tool> (<license>): <link>
<source>: <link>

<The channel's fixed lines from channel.json upload.required_text, if any.>
<The footer file from channel.json upload.description_footer, word for word, if the channel has one.>
<Independence: who paid for the test, or that nobody did.>

#<topic> #<tool> #<channel>
```

No `<` or `>` may stay in the real description; the check fails on them, which also catches forgotten placeholders.
