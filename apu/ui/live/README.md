# The live voice lab

A FastAPI and websocket bench for speaking to the tutor, comparing three real-time voice engines
on one pipeline: speech in, the guard, the tutor, speech and braille out, and the notebook.

```bash
uv run python -m apu.ui.live.proxy
```

It starts at **http://localhost:8765**, on this machine only (`--host` opens it to a network,
and says what that means). It is the only server the voice front ends need:

| Address | What |
|---|---|
| `/` | this lab's own page: switch engines and compare them |
| `/presentation/` | the keynote stage ([its README](../presentation/README.md)) |
| `/shared/` | the websocket client and the microphone both pages run on |
| `/ws/{model_id}` | the websocket itself, where the tutor is reached |

`GEMINI_API_KEY` is required; `ELEVENLABS_API_KEY` for the ElevenLabs engine.

## A turn

Browser audio arrives as 16 kHz PCM. A **voice intent** (save to my notebook, summarise my notes,
give me that in braille) is classified by the guard and then run by `intents.py`, without the
tutor. Anything else goes through the full turn, `apu.ui.turn.run_turn`: the guard, the APU
memory, the tutor and its tools, then speech (ElevenLabs, or Gemini as fallback) and braille
(liblouis), from `pipeline.py`.

## The three engines

| Engine | Runner | How it works |
|---|---|---|
| ElevenLabs (`eleven_english_sts_v2`) | `runner_elevenlabs.py` | per-turn audio, ElevenLabs transcription, the full turn, ElevenLabs speech. The fastest speech measured: `eleven_v4_turbo` reads an answer in 1.68 s ([models.md](../../../docs/models.md)) |
| Gemini Transcribe (`gemini-3.5-transcribe-live`) | `runner_gemini_transcribe.py` | live transcription shown to the pupil as they speak, then the full turn. A second provider, with a batch transcription fallback when the stream yields nothing |
| Gemini Live (`gemini-3.8-live`) | `runner_gemini_live.py` | one socket, audio in and audio out, no separate speech calls. Its answer is **held until the guard has ruled**, and dropped on a refusal |

The first two are the default path. Gemini Live has the most natural voice of the three, which
is an opinion, since no read-back score separates them. Holding its answer costs it any speed
advantage: 10.4 s and 10.6 s a turn against 8.6 s. It does not call the tutor: it answers from
its own model, without the APU memory or the tools, and its notebook saves go through the voice
intents. Wiring the tools back in is possible; moving the guard into the model is not, since the
check deciding whether a pupil is answered must happen before the model speaks.

## What the Gemini Live runner had to get right

1. **The session went silent after the first answer.** `session.receive()` ends at each turn
   boundary, so one `async for` served one answer. An outer loop drives it once per turn, and the
   send and receive halves cancel each other if either loses the socket. Pinned in
   `tests/test_live.py` with a fake session that ends exactly as the real one does.
2. **The end of a turn is sent, not guessed.** `turn_complete` interrupts active generation, so
   using it as a turn marker silenced every answer after the first. Automatic voice detection is
   off; the browser's push-to-talk sends `activity_start` and `activity_end`.
3. **A missing transcription is not a bad question.** Gemini does not always transcribe the
   input, and with nothing to classify the guard refused good questions. The pupil's audio is
   kept and transcribed the ordinary way when none arrives.
4. **Nothing is heard before the guard has ruled.** That is why the output transcription is
   buffered rather than streamed: streaming it would show an answer the guard has not allowed.

`thinking_level` is not supported on `gemini-3.8-live`, so none is sent.

## What protects a pupil here

- **Every utterance is classified before anything acts on it**, inside `run_turn` for the tutor
  and by `pipeline.classify` before a voice intent runs. A guard with no verdict stops the turn.
- **Who may open a socket.** An `Origin` header is judged against `APU_LIVE_ALLOWED_ORIGINS`
  wherever it comes from. **No `Origin` at all is accepted only from this machine**, which is what
  curl and the test suite send; a script elsewhere on the network can no longer leave the header
  off to get in. With the loopback bind, reaching this socket from another machine takes both a
  deliberate `--host` and an allowed origin.
- **The pupil is resolved against the roster**, and the server issues the session id, so a
  client cannot rotate it to escape the off-topic count. This is not authentication: anyone who
  reaches the port can still pick any pupil on the roster.
- **The log records what happened, not what a child said.** Turn text is DEBUG only.
- **The notebook is bounded**, in what it holds and in how much of it may reach a model.

## Files

`server.py` is the FastAPI app (routes, the roster, origin checks), `proxy.py` its entry point,
`pipeline.py` runs a turn and pushes its results, `intents.py` the voice intents and the braille
layout, and the three `runner_*.py` files the engines above. `static/` is this lab's own page:
its look and its dashboard, while the socket, the microphone and the loudspeaker come from
`../shared/`, where both pages share one copy.
