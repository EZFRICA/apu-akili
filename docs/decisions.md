# Decisions, open questions and measured behaviour

The engineering record: what was decided and why, and what is still open. The numbers are in
[measurements.md](./measurements.md) and [models.md](./models.md), the attacks on the guard in
[security.md](./security.md). Tests and code comments point here, so a decision and the test that
pins it move together.

Akili is the education implementation of the Agent Processor Unit
(`github.com/EZFRICA/Agent-Processor-Unit`), with an L1 in-process cache, an L2 doubly linked
list persisted as JSON and an L3 local LanceDB: no L4, no Redis. It started as a port to one
vendor's models; every role now runs on the model that measured best for it.

## Open

- **Block cap.** The reference APU allows 12 active blocks (4 fixed, 8 dynamic); this one allows
  4 fixed and 5 dynamic. `MAX_ACTIVE_BLOCKS` exists in `apu/config.py` and is not wired. Pinned by
  `tests/test_block_cap.py`; change the test with the decision.
- **The memory write-back is on the critical path**, awaited before the answer returns. Running
  it in the background measured 34.6% less perceived latency, at the cost of a turn returning
  before its memory is written.
- **Scheduler.** `LocalScheduler` is inherited and never started (FIFO, priority ignored).
  `DeferredWriteScheduler`, with retries and dead letters, carries the escalation writes and the
  clustering jobs.
- **No page-in**: a block paged out to L3 does not come back into the DLL. Only the reference APU
  does that.
- **`delete_block_stitching`** calls `lance_driver.delete_local_block`, which does not exist.
  Inherited; pinned by a test.
- **Cloud registry.** Devices need Google credentials to download. Manifest `url` fields say
  `/courses/` while files sit at the bucket root; `manifest_generator.py` writes no embedding
  stamp; `prompt_exporter.py` writes where nothing reads; "Check for updates" refreshes prompts
  only.
- **Not carried over** from the reference: `scripts/migrate_embeddings.py`,
  `scripts/dedup_user_memory.py`, `scripts/bench_latency.py`. The benchmark harness behind
  [measurements.md](./measurements.md) measures turn and retrieval latency instead.
- **Authentication is a stub.** `X-Requester-Id` names the requester, with no password or token.
  Authorization from the registries is real. Signed tokens are required before any deployment.
- **Class policies are read once per session**; a change applies to new sessions.
- **The off-topic counter is per session**, so reconnecting restarts it. Persisting it per pupil
  would change what a school stores about a child.
- **No limit on message size.** A 47 000-character message was classified and answered.
- **`uncertain` still answers**, without tools and without counting: the softest path.
- **A cluster's `representative_text`** is its earliest event; a written summary is still to do.
- **Nobody is alerted to a welfare disclosure.** Routing it to a safeguarding lead is a school
  policy decision.
- **Other tools** (calculator, course search, chapter loader) are not implemented; they would
  plug in as tool calls like web search and the notebook.

## Decided

- **One model per role, chosen by measuring that role.** No model won everywhere: the best guard
  makes a bad search-query gate, and the best writer is slow at condensing. Re-measure when a
  model changes; two routing decisions have already reversed on new evidence.
- **Every exchange goes through the guard, whatever the modality.** Audio is transcribed first
  and the transcript is classified like typed text.
- **A search query is classified too.** A genuine lesson can carry an off-topic errand that the
  message classifier passes; failing the check means no search, never an unchecked one.
- **A disclosure of distress is its own verdict**, never counted, never stored. Before this, "I
  do not want to live any more" was refused, counted, and stored for a teacher
  ([security.md](./security.md)).
- **An escalation is recorded once per session**, when the count reaches the class threshold.
- **Greetings, thanks, questions about the tutor and notebook requests count as school use**, so
  a pupil saying hello is never counted off-topic.
- **Five interaction modes**: text to text, voice to voice, voice to text, text to voice,
  braille to braille.
- **One role per requester** in the assignment registry; guard sessions live in memory.
- **Streamlit stays, with an accessibility patch on top.** Its AppTest harness runs 22 interface
  tests headless in the same suite; the patch makes the axe-core audit clean
  ([accessibility.md](./accessibility.md)).
- **The embedder stays local**: retrieval must work on a disconnected device.
- **Gemini Live runs only in the live lab, behind the guard.** It answers the pupil itself, so
  `apu/ui/live/runner_gemini_live.py` holds its answer, audio and transcript, until the guard has
  ruled, and drops it on a refusal. It still answers from its own model, without the course, the
  APU memory or the write-back: a voice engine to compare, not the tutor.

## Tool calling

Tools are standard OpenAI tool calls through the one OpenAI-compatible client every provider
uses; the tutor model calls them natively ([models.md](./models.md)). On a tool-call turn
`message.content` is `None`, so the tool loop uses `call_main_model_message` and reads the whole
message rather than `call_main_model`, which returns only the content.

## Found and fixed, worth remembering

- **An empty final answer.** After two searches, the forced last round sometimes returned no
  content. The tutor retries once with "answer now from the results above", then falls back to a
  message recorded in `answer_problems`.
- **LaTeX in the interface.** The tutor writes maths as `\( … \)` and `\[ … \]`; Streamlit shows
  that raw, so the page converts it, and voice and braille ask for plain text.
- **The transcript is not in `response.text`.** A dedicated speech model returns an
  `audio_transcription` part and leaves the text empty; the reader takes that part first.
- **Console names are not API ids**: `gemini-3.1-flash-tts` is a 404. Only listing what a key can
  call settles it.
- **Speech can stop early.** One reading returned 22 s of audio for 90 s of text, so `synthesize`
  reads again once when the audio is under 60% of the length the text implies.
- **A new event loop per turn cost 0.5 s**: the guard's HTTP client recovered from a closed loop
  every turn. `apu.ui.common.run` keeps one loop alive.

## Clustering

Escalations are clustered per class with HDBSCAN on the local embedder. Requests on one theme
phrased differently reach only 0.26 to 0.60 cosine similarity and form **no cluster**; closely
phrased ones (0.70 to 0.93) cluster cleanly, but an isolated request next to them was absorbed
instead of labelled noise. A class whose events form a single group gets no cluster, which
`allow_single_cluster` would fix only by merging unrelated requests. Kept as is and pinned by a
test. **Open**: on real class traffic this needs a stronger embedder for this step or another
method, which is why the demo data uses closely phrased requests.

## The notebook

- Saves are recognised from natural phrasing ("just keep the rule for adding fractions") once the
  tool instructions name such phrasings.
- A spoken "summarise my notebook" works in the live lab, so a pupil with no screen can hear
  their notes and have them put into braille. It goes through the notebook service, not the
  tutor, which still never reads the notebook.
