# Method: measure, test the format, grade, set the deadline

`skills/idea/scripts/idea.py` computes exactly these rules. When a rule changes, change this file and the script
together. Thresholds marked "pack" come from `channel.json` `idea` and can be set per user. Rules marked "(our rule)"
are thresholds Crewcut sets; the others follow the sources at the end.

A **format** is a fixed shape of video: the same premise, the same mechanic, the same title and picture pattern. Only
the **interest topic** changes from episode to episode ("I tried every …", then a plane, a train, a hotel). An
**outlier** is a video with many more views than the other videos of the same channel.

## 0. Own channel first

Before looking at other channels, read the user's own:

1. `crewcut formats score`: every own episode against the first 7 and 28 days of the last 10 videos (section 10).
2. `idea.py channel <own channel>`: the own outliers and early signals.
3. Take the 3 best own long videos apart: mechanic, interest topic, packaging. They are the first source of formats
   ("internal ideas": make the own hit again, with a twist, before others copy it).
4. Note the channels the user's viewers also watch (YouTube Studio, tab "Audience"). They go into the channel list.

## 1. Formats are markets

A niche sets the ceiling of views. A format is a market of its own. A format is worth making when many watch and few
deliver; outliers show this, above all on small channels. Formats close when copies arrive. Only formats with a high
barrier stay open longer.

Three ways in:

| Way | Meaning |
|---|---|
| 1 | Make the best video in a format that others make badly (the typical copy is weak). |
| 2 | Bring a proven format from another niche, another language market or from TV into the user's. |
| 3 | Scale: a fixed test bench that turns each new release into a video within days. |

**Hits alone prove nothing.** Tools and reports show winners only. A test on 5,000 short videos found that a "hot"
format raised the chance of an outlier from about 13 % to 16 %, in the large set not at all. So every format is
measured with its flops: how often it wins against how often the same channels win anyway (section 3).

## 2. Measures

| Measure | Calculation |
|---|---|
| basis median | median views of up to `baseline_before` long uploads before the video and `baseline_after` after it (pack, 15 and 15) on the same channel, at most `baseline_months` away (pack, 6), each at least `mature_days` old today (pack, 28). The video itself does not count. Fewer than `baseline_min_uploads` (pack, 10): no value. |
| x median | views / basis median. Final only when the video is at least `mature_days` old; a younger video's x median is a lower bound ("so far"), because it still grows. |
| tier | candidate from `outlier_x_median` (pack, 2.0), strong from `strong_x_median` (3.0), very strong from `very_strong_x_median` (10.0) |
| x last 5 | views / **median** of the 5 long uploads before it. Above 1 within 3 days of upload is an early signal, even under 2x median. For the user's own channel this is the first measure. |
| per sub | views / subscribers today, only for videos up to `per_sub_max_days` old (pack, 90) |
| log x | log10 of x median; average x only as log x or as a median, never as a raw mean |
| long upload | longer than `long_min_seconds` (pack, 181 s: Shorts can be up to 3 minutes); live streams are left out |
| fresh | at most `fresh_days` old (pack, 14) |
| small channel | `small_channel_subs` (pack, 1,000 to 100,000) |
| breakthrough | small channel with at least `breakthrough_per_sub` views per subscriber (pack, 3.0) |
| co-view era | published from `coview_from` (pack, 2026-11-01). Since November 2026 public view counts include co-views (several people at one TV); a baseline that crosses that day is marked, and comparisons across it are uncertain. |

The window around the video ("at that time") protects against fast-growing channels: measured against today's 30
newest uploads, an old video of a channel that grew looks weak, and a new one looks strong.

A video counts as an **outlier** when its x median reaches the candidate tier or its per sub reaches
`outlier_per_sub` (pack, 1.0), and

1. its baseline has at least `baseline_min_uploads` uploads and a median of at least `baseline_min_median` (pack, 500);
2. it has at least `min_views_market` views in the market language (pack, 10,000) or `min_views_other` in other
   languages (pack, 3,000); "well proven" in the market language from `well_proven_views` (pack, 50,000).

The early signal (x last 5 over 1 within 3 days) counts as well; it needs no views floor.

**Flags.** A collaboration with a big guest (`collab`), the news of a launch day (`news`), visible paid promotion
(`ad`) or a view curve with a single spike (`spike`) are flagged in the labels. Flagged videos leave the tests and are
listed apart.

## 3. Test a format with its flops

1. **Collect every upload, not only the hits.** `idea.py collect` reads every long upload of the last
   `collect_months` (pack, 12; 24 for neighbouring niches with `--months 24`) per channel, plus the baseline months
   before. Channel lists: core niche, neighbouring niches (by the viewers' profile), the user's language, and proof
   languages; at least a third of the channels with 1,000 to 100,000 subscribers.
2. **A cheap label for every video.** Every collected long video gets a format id, or "none", from its title and
   thumbnail: the Scout reads both (`formats --todo` writes the list), or a title rule does it (`--pattern ID=REGEX`,
   the library's `title_patterns`). Only with every video labelled is the denominator right. Check 1 in 20 labels by
   hand.
3. **The full format card** for every hit and as many other videos of the same channels (random, seeded;
   `formats --cards`): title, thumbnail, transcript (automatic subtitles through yt-dlp when it is switched on) and
   frames when available (the first 60 seconds every 10 seconds, then one per minute; or a second opinion that watches
   the public link). Fields: premise in one sentence, mechanic (comparison, claim test, self-experiment with a number,
   build, ranking or list, tutorial, reaction or analysis, story or case, news, challenge with a limit, tiers,
   inversion), interest topic, viral vector, stake (money, time, data, job, status, none), title template, title
   characters and words, thumbnail pattern, hook type of the first 15 seconds, intro seconds, structure, traffic type
   (browse or search), cuts and topic changes per minute (on screen recordings only the topic changes are usable).
   Format and interest topic stay apart. Check 1 in 10 cards by hand.
4. **Measure each format** (`idea.py formats`, flagged videos and videos under 28 days left out):

   | Measure | Calculation |
   |---|---|
   | n, channels, hits | format videos, their channels, and the videos that are outliers (x median at least 2.0 with the views floor) |
   | normal rate | each channel's hit rate on its videos outside the format, shrunk toward the pooled rate of all channels by 10 videos (our rule; a channel with no other hit would otherwise make every hit look impossible) |
   | p hits | the chance of at least that many hits if every format video only had its channel's normal rate (Poisson binomial, exact) |
   | channel wins, p channel | channels where the median x of the format's videos is over 1.0; sign test against a coin flip |
   | q hits, q channel | p hits and p channel after Benjamini-Hochberg over all formats tested together (many tests make chance hits) |
   | lift | median x median of all format videos |
   | share small | share of the hits on small channels |
   | without the top channel | everything again without the channel with the most hits |
   | edge | above (p hits under 0.05), below (the chance of so few hits under 0.05), or no difference |

5. **Evidence level** (our rule):

   | Level | Condition |
   |---|---|
   | strong | n at least 20, channels at least 4, q hits under 0.05, q channel under 0.10, lift at least 1.5, and without the top channel still at least medium |
   | medium | n at least 8, channels at least 3, p hits under 0.05, channel wins at least 2/3 of the channels, lift at least 1.2, and without the top channel still at least hint |
   | hint | hits on at least 2 channels, and too few videos for the tests (under 8, or under 3 channels), or an edge that misses medium |
   | one-channel | more than half of the hits from one channel, or it falls below hint without that channel |
   | none | no edge, or hits on fewer than 2 channels |

   Size: at a normal rate of 13 % a doubling needs about 60 videos to be seen safely; with 8 videos only "4 of 8" is
   clear (p = 0.013).
6. **Repeatable on a channel:** a channel made the format at least 3 times and episodes 3 and later still have a median
   x of at least 1.2. The first episode is usually the best (regression to the mean), which alone does not prove
   saturation.
7. **Decay** in windows of `decay_window_days` (pack, 56) of mature videos: "closing" (our rule) when from the second
   last to the last window the supply of format videos rises by at least 50 % and their median x falls by at least
   30 %.

## 4. Saturation in the source market

The source market is where formats are born (`market_language` and `market_region`, pack, default English and US).

- **Copy:** a long video in the market language whose title matches the format (`--pattern`, or 60 % of the topic's
  words), published in the last 16 weeks.
- **First strong hit:** the earliest copy with at least 10,000 views and at least 25 % of the best video's views.
- **Late copies:** copies 16 to 30 that are at least 7 days old; with fewer than 16, the last 5 of them.

| Verdict | Rule |
|---|---|
| no proof | no copy over 10,000 views in 16 weeks |
| closed | first hit older than 21 days, at least 10 copies after it, late copies' median under 1,000 views (or under 1 % of the best) |
| closing | first hit at most 21 days old and at least 3 copies, or late copies falling |
| open | fewer than 3 copies in the last 28 days |
| stable | late copies still reach 10 % of the first hit |

Formats with a low barrier stay worth it for one to three weeks; copies start after one to three days. Counting comes
first from the collected uploads; one search per format and language adds the rest, and its count is a lower bound.

## 5. The gap in the user's market

Only when the user's language (`channel.json` `language`) differs from the market language.

- **empty:** no video in the user's language on the format.
- **thin:** the best one has at most `gap_thin_views` views (pack, 30,000) **and** fewer than `gap_thin_x_market`
  times (pack, 2.0) the median of the largest channel on the topic in the user's language (section 9;
  `--market-channel`, else the largest channel in the user's search). Without that channel only the fixed limit
  applies, and the check says so.
- **taken:** the best one has more.
- **Imports:** every video in another language among the top 20 of the user's search for the format: dubbed with a
  second audio track, with a translated title, or as the original. Videos can be auto-dubbed into many languages, so
  the gap is smaller than a search for titles in the user's language shows. They compete with a local version. A test
  subject that belongs to the user's market (a local company, office, exam, prices in the local currency) beats them.

## 6. Grade (from the measured values)

| Grade | User's market (gap and proof) | Source market (same language) |
|---|---|---|
| 5 | gap empty, strong proof (3x median) | open, typical copy weak, strong proof |
| 4 | gap empty with medium proof (2x median), or thin with strong proof | open or stable, strong proof |
| 3 | gap thin, medium proof | open or stable with medium proof, or closing but the user's version differs (way 1) |
| 2 | gap taken with proof, or proof weak | closing, or proof weak |
| 1 | taken and no proof | closed or no proof |

When the markets differ the user's column decides; when they are the same, the source column. Then:

- **Grades 4 and 5 only with evidence level strong or medium** (section 3). Without a format test (`check
  --evidence`), an idea reaches at most 3.
- Take one grade off when an import with more than `imports_penalty_views` views (pack, 100,000) ranks in the user's
  search and the test subject is not local (`--local`).
- The barrier and a series format that tires are judgement: take a grade off yourself and say why.

## 7. Audience score (who clicks)

`channel.json` `idea.audience` names the broad audience of the channel as groups of words (for example the people who
build things, the people who make content, the people who want more out of a tool), the words that name the niche
(`core`), words that open a topic for everyone (`open`), words of a framing that scores 0 (`zero`, for example a
company or B2B framing on a channel for individuals), narrow topics (`narrow`, minus 2) and insider words (`insider`,
minus 1 unless an open word stands next to them). The score is a word estimate from the title or topic, 0 to 5:
1, plus 1 for a core word, plus 2 for any group, plus 1 for two groups or an open word. A topic with score 0 is listed
under "not ranked, on purpose". The ranking takes the grade first, then the audience score, then the proof.
No `audience` in the pack: no score.

## 8. Barrier and deadline

| Barrier | Example |
|---|---|
| low | anyone can redo it in a day |
| medium | needs material or a helper |
| high | needs money, a real professional, a real company or many days |

| Situation | At the latest |
|---|---|
| low barrier, source market open or closing | first hit + 14 days (the script prints "send by") |
| low barrier, source market closed | only with a local test subject, else not at all |
| new tool on GitHub | in the first week of its rise |
| new model | 48 to 72 hours after the launch |
| event as the shell | within two weeks of the event |
| high barrier | no pressure from copies; early is still better |

## 9. Market size of a series

Before a new series: take the largest channel on the topic in the user's language and its median of the last 30 long
uploads (`idea.py channel <handle>`). A realistic aim: about 5 % of that median per video after three to six months, at
most 80 % after two years. Under 5,000 views the market is small: start the series with a broader click topic. This is a
rule of thumb, not a measurement.

## 10. Testing a format on the own channel

1. A new format runs as an extra video next to the proven one, not instead of it. About 1 in 4 uploads is a test.
2. Before the upload: estimate the views after 24 hours and 7 days, and the rank among the last 10 videos.
3. Measure fairly: `crewcut youtube results <episode> --first 7` and `--first 28`. The scoreboard (`crewcut formats
   score`) divides the views of those days by the median of the same days of the last 10 videos of the same length
   (x 7d, x 28d), and click-through rate and average view percentage by theirs (CTR rel, AVP rel). Never compare
   today's total views of a new video with old videos.
4. **Search and browse apart.** A format found through search starts slowly: judge it on x 28d; a browse format (home
   page and feed) on x 7d. The traffic type comes from the report's traffic shares, else from the project or the format
   library (`traffic_type`).
5. **Packaging test:** YouTube's A/B test with 2 clearly different variants, or a swap by hand after 48 hours when
   the rank is under the estimate or CTR rel under 0.8. Never both: a swap ends the test.
6. **Diagnosis before any stop** (CTR rel and AVP rel, border 1.0 each): both high, the format carries; click high and
   view share low, the packaging carries and the script or opening is weak (change the script, keep the format); click
   low and view share high, the content carries and the packaging is weak (new title and thumbnail); both low, the
   format is weak for us.
7. **Stop early after 2 episodes** only when both are under 0.5 and both "weak for us".
8. **Decide after 4 episodes:** keep when the median x of the last 4 is at least 1.2, or the subscribers per 1,000
   views are above the channel's; drop under 0.8 without that; in between change after the diagnosis and measure 2
   more. A running format stays while the median of its last 4 is at least 1.0, even when others copy it.
9. With so few episodes chance is large: even with no effect, 2 of 3 episodes are over the median in half the cases.
   4 episodes are a signal, not a proof.

## 11. Limits of the numbers

Searches return the top results only, so supply counts are lower bounds. Labels and cards are a model's or a person's
judgement; check samples by hand. Videos under 28 days still grow. Subscriber counts are today's, not those of the
upload day. Click rate and watch time of other channels are not public. The tests show links, not causes. View counts
from November 2026 on include co-views.

## Sources

- Paddy Galloway, Open Residency 2026 (outliers at 3 to 4x the channel's normal, own hits first, ideas funnel,
  forecast before upload): https://www.youtube.com/watch?v=Z2uoA3bhJT0
- 1of10, tutorial and Jay Clouse interview (2x, "the videos around it", 3 outliers for a pattern, format and interest
  topic apart, 1 in 4 uploads a test): https://www.youtube.com/watch?v=x5BKQtO5IWU,
  https://www.youtube.com/watch?v=h6ipOOl4upI
- Jake Sucoff's test of "hot formats" against each account's normal rate (the reason for counting flops):
  https://www.linkedin.com/in/jsucoff/
- vidIQ outlier tiers (2x, 5x, 10x): https://support.vidiq.com/en/articles/9660010-outliers
- YouTube Help on co-views in public view counts from November 2026: https://support.google.com/youtube/answer/12220281
- Victor Guo's format arbitrage (formats as markets), summarised by Creator Set:
  https://creatorset.substack.com/p/guide-format-arbitrage
