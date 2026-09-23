# APU Akili

A school tutor built on the Agent Processor Unit: a tiered, persistent memory architecture for LLM agents, with a topical guard in front of every exchange, running on whichever model measured best for each role.

## What this is

This repository is Akili, the education implementation of the Agent Processor Unit (APU): a memory hierarchy for AI agents (L1 in-process cache, L2 a doubly linked list persisted as JSON, L3 a local LanceDB vector store) with a BMJ (Bidirectional Metadata Jump) routing algorithm, wrapped in what a school actually needs: a topical guard on every exchange, escalations for the teacher, a pupil's notebook, and text, voice and braille channels.

Each model call is routed to its own provider and model, chosen by measuring the candidates in that exact role rather than by reputation ([docs/models.md](./docs/models.md)).

See [docs/decisions.md](./docs/decisions.md) for the decisions behind it, what is still open, and what was measured against the live models.

Four things live in this repository, and only the first is the product:

| | What it is |
|---|---|
| **The tutor** | `apu/`, the memory hierarchy, the guard, the notebook and the modalities, with a Streamlit interface for the pupil, the teacher and the demo. |
| **The live voice lab** | `apu/ui/live/`, a FastAPI and WebSocket bench for comparing real-time voice runners on the same pipeline. A test bench, not a product surface. |
| **The chat interface** | `apu/ui/chainlit_app.py`, a chat-first front end over the same turn. |
| **Pocket Akili** | `apu/ui/hardware/`, a specification and 3D viewer for a tactile handheld companion. A design study, with no firmware behind it. |

The interfaces are deliberately several: they are aimed at different people, and a pupil picks the one that suits them. What they share is `apu/ui/turn.py`, so the rules that matter cannot drift between them.

## Why

The architecture targets agents that need to run useful workloads on constrained hardware and inconsistent connectivity, the kind of machine class and budget you find in a typical West African classroom or field deployment, not a high-end workstation. Two design choices follow from that constraint:

- The embedding model stays local (`paraphrase-multilingual-MiniLM-L12-v2` via fastembed/ONNX) rather than calling a remote embedding API, since it is the component on the hot path for every retrieval. It is swappable: pick a smaller or larger embedder depending on the target device.
- The answer call and the background memory-extraction call go to different models, so the always-on agent stays responsive without burning through inference budget on every turn.

## How

```
User turn
   │
   ▼
Planner node (LangGraph) ──► MMU routes query across L1 → L2 → L3 → L4
   │                                     │
   ▼                                     ▼
Main answer call                 Local embedder (fastembed/ONNX)
(the tutor model, with tools)    for retrieval and block matching
   │
   ▼
Answer returned to user
   │
   ▼ (background, off the critical path)
Extraction call (the small write-back model)
   │
   ▼
New / updated memory blocks written to L2, paged to L3 on eviction
```

## Model routing

Each role was measured against candidates from four providers in that exact role; the numbers
and the runners-up are in [docs/models.md](./docs/models.md).

| Role | Model | Why this one |
|---|---|---|
| Tutor answer | `gemini-3.8-flash` | calls tools natively, and writes half as many tokens as the faster candidate, which the spoken channel pays for |
| Topical guard | `gemini-3.5-flash-lite` | holds all 69 attacks of the red team corpus, twice, at 0.66 s against 1.58 s for a 120B model |
| Memory write-back | `gemini-3.5-flash-lite` | same result as the previous model at a fifth of the latency |
| Search-query gate | `gemini-3.1-flash-lite` | 10/10, and unlike the guard's model it does not block legitimate PE queries |
| Speech out | `eleven_flash_v2_5` | first audio in 0.52 s against 11.55 s, and half the French error rate |
| Speech in | `scribe_v2` | 1.04 s. The measurement preferred `scribe_v1`, which kept every number in a spoken French maths question: see [docs/models.md](./docs/models.md) |
| Retrieval embeddings | local MiniLM (ONNX) | 4 ms per query and works with no network, which is the point of the architecture |

Every text role goes through one OpenAI-compatible client per provider, so moving a role is a
setting, not a code change. See `apu/inference/llm.py`.

## Quickstart

Every command runs through [uv](https://docs.astral.sh/uv/), from the repository root. There is no virtual environment to create or activate by hand: `uv run` uses the project's `.venv/` automatically.

### 1. Prerequisites

- **uv**. Install it with one of:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  ```bash
  brew install uv
  ```
  uv downloads Python 3.13 by itself if it is not already on the machine.
- **A Gemini API key**, from https://aistudio.google.com/apikey. Optional: an ElevenLabs key
  for the voice modes, and a Tavily key for web search.
- **About 300 MB of disk** for the local embedding model, and a network connection for this first setup. After setup, only the model calls need the network; retrieval stays local.
- **liblouis**, only for braille output: `brew install liblouis` (macOS) or `apt install liblouis20` (Debian/Ubuntu). Everything else works without it.

### 2. Get the code and install the dependencies

```bash
git clone git@github.com:EZFRICA/apu-nemotron.git
```

```bash
cd apu-nemotron
```

```bash
uv sync
```

`uv sync` creates `.venv/` and installs the exact versions pinned in `uv.lock`, including the test tools and Streamlit.

### 3. Configure

```bash
cp .env.example .env
```

Then open `.env` and set `GEMINI_API_KEY`, which every text role uses by default. `ELEVENLABS_API_KEY` is needed only for the voice modes, and `NEBIUS_API_KEY` or `NVIDIA_API_KEY` only if you point a role at those providers.

| Variable | Default | What it does |
|---|---|---|
| `GEMINI_API_KEY` | *(none, required)* | Key for the roles below that default to the `gemini` provider |
| `APU_TUTOR_PROVIDER` / `APU_TUTOR_MODEL` | `gemini` / `gemini-3.8-flash` | Writes the answer the pupil reads; must support native tool calls |
| `APU_GUARD_PROVIDER` / `APU_GUARD_MODEL` | `gemini` / `gemini-3.5-flash-lite` | The topical guard. Must match `apu/guardrails/config/config.yml` |
| `APU_EXTRACTION_PROVIDER` / `APU_EXTRACTION_MODEL` | `gemini` / `gemini-3.5-flash-lite` | Extracts what to remember from each exchange |
| `APU_QUERY_GATE_PROVIDER` / `APU_QUERY_GATE_MODEL` | `gemini` / `gemini-3.1-flash-lite` | Classifies a search query before it is sent |
| `ELEVENLABS_API_KEY` | *(none)* | Speech in and out; without it the voice modes fall back to the browser voice |
| `APU_TTS_PROVIDER` / `APU_TTS_MODEL` | `elevenlabs` / `eleven_flash_v2_5` | Reads the answer out loud |
| `APU_STT_PROVIDER` / `APU_STT_MODEL` | `elevenlabs` / `scribe_v2` | Transcribes the pupil's recording |
| `NEBIUS_API_KEY`, `NVIDIA_API_KEY` | *(none)* | Only needed if a role is pointed at those providers |
| `LOCAL_EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Local ONNX embedder (full fastembed id) |
| `LOCAL_EMBEDDING_DIM` | `384` | Vector width; must match the embedder |
| `LOCAL_EMBEDDING_CACHE_DIR` | `./models` | Where the ONNX model files are read from |
| `APU_DATA_DIR` | `./data` | Per-device state: DLL (L2), LanceDB (L3), embedding stamp |
| `APU_MAX_DYNAMIC_BLOCKS` | `5` | Cap on non-fixed memory blocks before LRU page-out to L3 |
| `REGISTRY_MANIFEST_URL` | `https://storage.googleapis.com/akili-registry/manifest.json` | Cloud registry the device downloads courses from (bucket read from the URL) |
| `GOOGLE_APPLICATION_CREDENTIALS` | *(unset: Application Default Credentials)* | Service-account JSON with access to the registry bucket |
| `GCS_BUCKET_NAME` | *(none)* | Only for publishing: bucket `batch_pipeline.py --upload` writes to |
| `TAVILY_API_KEY` | *(none)* | Web search, from https://tavily.com/ |
| `APU_CLASS_POLICIES_PATH` | `registries/class_policies.json` | Per-class policy: escalation threshold, extra excluded search domains |
| `APU_TEACHER_ASSIGNMENTS_PATH` | `registries/teacher_assignments.json` | Who teaches or administers which class; the only source of roles |
| `APU_STUDENT_ID` / `APU_CLASS_ID` | `eleve-aya` / `lycee-cocody:3eA` | Identity the interface opens with; the sidebar switches it (stub, no login) |

### 4. Fetch the embedding model (once, needs the network)

```bash
uv run python scripts/fetch_embedding_model.py
```

This downloads about 240 MB into `./models` and then checks that the model loads from that cache with no network. The app itself **never downloads at runtime**: on an offline device, copy `models/` over from a connected machine, or point `LOCAL_EMBEDDING_CACHE_DIR` at an existing copy.

### 5. Course content: the cloud registry

Course chapters reach the tutor through a **cloud registry**: Markdown courses are embedded once with the same local model, published as Parquet files plus a `manifest.json` to a Google Cloud Storage bucket, and each device downloads the courses it needs into its local LanceDB (L3). No LLM is involved on this side.

**On a device (download courses).** The client reads the bucket through an authenticated Google Cloud client, so the device needs credentials, not only network access. Either sign in with your Google account (the `gcloud` CLI is a Google tool, not a Python command):

```bash
gcloud auth application-default login
```

or set `GOOGLE_APPLICATION_CREDENTIALS` in `.env` to a service-account JSON with read access to the bucket. Then, in the interface (step 7), open **📚 Active course** on the student page, click **Browse the cloud registry**, pick a course and click **⬇️ Download and activate**. **🔄 Check for updates (prompts)** refreshes the system prompts from the registry. Courses stay usable offline once downloaded.

**Publishing your own registry (maintainer).** Chapters live in `cloud_registry/courses/<grade>/<subject>/*.md`, the list of grades and subjects in `cloud_registry/config/curriculum.yaml`, the tutor prompts in `cloud_registry/courses/prompts/`. Build the registry locally into `cloud_registry/registry/` to inspect it:

```bash
uv run python cloud_registry/pipeline/batch_pipeline.py
```

Then set `GCS_BUCKET_NAME` in `.env`, authenticate as above with write access, and publish:

```bash
uv run python cloud_registry/pipeline/batch_pipeline.py --upload
```

Point devices at it with `REGISTRY_MANIFEST_URL=https://storage.googleapis.com/<your-bucket>/manifest.json`. The registry and the devices must use the same embedding model: a device refuses to download from a registry built with another one. Details and known issues: [cloud_registry/README.md](./cloud_registry/README.md).

### 6. Run the tests

```bash
uv run pytest
```

The suite needs neither a key nor the network: every provider's client is replaced by one fake that also checks which model each role's call goes to. If step 4 was skipped, the 7 tests that use the real embedding model are reported as skipped and everything else still runs.

### 7. Launch the interface

```bash
uv run streamlit run apu/ui/app.py
```

Streamlit prints a local URL, `http://localhost:8501` by default: open it in a browser. The project's `.streamlit/config.toml` runs it headless (no browser auto-open, no first-run prompt, no usage statistics) with a dark theme.

What you get, in three pages:

- **Student.** The tutor chat. Every question first goes through the topical guard, then gets its answer (with Tavily web search when the model needs it) and the memory extraction, all before the answer is displayed. Above the chat: the interaction mode (text, voice, braille), the off-topic counter against the class threshold, and the guard's last verdict. Under each answer, **💾 Save to notebook** keeps it in the student's notebook. Tabs show the notebook and its braille sheets, the last turn's searches and sources, and the memory hierarchy (L1 cache, L2 DLL chain, L3 LanceDB tables). The **📚 Active course** panel activates a local course, downloads one from the cloud registry (**Browse the cloud registry**, **⬇️ Download and activate**), refreshes prompts, and resets the student's memory.
- **Teacher / Admin.** A class's escalations (resolve with a note), their clusters, and an access-control check that shows a refusal outside the person's scope.
- **Demo setup.** Environment checks, live tests of the tutor model and Tavily, and demo data preparation.

The sidebar's **Sign in as** switches between demo students, teachers and admins. It is a stub, not authentication: see [Live demo](#live-demo).

To use another port:

```bash
uv run streamlit run apu/ui/app.py --server.port 8502
```

An alternative chat-first interface is available with Chainlit via `uv run chainlit run apu/ui/chainlit_app.py -w`. It provides native token streaming, in-composer audio recording, and action buttons directly under messages. The tutor runs through the shared `apu.ui.turn` runner, ensuring the topical guard and pedagogical pipeline behave identically to Streamlit.

For real-time multimodal audio and voice streaming, see the dedicated lab in [apu/ui/live/README.md](apu/ui/live/README.md). This interface runs on FastAPI and WebSockets to support bidirectional audio with Gemini Live and ElevenLabs, including voice intents and live braille generation. It can be launched with `uv run python -m apu.ui.live.proxy` on port 8765.

For the physical companion prototype designed for visually and motor impaired students, see the interactive 3D hardware studio in [apu/ui/hardware/README.md](apu/ui/hardware/README.md). It models a lightweight (165g) portable tactile voice recorder featuring raised geometric buttons, embossed Braille markings, a 3.5mm audio jack, USB-C fast charging, and a dedicated refreshable Braille display dock connector. It can be launched with `uv run python -m apu.ui.hardware.app` on port 8766.


### 8. Where state lives, and how to reset it

Everything the device holds is under `data/` (gitignored): `data/memory/metadata_links.json` is the DLL (L2), `data/akili_db/` the LanceDB store (L3: downloaded courses in `edu_registry`, archived student memory in `user_memory`), `data/local_manifest.json` the list of downloaded courses, `data/prompts.json` the system prompts from the registry, `data/escalations.sqlite3` the escalation events, `data/notebook.sqlite3` the student notebooks. **🗑️ Reset the student's memory (L1 + L2)** (student page) wipes L1 and L2; rows already archived in L3 stay. To reset everything and reload demo data, use the demo preparation (below), or stop Streamlit and delete the directory:

```bash
rm -rf data
```

### Troubleshooting

- **`⚠️ This turn could not be completed: GEMINI_API_KEY is not set` in the chat.** Set the key in `.env`, then stop Streamlit (Ctrl+C) and launch it again. A role pointed at another provider names that provider's variable instead. The **Demo setup** page checks every key and dependency at a glance.
- **`Embedding model ... is not present in ...`.** Step 4 was not run, or `LOCAL_EMBEDDING_CACHE_DIR` points to the wrong place.
- **"Registry unreachable" in the sidebar.** The device could not read the registry bucket: no Google credentials (step 5), no network, or a wrong `REGISTRY_MANIFEST_URL`. The terminal running Streamlit prints the exact reason (`[Sync] Auth failed: ...`). Courses already downloaded remain available.
- **"This registry was built with '...'" when downloading.** The registry and this device use different embedding models; align `LOCAL_EMBEDDING_MODEL` with the registry's, or republish the registry.
- **`Port 8501 is already in use`.** Use `--server.port` as shown above.
- **`⚠️ This turn could not be completed: The topical guard could not classify this turn`.** Every question first goes through the topical guard, which calls the guard model. Same fix as a missing or invalid provider key. The tutor deliberately does not answer when the guard cannot run.

## Live demo

The full run sheet is in [DEMO.md](./DEMO.md). In short:

1. With `.env` holding `NEBIUS_API_KEY` and `TAVILY_API_KEY`, prepare the demo data. This resets the local state under `data/`, builds and imports the courses locally (no Google credentials), and seeds example escalations with their clusters:
   ```bash
   uv run python scripts/prepare_demo.py
   ```
2. Launch the interface and open the printed URL:
   ```bash
   uv run streamlit run apu/ui/app.py
   ```
3. Check **Demo setup**: every line should be ✅, and the two live tests should answer.

> **Identity is simulated.** The sidebar lets anyone act as any demo student, teacher or admin, with no password. What the chosen person can see and do is real: it comes from `registries/` through the same service functions as the API.

## Guardrails, escalations and the teacher API

### Topical guard (NeMo Guardrails)

Every student turn goes through one shared input rail before anything else (`apu/guardrails/config/`, Colang). A classifier running on the configured guard model decides **strictly school use** (lessons, exercises, revision, study-related research) versus **off-topic**. There is no list of allowed subjects.

What varies per class is data, not Colang: `registries/class_policies.json` holds each class's `escalation_threshold` and extra search exclusions. A session reads its class policy **once, when it opens**; a changed threshold applies to the next session.

- Off-topic, below the threshold: a kind redirect towards schoolwork.
- Off-topic, reaching the threshold: a firmer reply, and one `EscalationEvent` written in the background. Further attempts in the same session stay firm without adding events.
- The off-topic counter lives in memory for the session and restarts on reconnection.
- If the classifier cannot be reached, the turn is not answered.

The classifier is shown the last thing the tutor asked and the last thing the pupil said,
as background it must not follow. A tutor that teaches by asking questions gets answers
like "four", "yes" or "I don't know", and judged on their own those were refused: measured
on a real session, five turns out of seventeen were stopped, at least three of them
wrongly. Only the pupil's latest message is ever classified, the exchange is capped and its
delimiters cannot be forged, and everything that is not a clear allow still stops the turn.

### Web search (Tavily)

`apu/tools/web_search.py` only searches for a turn the topical guard validated, excludes social networks for everyone (`GLOBAL_EXCLUDED_DOMAINS`) plus each class's own additions, and returns its sources. `apu/modality/citations.py` renders them per output channel: a list at the end in text or braille; source names said aloud (never URLs) in voice, plus the written list when a screen is available. The tutor requests a search through native OpenAI tool calls (see [docs/decisions.md](./docs/decisions.md)), and the query it produces is itself classified before anything is sent ([docs/security.md](./docs/security.md)). The `web_search` tool is only offered on turns the guard validated, and a turn makes at most 2 searches before the model must answer.

### Escalations and clustering

Escalation events are stored apart from the tutoring memory (`data/escalations.sqlite3`): they are never DLL blocks, never L3 rows, and never returned by the pedagogical search. Events are immutable; "resolved" is a separate record joined at read time. After every 5 new events in a class (`APU_ESCALATION_CLUSTER_TRIGGER_COUNT`), a background job clusters that class's events (HDBSCAN on local embeddings); reads only return the last stored result.

### Teacher and admin API (FastAPI)

```bash
uv run uvicorn apu.api.app:app --reload
```

| Route | Who |
|---|---|
| `GET /escalations?class_id=...` | the class's teacher, or an admin of its establishment |
| `POST /escalations/{event_id}/resolve` | same; body `{"note": "..."}` is optional |
| `GET /escalations/clusters?class_id=...` | same |
| `GET /establishments/{establishment_id}/classes` | admin: every class of the establishment; teacher: their own |

Roles and scopes come only from `registries/teacher_assignments.json`, never from the request. With the demo registries (the `curl` CLI is not a Python command):

```bash
curl -H "X-Requester-Id: admin-cocody" http://127.0.0.1:8000/establishments/lycee-cocody/classes
```

> **⚠️ Authentication is a stub and is not secure.** The requester is whoever the `X-Requester-Id` header says, with no password or token: anyone who can reach the API can act as any teacher or admin. See `apu/auth/identity.py` before deploying anything.
>
> **Authorization, on the other hand, is real and tested.** Every route calls `authorize_view` first, and the scope comes only from `registries/teacher_assignments.json`: a teacher reads their own class and is refused on any other, an admin is confined to their establishment, and an unknown requester is refused outright (`tests/test_api.py`). So a teacher cannot reach another class's pupils even by asking; what a stub identity allows is claiming to be a different teacher.
>
> The pupil side has no equivalent: the interfaces take the pupil from a selector or a query parameter, and the notebook they open is real, persisted data. That is the gap to close before a real class uses this.

### Speech (Gemini)

The voice modes record the student's question, transcribe it, and read the tutor's answer out loud (`apu/modality/voice.py`). ElevenLabs does the audio by default, Gemini is the alternative, and neither ever answers: **the transcript goes through the topical guard exactly like a typed question**, and the tutor model still writes every answer. A full spoken turn measures 8.6 s end to end. A real-time speech-to-speech model is not the default, for the same reason: it answers the student on its own initiative, which is precisely where the guard has to sit. One is nevertheless available in the live lab, on the condition that makes it acceptable: its answer is held server side, audio and transcription both, until the guard has classified the question, and discarded unplayed on a refusal. That hold costs it its latency advantage (about 10 s a turn against 8.6 s), which is why the per-turn path stays the default. See [apu/ui/live/README.md](apu/ui/live/README.md).

Speech is optional. Without `ELEVENLABS_API_KEY` the interface still runs in text and braille, and a spoken answer falls back to the browser's own voice. To use Gemini for either direction instead, set `APU_TTS_PROVIDER` or `APU_STT_PROVIDER` to `gemini`. The Gemini speech model ships as `gemini-3.8-flash-lite-tts`, the fastest of the seven that account exposes: 3.47 s a reading against 3.60 s for `gemini-3.8-flash-tts` and 6.29 s for the `gemini-3.1-flash-tts-preview` it replaces, with no difference a read-back can detect ([docs/models.md](./docs/models.md)). For speech in, the Gemini side is `gemini-3.5-transcribe`, which kept every number in the measured French maths set at 1.48 s against 1.04 s for the ElevenLabs transcriber. Beware that the ids the API accepts differ from the names shown in the Gemini console: `gemini-3.1-flash-tts` is a 404.

A spoken turn takes about 8.6 s end to end: transcription, guard, answer, then speech.

### Braille

`apu/modality/braille/` translates with liblouis (English UEB by default, French BFU with `language="fr"`, grade 1 or grade 2) into Unicode braille or embosser encoding (Braille ASCII / BRF), and includes a simulated embosser. liblouis is a C library installed by the system, not by uv:

```bash
brew install liblouis
```

On Debian/Ubuntu: `apt install liblouis20`. Without it, the braille tests are skipped.

### Accessibility

The interface is audited, not assumed: axe-core against the running page, plus DOM checks
after a real turn. The findings, the patch that fixes them and what is still open are in
[docs/accessibility.md](./docs/accessibility.md). Alt+Q focuses the question box from
anywhere, and a skip link is the first focusable element.

### How the choices in this repository were checked

The model for each role, the latency of each component, and the guard's resistance to attack
were measured against the live services rather than assumed, and the findings are written
down:

- [docs/models.md](./docs/models.md): candidates from four providers compared in the exact
  role each would hold, including which models a key can actually call.
- [docs/measurements.md](./docs/measurements.md): what every component costs, and the three
  changes those numbers produced.
- [docs/security.md](./docs/security.md): 69 labelled attacks and 14 multi-turn social
  engineering scenarios against the guard, what got through, and the two gates it led to.
- [docs/accessibility.md](./docs/accessibility.md): the interface audited with axe-core.

The harnesses that produced them need several provider keys and cost money to run, so they are
not part of this repository.

### Student notebook

During a conversation the student keeps what matters to them in a notebook (`apu/notebook/`), and braille is generated from it. Each save keeps one of three things, the student's choice: the **full answer**, its **key points** (condensed by the tutor model, using only what the answer says), or an **excerpt** the student picks.

- **Two ways to save.** The **💾 Save to notebook** control under each answer, or by asking the tutor ("save the key points", "just keep the rule for adding fractions"): the tutor model calls the `save_to_notebook` tool. The chat path is what a student using voice or braille relies on. The tool is offered only on turns the guard validated, and the entry is filed under the student of the guard session, never a student named by the model.
- **Braille from the notebook.** In the **📓 Notebook** tab, pick entries, then generate a braille sheet from them as written, or from a revision summary the tutor model writes from them. Grade 1 or 2, shown in Unicode braille, with a BRF file for the embosser.
- **The tutor never reads the notebook.** No entry reaches the tutor's own turn: not the prompt, not a tool result, and a test drives a real turn with a marker in the notebook to check it. The store is its own SQLite file, apart from the DLL and L3.
- **One path sends entries to a model, and only the pupil opens it.** Asking for a revision sheet, in the Notebook tab or out loud in the live lab, sends the entries the pupil chose to the small write-back model, bounded by `APU_NOTEBOOK_MAX_SHEET_ENTRIES` and `APU_NOTEBOOK_MAX_SHEET_CHARS` in `apu/notebook/service.py`. It is a request, never something a turn does on its own.

## Repository layout

```
apu/
  config.py                # env loading, model IDs, paths, tunables
  logger.py                # shared logging (console + apu_runtime.log)
  inference/
    llm.py                 # one model per role, each with its own provider (OpenAI-compatible)
  runtime/
    agent.py               # LangGraph planner: retrieval, prompt, model calls, memory write-back
  mmu/
    dll.py                 # doubly linked list of memory blocks, LRU paging, BMJ routing
    cache_l1.py            # L1 in-process cache with per-type TTL
  storage/
    lance_driver.py        # L3 LanceDB vector store, embedding-space guard
  core/
    scheduler.py           # background task scheduler (ported stub, see docs/decisions.md)
    extraction.py          # tolerant parser for the extraction model's JSON
    block_detector.py      # proposes new dynamic memory blocks
    block_proposal.py      # the proposal contract between detector and executor
  embeddings/
    local_embedder.py      # local fastembed/ONNX wrapper, swappable per target device
  guardrails/
    config/                # shared NeMo Guardrails config: the guard model, topical rail (Colang)
    guard.py               # runs the input rail on each turn, fails closed
    actions.py             # classifier, off-topic counting and escalation, turn validation
    policy.py session.py   # per-class policy (read once per session), in-memory session state
  escalation/
    models.py              # EscalationEvent, EscalationResolution, cluster snapshots (immutable)
    clustering.py jobs.py  # HDBSCAN per class, deferred write and recompute jobs
  mmu/
    escalation_store.py    # escalation storage, kept out of the DLL and L3
    block_types.py         # block types the tutoring memory refuses
  auth/
    assignments.py         # registry: who teaches or administers what (only source of roles)
    authorization.py       # authorize_view
    identity.py            # AUTHENTICATION STUB, not secure
  api/
    app.py                 # FastAPI teacher/admin routes
  notebook/
    store.py               # notebook entries (full answer, key points, excerpt), SQLite
    service.py             # saving, key points and the revision sheet (the write-back model)
  tools/
    web_search.py          # Tavily search, only for guard-validated turns
    notebook.py            # save_to_notebook tool, only for guard-validated turns
  modality/
    mode.py citations.py   # interaction modes, source citations per output channel
    plain_text.py          # strips Markdown and math delimiters for braille
    braille/               # liblouis translator, embosser simulator, braille sheets (sheet.py)
  sync/
    sync_manager.py        # device side of the cloud registry: catalog, course download, prompts
  ui/
    turn.py                # one pupil turn, independent of the page that shows it
    app.py                 # Streamlit pages (uv run streamlit run apu/ui/app.py)
    chainlit_app.py        # Chainlit chat interface (uv run chainlit run apu/ui/chainlit_app.py -w)
    live/                  # Live voice lab, WebSockets, Gemini Live & ElevenLabs (see apu/ui/live/README.md)
    hardware/              # 3D tactile portable recorder prototype for students with disabilities (see apu/ui/hardware/README.md)
    common.py              # identity selector (stub), guard session, accessibility patch
    views/                 # student.py, teacher.py, demo.py
  demo/
    seed.py                # demo data preparation, reset, environment checks
cloud_registry/            # publishing side of the course registry (see its README)
  config/                  # curriculum.yaml, publishing settings
  courses/                 # Markdown chapters per grade/subject, tutor prompts
  pipeline/                # batch_pipeline.py: embed, build Parquet + manifest, upload to GCS
scripts/
  fetch_embedding_model.py # one-time download of the ONNX embedding model
  prepare_demo.py          # resets local state, loads courses locally, seeds example escalations
  purge_data.py            # erases stored escalations, by age or by pupil
.streamlit/config.toml     # headless, no telemetry, dark theme
registries/                # demo class policies, teacher assignments and demo students
DEMO.md                    # live demo run sheet
tests/                     # pytest suite, offline, no API key
docs/
  architecture.md          # one turn end to end, and where each layer lives
  decisions.md             # decisions, open questions
  models.md                # one model per role, and why
  measurements.md          # what each component costs
  security.md              # attacking the guard
  accessibility.md         # auditing the interface
```

## Status and documents

Working, and measured rather than assumed. The tutor answers with a guard on every exchange,
in text, voice and braille, with escalations and a teacher API behind a real authorization
registry; identity is still a stub and says so everywhere it appears.

| Document | What it holds |
|---|---|
| [docs/architecture.md](./docs/architecture.md) | one turn end to end, and where each layer lives |
| [docs/decisions.md](./docs/decisions.md) | what was decided and why, and what is still open |
| [docs/models.md](./docs/models.md) | the model chosen for each role, and the measurements behind it |
| [docs/measurements.md](./docs/measurements.md) | what each component costs, measured live |
| [docs/security.md](./docs/security.md) | attacking the guard, what got through, what was fixed |
| [docs/accessibility.md](./docs/accessibility.md) | the interface audited with axe-core, and what it cost |

## License

Apache License 2.0, see [LICENSE](./LICENSE).
