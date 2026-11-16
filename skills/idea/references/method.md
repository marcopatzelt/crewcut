# Method: measure, grade, set the deadline

`skills/idea/scripts/idea.py` computes exactly these rules. When a rule changes, change this file and the script
together. Thresholds marked "pack" come from `channel.json` `idea` and can be set per user.

## 1. Formats are markets

A niche sets the ceiling of views. A format (a fixed shape of video, such as "made better 100 times") is a market of its
own. A format is worth making when many watch and few deliver; outliers show this, above all on small channels. Formats
close when copies arrive. Only formats with a high barrier stay open longer.

Three ways in:

| Way | Meaning |
|---|---|
| 1 | Make the best video in a format that others make badly (the typical copy is weak). |
| 2 | Bring a proven format from another niche, or from another language market into the user's. |
| 3 | Scale: a fixed test bench that turns each new release into a video within days. |

## 2. Measures

| Measure | Calculation |
|---|---|
| x median | views / median of the last 30 long uploads of the same channel |
| x last 5 | views / average of the 5 long uploads before it. Above 1 within 3 days of upload is an early outlier, even under 2x median. For the user's own channel this is the first measure. |
| per sub | views / subscribers of the channel |
| long upload | longer than `long_min_seconds` (pack, 181 s: Shorts can be up to 3 minutes) |
| fresh | at most `fresh_days` old (pack, 14) |
| outlier | x median at least `outlier_x_median` (pack, 2.0), or per sub at least `outlier_per_sub` (pack, 1.0), or the early signal |
| small channel | `small_channel_subs` (pack, 1,000 to 100,000) |
| breakthrough | small channel with at least `breakthrough_per_sub` views per subscriber (pack, 3.0) |

## 3. Saturation in the source market

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

Formats with a low barrier stay worth it for one to three weeks; copies start after one to three days.

## 4. The gap in the user's market

Only when the user's language (`channel.json` `language`) differs from the market language.

- **empty:** no video in the user's language on the format.
- **thin:** the best one has fewer than `gap_thin_views` views (pack, 30,000).
- **taken:** the best one has more.
- **Imports:** market-language videos that show up in the user's search with a translated title. They compete with a
  local version. A test subject that belongs to the user's market (a local exam, office, trade) beats them.

## 5. Grade (judgement on the measured values)

| Grade | User's market | Source market |
|---|---|---|
| 5 | gap empty, strong proof (3x median or 10 per sub) | open, typical copy weak, barrier high |
| 4 | gap empty or thin, medium proof (2x median) | open or stable, strong proof |
| 3 | gap thin, medium proof; or a series format that tires | closing, but the user's version differs (way 1) |
| 2 | gap taken or proof weak | closing, barrier low |
| 1 | taken and no proof | closed |

When the user's market and the source market are the same, use the source column only. Take one grade off when imports
with more than 100,000 views sit in the user's search and the test subject is not local.

## 6. Barrier and deadline

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

## 7. Market size of a series

Before a new series: take the largest channel on the topic in the user's language and its median of the last 30 long
uploads (`idea.py channel <handle>`). A realistic aim: about 5 % of that median per video after three to six months, at
most 80 % after two years. Under 5,000 views the market is small: start the series with a broader click topic. This is a
rule of thumb, not a measurement.

## 8. Limits of the numbers

Searches return the top 50 results only, so supply counts are lower bounds. A format is recognised from its title; that
is a judgement. Videos of the last two weeks are still growing. Subscriber counts are today's, not those of the upload
day. Click rate and watch time of other channels are not public.
