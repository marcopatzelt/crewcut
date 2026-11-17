# Motion plan v001: demo          bar: none yet (the first approved video sets it)

Written from `motion-plan-v001.json` by `crewcut motion plan --check`. Edit the JSON; the density and budget lines are computed.

## Beats
| # | Time | The viewer must … | Picture | Column | Piece | Length | Cost |
|---|---|---|---|---|---|---|---|
| 1 | 0:00 | know what this is: it runs here, offline | the speaker alone; the first seconds are the face | – | – | – | – |
| 2 | 0:06 | believe the price | the price rolls up and lands on thirty as the word is said, then settles and carries the cut back | a | number_roll {value: 30, unit: cents, label: 1 million tokens, landAt: 1.6} | 3.6 s | 0 |
| 3 | 0:14 | hear the proof from someone else | the speaker, a slow punch-in; the post is said, not shown | – | – | – | – |

## (a) What we have that fits        1 piece: number_roll (params above)

## (b) What we build new for this video      0 pieces

## (c) What would make this video clearly better than the last one
| Upgrade | Why (lesson or reference it comes from) | Effort | Cost | Chosen |
|---|---|---|---|---|
| u1: The number lands on the spoken word, 2 frames early, and the exit is caused by the roll settling instead of a hard cut | baseline the 2D version of this demo cuts hard out of the counter: the bar of this demo is its own 2D cut | S | 0 | yes |
| u2: One GPU serving a hundred people as a custom grid that fills seat by seat | baseline the 2D grid of this demo is a static chart | M | 0 | no |

## Budget and density       full-frame 1 of max 5 · all motion 1 in 0:20 (max 0) · heroes 0 · GPU none, cap $2

## The shelf (read after the beats)

keyword_pop, number_roll
