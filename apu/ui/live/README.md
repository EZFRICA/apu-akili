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

The dashboard focuses on two production architectures engineered specifically for educational pair tutoring:

### 1. ElevenLabs STS (`eleven_english_sts_v2`)
- **Runner**: [`runner_elevenlabs.py`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/runner_elevenlabs.py)
- **Workflow**: Per-turn audio streaming with ElevenLabs Speech-to-Text transcription.
- **Pedagogy & Safeguards**: Once the turn boundary (`END_OF_TURN`) is signaled, the transcribed query passes through NeMo Guardrails and the Socratic agent graph before being synthesized into natural, expressive speech with ElevenLabs TTS.
- **Strengths**: Highest speech quality, robust voice modulation, and consistent turn pacing.

### 2. Gemini Transcribe (`gemini-3.5-transcribe-live`)
- **Runner**: [`runner_gemini_transcribe.py`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/runner_gemini_transcribe.py)
- **Workflow**: Real-time streaming Speech-to-Text using Gemini Live WebSocket (`response_modalities=["TEXT"]`).
- **Live User Feedback**: Streams interim and final user transcription tokens (`user_transcript`) to the browser so the student sees their words as they speak.
- **Pedagogy & Safeguards**: Routes the final recognized prompt into the full APU turn pipeline (NeMo Guardrails, MMU memory retrieval, Socratic agent reasoning, and TTS synthesis).
- **Strengths**: Minimal STT latency, instant visual feedback in prompter mode, and fallback to batch transcription if background noise occurs.

---

## Why Direct Audio-to-Audio Streaming Models (e.g., Gemini 3.8 Live) Do Not Fit This Use Case

Experiments were conducted with direct continuous audio-to-audio multimodal streaming models (`gemini-3.8-live` and `gemini-3.8-live-extended-thinking`). They were removed from the dashboard because raw continuous audio streaming is incompatible with APU's educational requirements:

1. **Mandatory Guardrail Verification (Turn Boundary)**:
   - In APU, student safety is paramount. Every student input must be validated by **NeMo Guardrails** to filter off-topic distractions and enforce pedagogical boundaries *before* any answer is generated.
   - Direct audio-in / audio-out models generate speech immediately upon receiving audio frames, bypassing pre-generation guardrail intervention.

2. **Curriculum Grounding and Agent Tools**:
   - The tutor must query the **MMU memory** (L1 working cache and L2 DLL curriculum database) and invoke tools like **`save_to_notebook`** when the student asks to record notes.
   - Raw multimodal audio streams do not seamlessly execute external tool chains or persist notes into the student's SQLite notebook.

3. **Turn Desynchronization & Silent Turns**:
   - Continuous bidirectional streaming sockets frequently desynchronize across multi-turn exchanges. Intermediate completion flags (`generation_complete` vs. `turn_complete`) cause queue blocking and silent second turns when the flow is paused for server-side evaluation.

**Conclusion**: The optimal architecture for APU is **Per-Turn STT + Socratic Agent Pipeline + TTS**, combining real-time transcription responsiveness with strict pedagogical safety and full memory persistence.

---

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

- [`server.py`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/server.py): FastAPI server, student registry API (`/api/students`), and WebSocket router (`/ws/{model_id}`).
- [`proxy.py`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/proxy.py): Uvicorn runner entry point on port 8765.
- [`pipeline.py`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/pipeline.py): Turn execution orchestration (guardrails, tutor, TTS, braille, WebSocket safe push).
- [`intents.py`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/intents.py): Regex matching and execution for voice intents (save, summary, braille).
- [`runner_elevenlabs.py`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/runner_elevenlabs.py): ElevenLabs STS per-turn streaming runner.
- [`runner_gemini_transcribe.py`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/runner_gemini_transcribe.py): Gemini Live real-time STT runner.
- [`static/`](file:///Users/mahuton/LocalDocs/2026/project/apu-akili/apu/ui/live/static): Modular frontend (HTML5, Web Audio API, mic visualizer, Lego components).
