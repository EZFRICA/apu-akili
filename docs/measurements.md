# Measurements

What each component costs, measured against the services it really uses, not mocked. Where an
answer can be right or wrong the harness checks it: a fast component that answers wrongly is not
healthy. The harness needs several provider keys, so it is not in this repository.

Run on **2026-10-04**, Apple M2, home broadband in Europe, with the routing of
[models.md](./models.md), two runs per case; the tables give the median.

## The local tier costs almost nothing

| Component | Case | Median | Result |
|---|---|---:|---|
| embed | one query | 10 ms | 384 dimensions |
| embed | batch of 16 | 141 ms | 16 vectors |
| retrieval | L3 vector search | 54 ms | 12 rows; the first search opens the connection |
| retrieval | memory search, BMJ and L3 | 12 ms | 1 block |
| retrieval | load the DLL (L2) | under 1 ms | 4 nodes |
| braille | grade 2, short answer | 10 ms | 126 cells |
| braille | grade 2, revision sheet | 4 ms | 880 cells, 1 page |
| api | `GET /escalations` | 11 ms | 200, 6 events |
| clustering | 6 events, real embedder and HDBSCAN | 57 ms | 2 clusters |

The whole memory hierarchy, braille and the teacher API cost milliseconds next to a model call
of a second or more. **What costs time is the network, not the tiering**, which is the premise of
the architecture.

## The remote tier is the whole cost

| Component | Case | Median | Result |
|---|---|---:|---|
| guard | seven cases, English and French, one injection | 0.79 to 1.09 s | every verdict right |
| answer | the tutor model, one question | 7.44 s | 2172 characters |
| write-back | the memory write-back model | 0.73 s | valid JSON |
| search | Tavily, two queries | 1.7 s | 5 sources each, no excluded domain |
| notebook | key points | 0.85 s | 5 points |
| notebook | revision sheet | 0.90 s | 363 characters |
| voice | speech out, Gemini fallback | 1.56 s | 562 kB of WAV |
| voice | speech in, Gemini | 1.44 s | transcript exact |
| turn | text to text, no search | 7.45 s | 1548 characters, no memory problem |

The bench measures speech on the Gemini path; ElevenLabs, the default, is measured in
[models.md](./models.md) at 1.68 s for speech out. A spoken turn end to end took 8.6 s on
2026-09-23.

**A text turn is the tutor writing.** Retrieval is milliseconds and the guard about a second; the
rest is the answer. A text turn measured 5.0 s on 2026-09-23 and 7.45 s here, for a 1548-character
answer; two runs with answers of different lengths are not enough to call that a regression.

## What earlier measurements changed

The first full run, on 2026-09-19 with the models then in use, produced these changes, all still
in the code:

- **Latency tracks tokens written, not model size.** On the notebook's key points the small model
  wrote about 1700 tokens to return 140 characters and took 11.6 s; a larger, terser model took
  3.5 s. "A small model for background work" was an assumption the measurement did not support.
  The current small model does it in 0.85 s, so the role moved again: a routing decision holds
  only for the models it was measured on.
- **A new event loop per turn cost half a second.** NeMo Guardrails caches HTTP clients bound to
  the loop that made them, and `asyncio.run` per turn left them stale: 1.48 s a guard check
  against 0.98 s on one shared loop. `apu.ui.common.run` keeps one loop alive, pinned by a test.
- **A spoken turn took 43.9 s**, 79% of it the speech model reading the answer. Moving speech to
  ElevenLabs brought it to 8.6 s.
- **An answer can come back cut.** One reading returned 22 s of audio for 90 s of text, and a
  listening pupil cannot tell. `synthesize` reads again once when the audio is under 60% of the
  length the text implies, and keeps the fuller one.
- **The guard is on every turn and costs about a second.** That is the price of the product's
  central promise, and the injection case is the slowest, since there is more to weigh.

**Still open**: a tutor answer of 2000 characters or more is long for a pupil, and it sets the
pace of every turn, every reading aloud and the bill. Asking for shorter answers is a teaching
decision as much as a performance one.
