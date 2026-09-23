# APU Live Voice Lab

Real-time multimodal voice and audio interface for the APU Akili tutor.

## Overview

The `apu/ui/live` directory provides an interactive voice lab powered by FastAPI and WebSockets, enabling students to interact with the tutor via speech, featuring real-time speech-to-text, speech synthesis (TTS), automatic Braille card generation, and student notebook integration.

## Architecture

```
Browser (PCM 16kHz Audio / Mic)
       │
       ▼ WebSocket `/ws/{model_id}`
FastAPI Server (`apu/ui/live/server.py`)
       │
       ├──► Voice Intent Detection (`intents.py`)
       │      • Save to notebook ("save to my notebook", "save in memory")
       │      • Notebook summary ("summarize my notes")
       │      • Braille translation ("format in braille")
       │
       └──► Pedagogical Pipeline (`pipeline.py`)
              • NeMo Guardrails (topical safety and curriculum filter)
              • Hierarchical MMU Memory (L1 RAM cache + L2 DLL syllabus)
              • Socratic Tutor Reasoning Engine (`apu.ui.turn.run_turn`)
              • Tool Execution (`save_to_notebook` SQLite persistence)
              • TTS Synthesis (ElevenLabs / Gemini) & Braille (liblouis)
```

## Supported Models on the Dashboard

The dashboard offers three runners. The first two are the production path; the third is the
direct audio-to-audio one, kept because its voice is the most natural of the three.

### 1. ElevenLabs STS (`eleven_english_sts_v2`)
- **Runner**: [`runner_elevenlabs.py`](./runner_elevenlabs.py)
- **Workflow**: Per-turn audio streaming with ElevenLabs Speech-to-Text transcription.
- **Pedagogy & Safeguards**: Once the turn boundary (`END_OF_TURN`) is signaled, the transcribed query passes through NeMo Guardrails and the Socratic agent graph before being synthesized into natural, expressive speech with ElevenLabs TTS.
- **Strengths**: the fastest speech of everything measured, 0.52 s to a complete reading
  against 3.47 s for the quickest Gemini model, and consistent turn pacing.

### 2. Gemini Transcribe (`gemini-3.5-transcribe-live`)
- **Runner**: [`runner_gemini_transcribe.py`](./runner_gemini_transcribe.py)
- **Workflow**: Real-time streaming Speech-to-Text using Gemini Live WebSocket (`response_modalities=["TEXT"]`).
- **Live User Feedback**: Streams interim and final user transcription tokens (`user_transcript`) to the browser so the student sees their words as they speak.
- **Pedagogy & Safeguards**: Routes the final recognized prompt into the full APU turn pipeline (NeMo Guardrails, MMU memory retrieval, Socratic agent reasoning, and TTS synthesis).
- **Strengths**: instant visual feedback in prompter mode, and a fallback to batch
  transcription when the stream yields nothing. On the measured set it keeps every number in
  a spoken French maths question, at 1.48 s against 1.04 s for the ElevenLabs transcriber
  (`docs/models.md`), so it trades a little latency for a second provider.

---

### 3. Gemini Live (`gemini-3.8-live`)
- **Runner**: [`runner_gemini_live.py`](./runner_gemini_live.py)
- **Workflow**: One bidirectional socket. Browser PCM 16 kHz in, model PCM 24 kHz plus an
  output transcription out, with no separate STT or TTS call.
- **Pedagogy & Safeguards**: The model answers on its own initiative, which is the whole
  difficulty. The answer is therefore **held server side**, audio and transcription both,
  until the guard has classified the transcript of what the pupil said. On a refusal the
  model's audio is discarded unplayed and the guard's own reply is spoken in its place. A
  guard that cannot reach a verdict, or a turn with no transcript at all, blocks the turn:
  the failure is closed, as everywhere else in APU.
- **Strengths**: a single connection instead of three calls, and the most natural voice of
  the three. That last one is a judgement, not a measurement: no read-back score separates
  these engines, so it is recorded as an opinion rather than dressed up as data.
- **Cost of the hold**: no latency advantage. Measured over three consecutive spoken
  turns: 10.4 s, 10.6 s, and 8.9 s for a refused one, against 8.6 s for the per-turn path.

---

## Four Things This Runner Had to Get Right

Direct audio-to-audio was shelved for a while. These are the reasons, and what each one
turned out to be.

1. **The session used to go silent after the first answer.**
   `session.receive()` in `google-genai` ends its iteration at a turn boundary, so a single
   `async for` over it serves one answer and then returns. The second question reached
   Gemini and its answer was never read. An outer loop drives the iterator once per turn,
   and the send and receive halves cancel each other, so neither is left awaiting a socket
   the other has already lost. `tests/test_live.py` pins this down with a fake session that
   ends its iteration exactly as the real one does.

2. **The turn boundary has to be sent, not guessed.**
   The end of a turn used to be marked with an empty `client_content` carrying
   `turn_complete=true`, and the session then answered the first question and ignored every
   one after it, the socket staying open and idle. The API documents why: `turn_complete`
   unconditionally interrupts active generation. Automatic voice activity detection is
   disabled and the browser's own push-to-talk boundary is sent instead, as explicit
   `activity_start` and `activity_end` markers.

3. **A missing transcription must not look like a bad question.**
   Gemini does not always return an input transcription. With nothing to classify, the
   guard refused perfectly good questions. The pupil's own audio is therefore kept for the
   turn and transcribed the ordinary way when no live transcription arrives.

4. **Nothing may be heard before the guard has ruled.**
   The hold described above is what makes this runner acceptable at all. It is the reason
   the output transcription is buffered rather than streamed token by token: streaming it
   would show the pupil, on screen, an answer the guard has not yet allowed.

**Remaining limitation, and it is this runner's, not the model's**: the runner does not
call the tutor graph, so it has neither the MMU memory nor the agent tools, and notebook
saves go through the voice intents in `intents.py` rather than `save_to_notebook`. The
model itself supports function calling, asynchronous by default, and search grounding, so
wiring the tools back in is work waiting to be done rather than a wall. What cannot be
moved into the model is the guard: a tool call is the model's own decision, and the check
that decides whether a pupil is answered at all has to happen before the model speaks.
Until that work is done, the per-turn runners keep the full pipeline, which is why they
remain the default.

**One API note**: `thinking_level` is not supported on `gemini-3.8-live`, so no thinking
configuration is sent.

---

## What protects a pupil here

- **Every utterance is classified before anything acts on it.** The tutor path classifies
  inside `run_turn`; a voice intent never reaches the tutor, so `pipeline.classify` does it
  before the intent runs. A guard that cannot reach a verdict stops the turn.
- **The socket is origin checked.** A websocket is not covered by the browser's same-origin
  policy, so a page the pupil visits could otherwise open one to this server. Set
  `APU_LIVE_ALLOWED_ORIGINS` (comma separated) to serve the lab from anywhere but localhost.
- **The pupil is resolved against the roster**, and the session identifier is issued by the
  server, so a client cannot rotate it to escape the guard's off-topic count. This is not
  authentication: identity is a stub across the whole project, and anyone who can reach this
  port can still pick any pupil on the roster.
- **The log carries what happened, not what a child wrote.** Turn text is DEBUG only.
- **The notebook is bounded**, both in what it holds and in how much of it may be sent to a
  model, through `apu/notebook/service.py`.

## Quickstart

### 1. Environment Variables

Ensure your root `.env` file contains your API keys:
```bash
GEMINI_API_KEY=your_gemini_key
ELEVENLABS_API_KEY=your_elevenlabs_key  # required for ElevenLabs STS runner
```

### 2. Launch the Live Server

Start the live server with `uv`:
```bash
uv run python -m apu.ui.live.proxy
```

The server starts by default at **http://localhost:8765**. Open this URL in your browser to access the voice interface.

## Key Files

- [`server.py`](./server.py): FastAPI server, student registry API (`/api/students`), and WebSocket router (`/ws/{model_id}`).
- [`proxy.py`](./proxy.py): Uvicorn runner entry point on port 8765.
- [`pipeline.py`](./pipeline.py): Turn execution orchestration (guardrails, tutor, TTS, braille, WebSocket safe push).
- [`intents.py`](./intents.py): Regex matching and execution for voice intents (save, summary, braille).
- [`runner_elevenlabs.py`](./runner_elevenlabs.py): ElevenLabs STS per-turn streaming runner.
- [`runner_gemini_transcribe.py`](./runner_gemini_transcribe.py): Gemini Live real-time STT runner.
- [`runner_gemini_live.py`](./runner_gemini_live.py): direct audio-to-audio runner, with the answer held until the guard has ruled.
- [`static/`](./static): Modular frontend (HTML5, Web Audio API, mic visualizer, Lego components).
