# Choosing a model for each role

Eight places in the pipeline call a model, and they ask for different things: a classifier that
must be right about a child in distress, a tutor that must call tools, an embedder that must run
offline, a voice that must not make a pupil wait. Every figure below comes from a call actually
made, on 2026-09-19 from a laptop in Europe (speech re-measured 2026-10-04), not from a model
card. The harness needs several provider keys, so it is not in this repository.

## What runs now

`apu/inference/llm.py` routes each text role, `apu/modality/voice.py` the speech roles,
`apu/tools/visual.py` the pictures. The
guard's model is named twice, in `apu/config.py` and `apu/guardrails/config/config.yml`, and a
test pins them together.

| Role | Model | Measured | Beaten, and why |
|---|---|---|---|
| Tutor answer | `gemini-3.8-flash` | a text turn in 5.0 s, 7.45 s on 2026-10-04 | gpt-oss-120b, faster but writing 471 tokens to its 258 |
| Topical guard | `gemini-3.5-flash-lite` | 69/69 attacks, 0.66 s | the 120B model it replaced, 69/69 in 1.58 s |
| Search-query gate | `gemini-3.1-flash-lite` | 10/10, 0.73 s | 3.5 Flash Lite, which blocks a legitimate PE query |
| Memory write-back | `gemini-3.5-flash-lite` | 0.77 s | the previous small model, same result in 3.92 s |
| Notebook key points, sheets | `gemini-3.5-flash-lite` | 0.85 s | the tutor model, 6.9 s |
| Embeddings | local MiniLM (ONNX) | 4 ms, offline | online embedders, 50 to 100 times slower |
| Speech in | `scribe_v2` | about 1 s | `scribe_v1`, which fails on exactly the same clips |
| Speech out | `eleven_v4_turbo` | 1.68 s, first audio 0.35 s | `eleven_flash_v2_5` is faster (0.85 s): a choice of voice |
| Speech out, fallback | `gemini-3.8-flash-lite-tts` | 3.47 s | the fastest Gemini speech model, used if ElevenLabs fails |
| Pictures | `gemini-nano-banana-2.1` | 15 to 35 s a picture | nothing else measured yet |

**A routing decision holds only for the models it was measured on.** The notebook moved twice:
off the small model when that model spent 1700 tokens to return 140 characters, then back onto
the small one once a different small model measured 0.81 s against 6.89 s.

## Providers, verified by calling them

- **Gemini**: the console's display names are not API ids (`gemini-3.1-flash-tts` is a 404, only
  the `-preview` id exists); the omni models refuse `generateContent`. Two models the API marks
  confidential were measured and are not named here.
- **Nebius Token Factory**: 24 callable models (Nemotron, Qwen, DeepSeek, gpt-oss, gemma, one
  embedder). No speech, no images.
- **NVIDIA NIM**: 82 models listed, few callable with this key, and the ones that answer are the
  same weights Nebius serves, **slower**, with timeouts of 60 to 180 s. Kept as a second source.
- **ElevenLabs**: three transcribers and the account's voices; library voices are refused on a
  free plan (HTTP 402), and `scribe_v2_realtime` belongs to the websocket API only.
- **Gemini Live**: needs explicit `activity_start` and `activity_end` markers. Automatic voice
  detection never closed the turn on a recorded clip.

## Topical guard

Eighteen labelled cases left four candidates tied at 100%, so the best were run against the full
69-attack corpus from [security.md](./security.md):

| Candidate | Attacks held | Median | Missed |
|---|---:|---:|---|
| gemini: gemini-3.5-flash-lite | **69/69**, twice | **0.66 s** | nothing |
| gemini: gemini-flash-lite-latest | 69/69 | 0.74 s | nothing |
| nebius: nemotron-3-super-120b (then current) | 69/69 | 1.58 s | nothing |
| gemini: gemini-3.1-flash-lite | 68/69 | 0.60 s | a lesson carrying an off-topic errand |
| gemini: gemini-3.8-flash | 67/69 | 1.26 s | called a sad pupil off-topic, over-blocked a question |
| nebius: gemma-3-27b-it | 65/69 | 0.38 s | a ROT13 payload, two prompt exfiltrations |

**Size and version do not predict this.** The newest, largest Flash is twice as slow as the Lite
models and treats a pupil saying they are unhappy as misbehaviour. Gemma is fastest and fails
exactly the obfuscation a curious pupil will find.

## Search-query gate

| Candidate | Accuracy, 10 queries | Median | Output tokens |
|---|---:|---:|---:|
| gemini: gemini-3.1-flash-lite | **1.00** | **0.73 s** | 8 |
| gemini: gemini-3.5-flash-lite | 0.90 | 0.62 s | 10 |
| nebius: Nemotron-3-Nano-30B (then current) | 1.00 | 1.15 s | 75 |

The best guard is a worse gate: it blocks "offside rule football explanation", a legitimate PE
query. Strictness makes a good guard and a bad gate, so the two roles get different models.

## Memory write-back

| Candidate | Valid JSON | Kept the pupil's name | Median | Output tokens |
|---|---:|---:|---:|---:|
| gemini: gemini-3.5-flash-lite | 3/3 | 3/3 | **0.77 s** | 68 |
| gemini: gemini-3.1-flash-lite | 3/3 | 3/3 | 0.80 s | 55 |
| nebius: gemma-3-27b-it | 3/3 | 3/3 | 0.94 s | 69 |
| nebius: Nemotron-3-Nano-30B (then current) | 3/3 | 3/3 | 3.92 s | 383 |

The first three are tied: one of them measured 1.42 s in an earlier session on the same network.
The gap that survives is the verbose model, slow because it writes six times more.

## Tutor

Three cases: English, French answered in French, and a braille turn that must be plain text.
Native tool calling is required, since web search and the notebook are tool calls.

| Candidate | Tool calls | Checks | Median | Output tokens |
|---|---|---:|---:|---:|
| nebius: gpt-oss-120b | yes | 5/5 | **2.03 s** | 471 |
| nebius: nemotron-3-super-120b (then current) | yes | 5/5 | 2.91 s | 432 |
| gemini: gemini-3.8-flash | yes | 5/5 | 3.27 s | 258 |
| gemini: gemini-3.1-pro-preview | yes | 5/5 | 8.47 s | **205** |
| nebius: Qwen3.5-397B-A17B | yes | 5/5 | 8.26 s | 1305 |
| nebius: gemma-3-27b-it | **no** | | | |

These checks rank speed and verbosity, not teaching quality. They do disqualify gemma, which
never emits a tool call, and Qwen3.5, which writes three times more than the others: the spoken
channel pays for every word.

## Embeddings

Twelve questions over the 16 shipped chapters, without the class filter production applies.

| Candidate | Top-1 | Per query |
|---|---:|---:|
| nvidia: nemotron-3-embed-1b | **1.00** | 196 ms |
| nebius: Qwen3-Embedding-8B | 0.92 | 314 ms |
| local: MiniLM-L12-v2 (current) | 0.83 | **4 ms** |
| gemini: gemini-embedding-001 | 0.83 | 390 ms |

**Keep the local embedder**: it must work on a disconnected device. Its two misses are fractions
chapters of another grade, which the class filter removes. If retrieval ever moves online,
NVIDIA's embedder is the one to use.

## Speech to text

Ten clips, half in French, spoken by two engines so that no transcriber is graded only on its
own provider's audio.

| Candidate | Mean WER | Median |
|---|---:|---:|
| gemini: gemini-3.8-flash | **6.7%** | 1.67 s |
| elevenlabs: scribe_v2 | 7.7% | 1.04 s |
| elevenlabs: scribe_v1 | 7.7% | 1.04 s |
| gemini: gemini-3.5-transcribe (then current) | 15.3% | 1.50 s |
| gemini-live: gemini-3.8-live | 18.1% | 5.51 s |

For a maths tutor the numbers matter most. On ten French questions carrying 22 numbers,
`scribe_v1` and `scribe_v2` both kept 16, **failing on the same clips in the same words**
("36 billes" heard as "26 bills"). An error both make on one clip is the clip, so nothing
separates them, and `scribe_v2` stays. An earlier version of this file chose `scribe_v1` on a
single dropped number in one run; the wider set reversed it.

Two cautions. A 71% WER for Gemini on "un quart plus un sixième" is a correct transcription that
wrote "1/4 + 1/6". And `gemini-3.8-live` is a dialogue model, listening to reply rather than to
transcribe. `gemini-3.5-transcribe-live` does work, once driven with explicit activity markers.

## Text to speech

ElevenLabs, measured 2026-10-04 on a 230-character answer, read back to check nothing was
dropped:

| Candidate | Whole answer | First audio | Audio produced | Read-back WER |
|---|---:|---:|---:|---:|
| elevenlabs: eleven_flash_v2_5 | **0.85 s** | **0.32 s** | 13.8 s | 0% |
| elevenlabs: eleven_v4_turbo (current) | 1.68 s | 0.35 s | 16.1 s | 0% |
| elevenlabs: eleven_v4 | 3.15 s | 0.77 s | 16.1 s | 0% |

`eleven_v4_turbo` halves `eleven_v4`'s latency and stays twice as slow as `eleven_flash_v2_5`.
Both v4 models speak a sixth more slowly. The read-back separates nothing, so **the choice
between them is how the voice sounds**, judged by listening, and it costs under a second.

The Gemini speech models, the fallback, on four tutor answers read three times each:

| Candidate | Latency | Faster than real time |
|---|---:|---:|
| gemini: **gemini-3.8-flash-lite-tts** (fallback) | **3.47 s** | 2.8 x |
| gemini: gemini-3.8-flash-tts | 3.60 s | 2.3 x |
| gemini: gemini-3.1-flash-tts-preview (previous) | 6.29 s | 1.5 x |
| gemini: gemini-2.5-pro-preview-tts | 10.77 s | 1.0 x |

On the same protocol, ElevenLabs' v2.5 models were seven times faster than the best Gemini
model (0.46 s and 0.52 s against 3.47 s), and ElevenLabs gives a complete file at once, which a
download or a braille sheet needs. Gemini Live streams: first words after 1.4 s, but the
whole clip still takes as long as the speech.

**Gemini Live as the whole conversation** answers the pupil itself, so on its own it would skip
the guard. The live lab runs it only with its answer held until the guard has ruled; even then
it answers from its own model, not through the tutor ([decisions.md](./decisions.md)).

## Pictures

Measured 2026-10-07, on real turns asking for a fractions diagram, a 3-4-5 triangle, the
perimeter of a rectangle and the water cycle, in English and French.

- **Through the Gemini SDK, not the router.** The OpenAI compatibility endpoint answers an image
  model with `Unhandled generated data mime type: image/jpeg`, and its images route returns 404.
  So pictures are, with speech, the second place a provider SDK is called directly.
- **TEXT and IMAGE are both requested.** Asked for `["TEXT"]`, the model draws anyway; asked for
  `["IMAGE"]`, it returns a picture with no word. With both, the text answers the question.
- **Where a turn's time goes**, three timed runs: the guard 0.7 s, the tutor's call that writes
  the request and the waiting sentence about 6 s, the picture gate 0.8 s, the picture 15 to 18 s
  (33 to 35 s in two other runs), the answer 3 to 4 s. The whole turn: 26 to 31 s. The pupil
  hears that the picture is coming 7 to 9 s in, 10 to 12 s once the sentence is spoken in the lab.
- **Every label and value was right** in the pictures checked. A pre-release version of the model
  labelled each quarter of a pizza "2/4", so a picture is still worth a teacher's glance.

## What this also taught

- **A small labelled set flatters models**: four tied at 100% on 18 cases; 69 attacks separated
  them.
- **Close latencies are noise**: only gaps like 3.92 s against 0.8 s, or the tenfold ones in
  speech, survive between sessions.
- **Verbosity is latency**: the slowest candidates were slow because they wrote more.
- **Streaming changes the ranking**: on total time Gemini Live looks worse than batch speech; on
  the first word heard it is eight times better.
- **Check that two zipped lists have the same length**: one embedder scored 0/12 because a batch
  of 16 returned fewer vectors, and every later score compared the wrong pairs.
