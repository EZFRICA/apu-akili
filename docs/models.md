# Choosing a model for each role

The pipeline has seven places where a model is called, and they ask for different things: a
classifier that must be right about a child in distress, a tutor that must call tools, an
embedder that must run on a disconnected device, a voice that must not make a pupil wait.
This is the measured comparison behind the choice for each one.

Everything here comes from a call that was actually made, on 2026-09-19, from a laptop in
Europe, with the four keys the project has. Nothing is taken from a model card or a
leaderboard. The harness that produced these numbers needs several provider keys and costs money to run, so it is not part of this repository; what it found is.

## What each provider actually offers, verified

| Provider | Verified by calling it | Not available |
|---|---|---|
| **Nebius Token Factory** | 24 models listed and callable: Nemotron 3 (super, nano, ultra, 3.5 lightning), Qwen 3/3.5, DeepSeek V4, GLM 5.x, Kimi, gpt-oss, gemma-3-27b, and one embedder (Qwen3-Embedding-8B) | no speech, no images |
| **Gemini** | text models up to `gemini-3.8-flash` (3.6, 3.7, 3.8 and the `gemini-flash-latest` alias all answer), `gemini-3.5-transcribe` (speech to text), the speech models `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, `gemini-3.1-flash-tts-preview` and the two 2.5 previews, plus two the API marks confidential and which are therefore not named here, `gemini-embedding-001` and `-2`, the Nano Banana image models | the console's display names are not API ids: `gemini-3.1-flash-tts` returns 404, only the `-preview` id exists; the omni models (`gemini-omni-1.1-flash`, `gemini-omni-flash-preview`) refuse `generateContent` with "This model only supports Interactions API" |
| **NVIDIA NIM** | 82 models are listed, but this key can call only some: `nemotron-3-super-120b-a12b`, `nemotron-3-ultra-550b-a55b`, `nemotron-3.5-lightning-30b-a3b`, `gpt-oss-20b`, `gemma-4-31b-it`, and the embedder `nemotron-3-embed-1b` | `llama-3.1-nemotron-70b-instruct`, `nemotron-nano-3-30b-a3b`, `llama-3.2-nv-embedqa-1b-v1`, `nv-embedqa-mistral-7b-v2`, `arctic-embed-l` all answer 404; `llama-3.1-nemoguard-8b-topic-control` answers 500 on every call; kimi, glm and the safety guards time out |
| **ElevenLabs** | speech synthesis with the account's own voices (`eleven_flash_v2_5`, `eleven_turbo_v2_5`, `eleven_multilingual_v2`), streaming and raw PCM included, and three transcribers: `scribe_v1`, `scribe_v1_experimental`, `scribe_v2` | the key has no `models_read` permission, so the catalogue cannot be listed; library voices are refused on a free plan (HTTP 402); `scribe_v2_realtime` is refused by the file endpoint, it belongs to the websocket API |
| **Gemini Live** (websocket) | `gemini-3.8-live` and `gemini-3.1-flash-live-preview` both stream speech out, `gemini-3.8-live` transcribes speech in, and `gemini-3.5-transcribe-live` transcribes a recorded clip in 2.8 s through the shipped runner | `gemini-3.5-transcribe-live` was written up here as aborting with code 1008 whatever was tried; that was the configuration, not the model, and it is corrected below. Live transcription needs explicit activity markers, since automatic voice detection never closed the turn on a recorded clip (60 s timeout) |

The NVIDIA finding matters for the architecture: the models that survive are the same
Nemotrons that Nebius serves, and every one of them was **slower through NIM** in these runs,
with timeouts on `nemotron-3.5-lightning` at 60 to 180 s. NIM is kept as a second source for
the same weights, not as a faster one.

## Role: the topical guard

Classifies each pupil message as school use, off topic, or a welfare disclosure. Measured on
18 labelled cases (French and English, injections, school pretexts, four disclosures), then
the best candidates were re-run against the **full 69-attack corpus** from
[security.md](./security.md).

| Candidate | 18-case accuracy | Welfare | Median | Output tokens |
|---|---:|---:|---:|---:|
| nebius: nemotron-3-super-120b | 1.00 | 4/4 | 1.65 s | 118 |
| nebius: gemma-3-27b-it | 1.00 | 4/4 | **0.38 s** | 4 |
| gemini: gemini-3.5-flash-lite | 1.00 | 4/4 | **0.67 s** | 3 |
| gemini: gemini-3.1-flash-lite | 1.00 | 4/4 | 0.69 s | 3 |
| gemini: gemini-flash-lite-latest | 1.00 | 4/4 | 0.77 s | 3 |
| gemini: gemini-flash-latest | 1.00 | 4/4 | 1.16 s | 3 |
| gemini: gemini-3.8-flash | 1.00 | 4/4 | 1.27 s | 3 |
| gemini: gemini-3.7-flash | 1.00 | 4/4 | 1.33 s | 2 |
| gemini: gemini-3.6-flash | 1.00 | 4/4 | 2.08 s | 3 |
| gemini: gemini-3.5-flash | 1.00 | 4/4 | 2.40 s | 2 |
| nebius: Nemotron-3-Nano-30B | 0.89 | 4/4 | 1.26 s | 142 |
| nvidia: nemotron-3.5-lightning | failed | | | timeouts |
| nvidia: nemoguard-8b-topic-control | failed | | | HTTP 500 on every call |
| gemini: gemini-omni-1.1-flash | failed | | | needs the Interactions API |

On 18 cases four candidates tie at 100%. The 69-attack corpus separates them:

| Candidate | Attacks held | Median | What it missed |
|---|---:|---:|---|
| gemini: gemini-3.5-flash-lite | **69/69** | **0.66 s**, 0.62 s on a second pass | nothing, twice |
| gemini: gemini-flash-lite-latest | 69/69 | 0.74 s | nothing |
| nebius: nemotron-3-super-120b (current) | 69/69 | 1.58 s | nothing |
| gemini: gemini-3.1-flash-lite | 68/69 | 0.60 s | the lesson carrying an off-topic errand, which the query gate stops anyway |
| gemini: gemini-3.8-flash | 67/69 | 1.26 s | called a sad pupil's request off-topic rather than welfare, and over-blocked a question about the filter |
| gemini: gemini-3.7-flash | 67/69 | 1.22 s | the same two |
| nebius: gemma-3-27b-it | 65/69 | 0.38 s | a ROT13 payload it did not decode, and two prompt-exfiltration cases |

**`gemini-3.5-flash-lite` is the best guard measured**: the same 69/69 as Nemotron Super, held
twice, at 0.66 s and 0.62 s against 1.58 s. `gemini-flash-lite-latest` (the moving alias)
matches it, a little slower.

**Size and version number do not predict this.** `gemini-3.8-flash`, the newest and largest
Flash tested, is twice as slow as the Lite models and gets two more cases wrong, one of which
matters: it treats "I am very sad and only this would cheer me up" as misbehaviour instead of a
pupil saying they are unhappy. The Lite line beats the full Flash line, and inside the Lite
line the newer 3.5 beats 3.1 here, while losing to it on the query gate below.

**Keep Nemotron Super, or take Gemini Flash Lite for 1 s less per turn.** Gemma is twice as
fast again and should not be used here: it fails exactly the obfuscation case that a curious
pupil will find. This is also why the small set was not enough to decide: gemma scored 100%
on it.

## Role: the search-query gate

Classifies the query the tutor wants to send. Ten labelled queries.

| Candidate | Accuracy | Median | Output tokens |
|---|---:|---:|---:|
| gemini: gemini-3.1-flash-lite | **1.00** | **0.73 s** | 8 |
| gemini: gemini-3.5-flash-lite | 0.90 | 0.62 s | 10 |
| gemini: gemini-flash-lite-latest | 0.90 | 0.72 s | 10 |
| nebius: nemotron-3-super-120b | 1.00 | 1.04 s | 77 |
| nebius: Nemotron-3-Nano-30B (current) | 1.00 | 1.15 s | 75 |
| nebius: gemma-3-27b-it | 0.90 | 0.41 s | 10 |
| nvidia: nemotron-3.5-lightning | 0.30 | 39 s | 7 timeouts |

**`gemini-3.1-flash-lite`**: same accuracy as the current Nano for a third of the latency, and
it answers in 8 tokens instead of 75.

The reversal is worth noting: `gemini-3.5-flash-lite`, the best guard of all the candidates,
drops to 9/10 here by blocking "offside rule football explanation", a legitimate PE query, and
so does the `latest` alias. Gemma misses the same one. Being stricter is what makes a good
guard and a bad query gate, so the two roles do not get the same model.

## Role: the memory write-back

Turns one exchange into JSON. Three runs each; the exchange names the pupil, so keeping the
name is part of the score.

| Candidate | Valid JSON | Kept the name | Median | Output tokens |
|---|---:|---:|---:|---:|
| gemini: gemini-3.5-flash-lite | 3/3 | 3/3 | **0.77 s** | 68 |
| gemini: gemini-3.1-flash-lite | 3/3 | 3/3 | 0.80 s, 1.42 s in an earlier session | 55 |
| nebius: gemma-3-27b-it | 3/3 | 3/3 | 0.94 s | 69 |
| nebius: Qwen3-30B-A3B | 3/3 | 3/3 | 1.72 s | 50 |
| nebius: Nemotron-3-Nano-30B (current) | 3/3 | 3/3 | 3.92 s | 383 |
| nvidia: nemotron-3.5-lightning | 1/3 | 1/3 | 54 s | 2 timeouts |

**Any of the three**, four to five times faster than the current Nano for the same result;
0.77 s, 0.80 s and 0.94 s are one session's medians and the gaps between them are within the
run-to-run variation seen on this network (the same 3.1 Lite measured 1.42 s in an earlier
session). What is far outside that variation is Nano, which spends
383 tokens where the others spend 55 to 69: same verbosity problem already measured on the notebook's
key points ([measurements.md](./measurements.md)).

## Role: the tutor

Answers the pupil. Three cases: an English question, a French question that must be answered
in French, and a braille turn whose answer must be plain text. **Native tool calling is a
hard requirement**: web search and the notebook are tool calls.

| Candidate | Tool calls | Checks | Median | Output tokens | Tokens/s |
|---|---|---:|---:|---:|---:|
| nebius: gpt-oss-120b | yes | 5/5 | **2.03 s** | 471 | **232** |
| nebius: nemotron-3-super-120b (current) | yes | 5/5 | 2.91 s | 432 | 148 |
| gemini: gemini-3.7-flash | yes | 5/5 | 3.08 s | 254 | 82 |
| gemini: gemini-3.8-flash | yes | 5/5 | 3.27 s | 258 | 79 |
| gemini: gemini-3.5-flash | yes | 5/5 | 4.46 s | 283 | 63 |
| gemini: gemini-3.1-pro-preview | yes | 5/5 | 8.47 s | **205** | 24 |
| nebius: Qwen3.5-397B-A17B | yes | 5/5 | 8.26 s | 1305 | 158 |
| nvidia: nemotron-3-ultra-550b | yes | 5/5 | 10.05 s | 256 | 26 |
| nvidia: nemotron-3.5-lightning | yes | 3/3 | 109 s | 932 | timeouts |
| nebius: gemma-3-27b-it | **no** | | 8.6 s to refuse | | |

Every candidate that answers passes the mechanical checks, so this table ranks speed and
verbosity, not teaching quality, which these checks cannot measure. What it does settle:
**gemma is disqualified for this role** because it never emits a tool call, and Qwen3.5 writes
three times more than the others, which the spoken channel pays for directly.

## Role: retrieval embeddings

Twelve questions, French and English, each with the course chapter it should retrieve, over
the 16 chapters this repository ships. Harder than production, which also filters by class
and subject: every miss below is a fractions chapter from the wrong grade.

| Candidate | Top-1 | Dim | Margin | Per query | All 16 chapters |
|---|---:|---:|---:|---:|---:|
| nvidia: nemotron-3-embed-1b | **1.00** | 2048 | 0.20 | 196 ms | 1.1 s |
| nebius: Qwen3-Embedding-8B | 0.92 | 4096 | 0.17 | 314 ms | 3.4 s |
| local: MiniLM-L12-v2 (current) | 0.83 | 384 | 0.18 | **4 ms** | 2.0 s |
| gemini: gemini-embedding-2 | 0.83 | 3072 | 0.08 | 482 ms | 12.1 s |
| gemini: gemini-embedding-001 | 0.83 | 3072 | 0.08 | 390 ms | 6.8 s |

**Keep the local embedder.** It is 50 to 100 times faster because it involves no network, and
it must keep working on a disconnected device, which is the point of the architecture. The
gap is two near-misses between two fractions chapters of different grades, which the
class filter removes in production. NVIDIA's embedder is the one to use if retrieval ever
moves online, and it also has the widest margin between the right chapter and the next.

## Role: speech to text

Ten clips, half in French, spoken by two different engines so no transcriber is graded only
on audio from its own provider. The clips are cached on disk, because re-synthesising them
moved one model's score by three points, more than the models differ from each other.

| Candidate | Mean WER | Worst clip | Median |
|---|---:|---:|---:|
| gemini: gemini-3.8-flash | **6.7%** | 14% | 1.67 s |
| gemini: gemini-3.7-flash | 6.7% | 14% | 1.69 s |
| gemini: gemini-3.5-flash | 6.7% | 14% | 1.79 s |
| gemini: gemini-3.6-flash | 7.7% | 29% | 2.29 s |
| elevenlabs: scribe_v2 | 7.7% | 14% | 1.04 s |
| elevenlabs: scribe_v1 | 7.7% | 14% | 1.04 s |
| elevenlabs: scribe_v1_experimental | 7.7% | 14% | **1.02 s** |
| gemini: gemini-3.5-transcribe (current) | 15.3% | 71% | 1.50 s |
| gemini-live: gemini-3.8-live | 18.1% | 71% | 5.51 s |

The three ElevenLabs transcribers are indistinguishable from each other on this set, and one
point behind Gemini Flash for 40% less latency. **Either is a clear improvement on the current
model.**

### Do the numbers survive?

Word error rate treats every word alike, and for a maths tutor the numbers are the payload. Six
French questions carrying ten numbers, spoken by `eleven_flash_v2_5`, then transcribed:

| Candidate | Numbers kept | Median |
|---|---:|---:|
| elevenlabs: scribe_v1 | **10/10** | **1.04 s** |
| gemini: gemini-3.8-flash | 10/10 | 2.43 s |
| gemini: gemini-3.5-transcribe | 10/10 | 1.48 s |
| elevenlabs: scribe_v2 | 9/10 | 1.04 s |

Every candidate keeps the numbers, in figures or in words, except `scribe_v2` on one clip, where
it produced the hallucination discussed above. **This is what settles the role**: `scribe_v1` is
as accurate as the Gemini models on what matters and more than twice as fast, and it is the
model to use rather than `scribe_v2`.

The 71% worst clip needs reading before it is believed: for "Combien font un quart plus un
sixieme ?" both Gemini transcribers wrote **"Combien font 1/4 + 1/6 ?"**. That is a 71% word
error rate and a correct transcription, because they normalise spoken numbers into figures.
Their other errors are real. ElevenLabs makes the opposite kind of mistake on the same clip,
hearing "un corps" or "encore" for "un quart", which is a real error.

**A correction: `gemini-3.5-transcribe-live` does work.** It is recorded above as aborting
with code 1008 under every configuration tried. It does not: driven with explicit
`activity_start` and `activity_end` markers, with automatic voice activity detection
disabled, it returned `"What is one half plus one quarter?"` for a synthesised clip in
**2.8 s**, through `apu/ui/live/runner_gemini_transcribe.py` and the websocket the lab
serves. The earlier finding was about how the session was driven, not about the model, and
the same mistake silenced `gemini-3.8-live` for a while (see `apu/ui/live/README.md`).

**Gemini 3.8 Live is not a transcriber.** It works, with explicit activity markers, but it is
a dialogue model: 5.5 s per clip and the worst accuracy of the set, because it is listening in
order to reply rather than to transcribe.

## Role: text to speech

The same 230-character answer, synthesised twice per engine, then transcribed back with
`scribe_v1` to check nothing was dropped. **Two timings matter and they are not the same**:
the whole answer, and the first audio the pupil hears, which is what streaming changes.

| Candidate | Total | First audio | Audio produced | Read-back WER |
|---|---:|---:|---:|---:|
| elevenlabs: eleven_flash_v2_5 | **0.87 s** | **0.52 s** | 13.9 s | 0% |
| elevenlabs: eleven_turbo_v2_5 | 0.97 s | 0.62 s | 14.0 s | 0% |
| elevenlabs: eleven_multilingual_v2 | 2.00 s | 1.66 s | 14.3 s | 0% |
| gemini-live: gemini-3.8-live | 16.23 s | 1.38 s | 14.7 s | 0% |
| gemini-live: gemini-3.1-flash-live-preview | 16.30 s | 1.39 s | 14.8 s | 0% |
| gemini: gemini-2.5-flash-preview-tts | 9.89 s | 9.89 s | 15.3 s | 50%, see the correction below |
| gemini: gemini-3.1-flash-tts-preview (current) | 11.55 s | 11.55 s | 16.1 s | 0% |

### The Gemini speech models, measured again a generation later

The table above was taken when `gemini-3.1-flash-tts-preview` was the only Gemini speech model
this account could reach. Seven exist now, and all nine candidates were put through the same
protocol: four tutor answers in English and French, the fractions and numbers a speech model
gets wrong, three readings each, every clip read back by `scribe_v2` and scored against the
text that was sent.

Two of the candidates are marked `[Confidential]` by the API, and their measurements appear
below without their names. An early access catalogue belongs to whoever granted the access,
and a model identifier is part of it.

| Candidate | Latency | Audio produced | Faster than real time | Failures |
|---|---:|---:|---:|---:|
| elevenlabs: eleven_turbo_v2_5 | **0.46 s** | 7.5 s | 16.3 x | 0 |
| elevenlabs: eleven_flash_v2_5 | 0.52 s | 7.3 s | 14.0 x | 0 |
| gemini: an unreleased model, not named here | 3.34 s | 9.4 s | 2.8 x | 0 |
| gemini: **gemini-3.8-flash-lite-tts** (current Gemini fallback) | 3.47 s | 9.6 s | 2.8 x | 0 |
| gemini: gemini-3.8-flash-tts | 3.60 s | 8.4 s | 2.3 x | 0 |
| gemini: an unreleased model, not named here | 3.90 s | 8.9 s | 2.3 x | 0 |
| gemini: gemini-3.1-flash-tts-preview (the previous default) | 6.29 s | 9.7 s | 1.5 x | 0 |
| gemini: gemini-2.5-flash-preview-tts | 6.92 s | 8.9 s | 1.3 x | 0 |
| gemini: gemini-2.5-pro-preview-tts | 10.77 s | 11.1 s | 1.0 x | 0 |

**A caveat on speech in.** The code loads `scribe_v2`, while the measurement below chose
`scribe_v1`: `scribe_v2` dropped a number on one clip of the maths set, and a tutor that
mishears "un quart" is worse than a slower one. The two are within 0.02 s of each other, so
the choice costs nothing either way. This is a decision to make deliberately rather than by
drift, and `APU_STT_MODEL` sets it.

**The read-back separates nothing here, and saying otherwise would be dishonest.** All nine
came back at the same error rate, to the third decimal, and that constant is a French
reference text written without accents which the transcriber restores accented. On these
texts every candidate is intelligible; what the measurement separates is latency.

Two consequences. `gemini-3.8-flash-lite-tts` replaces `gemini-3.1-flash-tts-preview` as the
Gemini model this project ships, because it reads the same answer in **3.47 s instead of
6.29 s**. And ElevenLabs stays the default, seven times faster than the best Gemini
candidate, with the Gemini path kept as the fallback that removes the dependency on a second
provider. What no automatic measurement settles is how natural a voice sounds, which is a
product judgement and is recorded as such.

**The Live API fixes most of the problem, and ElevenLabs fixes all of it.** Gemini Live streams
at real time, so the pupil hears the first words after 1.4 s instead of waiting 11.5 s, even
though the whole clip still takes as long as the speech itself. ElevenLabs produces the entire
file in under a second, so it is both the fastest to start and the only one that gives a
complete file immediately, which is what a download or a braille sheet needs.

**A correction to an earlier claim in this file.** One run of
`gemini-2.5-flash-preview-tts` read back as "[outro jingle]", and it was written up here as a
synthesis failure. That attribution was wrong, or at least unproven: the string appeared twice
in this work, both times reported by an ElevenLabs scribe, and the second time
**three other transcribers read the same clip correctly**, which proves the audio was fine and
the transcriber hallucinated. Four fresh syntheses from both engines, each read by three
transcribers, produced no jingle at all. What is established: the artifact is intermittent, it
has only ever come out of a scribe model, and one occurrence is demonstrably a transcription
hallucination. Whether the first one was too cannot be settled, since that clip is gone.

In French, read back with `gemini-3.5-flash`:

| Candidate | Time | Read-back WER (French) |
|---|---:|---:|
| elevenlabs: eleven_flash_v2_5 | 1.1 s | **11%** |
| elevenlabs: eleven_turbo_v2_5 | 1.0 s | 11% |
| elevenlabs: eleven_multilingual_v2 | 2.0 s | 21% |
| gemini: gemini-3.1-flash-tts-preview | 11.6 s | 21% |

(The reference text is written without accents, so every engine is penalised equally; the
comparison holds, the absolute figures overstate the errors.)

A spoken turn was measured at 43.9 s end to end, of which 34.8 s was Gemini reading the answer
([measurements.md](./measurements.md)). With ElevenLabs that phase becomes about 3 s.

### What about Gemini Live as the whole conversation?

Live is a speech-to-speech dialogue model, and using it that way would put it in the tutor's
place: it would hear the pupil and answer directly, with no topical guard, no class policy, no
off-topic counter and no escalation. That is refused, and it is the same reason as in
[security.md](./security.md). What the measurements add is that Live is still **usable as a
component**: as a pure synthesiser, driven with text the tutor already wrote, it streams and
respects the rule that every exchange is classified first. It is simply beaten by ElevenLabs
on every number here.

## What is configured now

These were applied on 2026-09-19 and are what the code ships with. `apu/inference/llm.py`
routes each text role to its provider; the speech roles are in `apu/modality/voice.py`; the
guard's model is named twice, in `apu/config.py` and in `apu/guardrails/config/config.yml`,
and a test pins them together.

| Role | Model | Measured after the change |
|---|---|---|
| Tutor answer | `gemini:gemini-3.8-flash` | a text turn end to end: **5.0 s**, against 7.4 s before |
| Topical guard | `gemini:gemini-3.5-flash-lite` | the 69-attack corpus through the real rail: **69/69 held**, at 0.70 s median then and 0.79 to 0.97 s since the prompt gained the preceding exchange, against 1.58 s |
| Memory write-back | `gemini:gemini-3.5-flash-lite` | 0.94 s, against 1.74 s |
| Search-query gate | `gemini:gemini-3.1-flash-lite` | unchanged accuracy, a third of the latency |
| Notebook key points and revision sheet | `gemini:gemini-3.5-flash-lite` | **1.0 s each**, against 6.7 s and 3.5 s on the tutor model |
| Speech out | `elevenlabs:eleven_flash_v2_5` | a spoken turn end to end: **8.6 s**, against 43.9 s |
| Speech in | `elevenlabs:scribe_v2` | 1.04 s. See the caveat below: the measurement preferred `scribe_v1` |
| Speech out, Gemini fallback | `gemini:gemini-3.8-flash-lite-tts` | 3.47 s a reading, against 6.29 s for the previous default |
| Retrieval embeddings | local MiniLM (ONNX) | 8 ms per query, unchanged and still offline |

**The notebook moved twice, and that is the point.** Its two calls were moved off the small
model in an earlier session, because the small model then was a verbose reasoner that spent
1700 tokens to return 140 characters. With the small model that measurement chose, the
picture reverses: 0.81 s against 6.89 s for the key points. A routing decision is only valid
for the models it was measured on.

### The comparison that led here

| Role | Previously | Chosen | Why, measured |
|---|---|---|---|
| tutor | nemotron-3-super-120b | gemini-3.8-flash | 258 tokens against 471 for gpt-oss-120b, which the spoken channel pays for directly; all candidates call tools and pass every check |
| guard | nemotron-3-super-120b | **gemini-3.5-flash-lite** | the same 69/69, held twice, at 0.66 s against 1.58 s; the larger 3.8 Flash is worse on both counts |
| query gate | Nemotron-3-Nano | gemini-3.1-flash-lite (**not** 3.5 Lite) | same 10/10, 0.73 s against 1.15 s, 8 tokens against 75; 3.5 Lite blocks a legitimate PE query |
| memory write-back | Nemotron-3-Nano | gemini-3.5-flash-lite or gemma-3-27b-it | same result, 0.77 to 0.94 s against 3.92 s |
| notebook key points | nemotron-3-super-120b | keep | already moved off Nano after measurement, 11.6 s to 3.5 s |
| embeddings | local MiniLM | keep | 4 ms and offline; the online alternatives are 50x slower for 2 chapters of accuracy on a set production filters anyway |
| speech to text | gemini-3.5-transcribe | **scribe_v1** | 10/10 numbers kept against 10/10 for Gemini Flash, at 1.04 s against 2.43 s; and not `scribe_v2`, which hallucinated on one clip |
| speech out | gemini-3.1-flash-tts-preview | **eleven_flash_v2_5** | first audio in 0.52 s against 11.55 s, whole file in 0.87 s, half the French error rate |
| speech out, fallback | | gemini-3.8-live | if a second provider is wanted: streams, so first audio in 1.38 s |
| illustrations | none yet | gemini-3.1-flash-lite-image (Nano Banana 2 Lite) | only provider with image generation among the four |

## What this exercise also found

- **A silent bug in the harness itself.** `gemini-embedding-2` scored 0/12 until the check
  that the number of vectors matches the number of texts was added: batching 16 documents
  returned fewer embeddings, and every score after that compared the wrong pairs. Measured on
  pairs alone the model is fine (0.86 related against 0.50 unrelated). Any evaluation that
  zips two lists together needs that check.
- **A small labelled set flatters models.** Four candidates tied at 100% on 18 guard cases;
  the 69-attack corpus put four attacks between them.
- **Model names in a console are not API ids**, on Gemini and on NVIDIA alike. Only a call
  settles it.
- **Neither size nor version number predicts the winner of a narrow job.** The best guard
  measured is a Lite model, `gemini-3.5-flash-lite` (69/69 at 0.66 s), ahead of the larger
  `gemini-3.8-flash` (67/69 at 1.26 s) and of a 120B Nemotron (69/69 at 1.58 s). Yet that same
  Lite model is the *worst* of the Gemini candidates on the query gate, because the strictness
  that makes it a good guard makes it block a legitimate PE query. Roles this narrow have to be
  measured one by one.
- **Close latencies are noise.** Three candidates inside 0.77 to 0.94 s on the write-back are
  tied, and one of them measured 1.42 s in an earlier session on the same network. Only gaps
  like Nano's 3.92 s, or the ten-fold ones in speech, survive between sessions.
- **Streaming changes the ranking.** Judged on total time, Gemini Live looks worse than the
  batch TTS it replaces (16.2 s against 11.5 s). Judged on when the pupil hears the first
  word, it is eight times better. A single "latency" column would have hidden that.
- **Verbosity is latency.** The slowest candidates in three roles were slow because they wrote
  more, not because their provider was slower: Nano spends 383 tokens on a JSON extraction
  that gemma does in 69.
