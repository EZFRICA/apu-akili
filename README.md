# APU Akili

A school tutor built on the Agent Processor Unit: a tiered, persistent memory for LLM agents,
a topical guard in front of every exchange, and the model that measured best for each role.

It is meant for the hardware and connectivity of a typical West African classroom: retrieval
runs on a local embedder and keeps working offline; only the model calls need the network.

## What is in this repository

| | What it is |
|---|---|
| **The tutor** | `apu/`: memory, guard, notebook, text, voice and braille, with Streamlit pages for the pupil, the teacher and the demo. The product. |
| **The live voice lab** | `apu/ui/live/`: a websocket bench comparing real-time voice engines on one pipeline. |
| **Pocket Akili** | `apu/ui/presentation/`: a tactile handheld's specification, and a 3D stage where a key press runs a real turn. A design study, no firmware. |

The memory has three tiers: L1 an in-process cache, L2 a doubly linked list of memory blocks
persisted as JSON (the DLL), L3 a local LanceDB store, with BMJ routing promoting the most
relevant block to the head. One turn end to end, and where each piece lives:
[docs/architecture.md](./docs/architecture.md).

## Model routing

Each role was measured against candidates from four providers, in that exact role
([docs/models.md](./docs/models.md)). Moving a role is a setting, not a code change.

| Role | Model | Why |
|---|---|---|
| Tutor answer | `gemini-3.8-flash` | calls tools natively, half the tokens of the faster candidate |
| Topical guard | `gemini-3.5-flash-lite` | holds all 69 attacks of the red team corpus, twice, in 0.66 s |
| Memory write-back | `gemini-3.5-flash-lite` | same result as before, at a fifth of the latency |
| Search-query gate | `gemini-3.1-flash-lite` | 10/10, without blocking legitimate PE queries |
| Pictures | `gemini-nano-banana-2.1` | labels and values right in every picture checked; 15 to 35 s each |
| Speech out | `eleven_v4_turbo` | 1.68 s, first audio in 0.35 s, read back without an error |
| Speech in | `scribe_v2` | about 1 s; `scribe_v1` fails on exactly the same clips |
| Embeddings | local MiniLM (ONNX) | 4 ms per query, and no network needed |

## Quickstart

Every command runs through [uv](https://docs.astral.sh/uv/) from the repository root; `uv run`
uses the project's `.venv/` without activating anything.

### 1. Prerequisites

- **uv** (`brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh | sh`). It fetches
  Python 3.13 itself.
- **A Gemini API key** (https://aistudio.google.com/apikey). Optional: ElevenLabs for voice,
  Tavily for web search.
- **About 300 MB of disk** for the embedding model, and the network for this first setup.
- **liblouis**, only for braille: `brew install liblouis` or `apt install liblouis20`.

### 2. Get the code

```bash
git clone git@github.com:EZFRICA/apu-akili.git
```

```bash
cd apu-akili
```

```bash
uv sync
```

### 3. Configure

```bash
cp .env.example .env
```

Set `GEMINI_API_KEY`, which every text role uses by default. `ELEVENLABS_API_KEY` is needed only
for voice, `TAVILY_API_KEY` only for web search. Every other setting, with its default and what
it does, is documented in `.env.example`.

### 4. Fetch the embedding model (once, needs the network)

```bash
uv run python scripts/fetch_embedding_model.py
```

It downloads about 240 MB into `./models` and checks that the model loads offline. The app never
downloads at runtime: on an offline device, copy `models/` from a connected machine.

### 5. Courses

Courses come from a **cloud registry**: chapters embedded with the same local model, published
as Parquet with a hashed manifest to Google Cloud Storage, and downloaded into each device's L3.
Downloading needs Google credentials (`gcloud auth application-default login`, or
`GOOGLE_APPLICATION_CREDENTIALS`), then **📚 Active course → Browse the cloud registry** on the
student page. Downloaded courses work offline. Publishing a registry, and its known issues:
[cloud_registry/README.md](./cloud_registry/README.md). For a demo without credentials, step 9
builds the courses locally.

### 6. Run the tests

```bash
uv run pytest
```

No key and no network: every provider's client is replaced by a fake that also checks which
model each role calls. Without step 4, the 7 tests that need the real embedder are skipped.

### 7. Launch an interface

There are three, sharing one tutor: the same guard, notebook and memory.

| Interface | Command | Opens at |
|---|---|---|
| **Streamlit**: pupil, teacher, admin, demo | `uv run streamlit run apu/ui/app.py` | `http://localhost:8501` |
| **Live voice lab**: three engines compared | `uv run python -m apu.ui.live.proxy` | `http://localhost:8765/` (this machine only) |
| **Keynote stage**: Pocket Akili in 3D | the same command as the lab | `http://localhost:8765/presentation/` |

The last two are **one server**: it carries the websocket every voice front end talks to, and
serves both pages and the socket and microphone code they share (`apu/ui/shared/`). The stage
cannot work without the lab, so there is no second command. Details in
[apu/ui/live/README.md](apu/ui/live/README.md) and
[apu/ui/presentation/README.md](apu/ui/presentation/README.md).

Streamlit has three pages. **Student**: the chat, the interaction mode (text, voice, braille),
the off-topic counter, and tabs for the notebook, the last turn's sources and the memory tiers.
**Teacher / Admin**: a class's escalations and their clusters. **Demo setup**: environment
checks and live tests. **Sign in as**, in the sidebar, switches identity: a stub, not a login.
Another port: add `--server.port 8502`.

### 8. Where state lives

Everything is under `data/` (gitignored): the DLL in `memory/metadata_links.json`, LanceDB in
`akili_db/`, then `escalations.sqlite3`, `notebook.sqlite3`, `prompts.json` and
`local_manifest.json`. **🗑️ Reset the student's memory** on the student page clears L1 and L2;
deleting `data/`, with Streamlit stopped, resets everything.

### 9. Live demo

```bash
uv run python scripts/prepare_demo.py
```

It **resets `data/`**, builds and imports the courses locally (no Google credentials) and seeds
example escalations. Then launch Streamlit and check that **Demo setup** is all ✅. The full run
sheet is [DEMO.md](./DEMO.md).

### Troubleshooting

- **`This turn could not be completed: GEMINI_API_KEY is not set`.** Set it in `.env` and
  restart Streamlit. A role moved to another provider names that provider's variable instead.
- **`The topical guard could not classify this turn`.** The guard model is unreachable, usually a
  missing or wrong key. The tutor never answers unguarded.
- **`Embedding model ... is not present in ...`.** Step 4 was not run, or
  `LOCAL_EMBEDDING_CACHE_DIR` is wrong.
- **"Registry unreachable" in the sidebar.** No Google credentials, no network, or a wrong
  `REGISTRY_MANIFEST_URL`; the terminal shows why (`[Sync] Auth failed: ...`).
- **"This registry was built with '...'".** The registry and the device use different embedding
  models; align `LOCAL_EMBEDDING_MODEL`.

## Guard, escalations and the teacher API

Every turn goes through one NeMo Guardrails input rail first (`apu/guardrails/`): school use,
off-topic, or a disclosure of distress. Off-topic replies change with each attempt; at the
class's threshold (`registries/class_policies.json`) one escalation is recorded, and the pupil is
told their teacher will see it. Distress is answered with care, never counted, never stored. If
the guard cannot rule, the turn is not answered. Web search and pictures run only on validated
turns, and what is to be searched or drawn is classified on its own first. Attacks, findings and fixes:
[docs/security.md](./docs/security.md).

Escalations are stored apart from the tutoring memory and clustered per class (HDBSCAN on local
embeddings). Teachers read them in Streamlit or through the API:

```bash
uv run uvicorn apu.api.app:app --reload
```

| Route | Who |
|---|---|
| `GET /escalations?class_id=...` | the class's teacher, or an admin of its establishment |
| `POST /escalations/{event_id}/resolve` | same; body `{"note": "..."}` optional |
| `GET /escalations/clusters?class_id=...` | same |
| `GET /establishments/{establishment_id}/classes` | admin: every class; teacher: their own |

```bash
curl -H "X-Requester-Id: admin-cocody" http://127.0.0.1:8000/establishments/lycee-cocody/classes
```

> **⚠️ Authentication is a stub.** The requester is whoever `X-Requester-Id` says, so anyone who
> reaches the API can claim any teacher or admin. **Authorization is real**: roles and scopes come
> only from `registries/teacher_assignments.json`, and a teacher is refused on any other class
> (`tests/test_api.py`). The pupil side has no equivalent yet. Both must close before a real
> class uses this.

## Voice, braille, pictures and the notebook

- **Voice.** The recording is transcribed, the transcript goes through the guard like typed
  text, and the tutor writes every answer. A spoken turn takes 8.6 s. Speech out falls back from
  ElevenLabs to Gemini (`gemini-3.8-flash-lite-tts`), then, on the Streamlit page, to the
  browser's own voice.
- **Braille.** `apu/modality/braille/` translates with liblouis, grade 1 or 2, English or French,
  to Unicode braille or BRF, and lays the page out the way an embosser prints it.
- **Pictures.** A pupil who asks to see something ("draw it", "fais-moi un schéma") gets a
  picture drawn for them (`apu/tools/visual.py`), on a screen only: braille and a voice without
  a screen get it described in words. Drawing takes 15 to 35 s, so the tutor first says, in the
  pupil's language, that it is coming; that sentence reaches the pupil 7 to 12 s into the turn.
- **Notebook.** The pupil keeps a full answer, its key points or an excerpt (`apu/notebook/`), by
  button or by asking. **The tutor never reads it.** A braille revision sheet made from entries
  the pupil picks is the only path from the notebook to a model.

## Documents

| Document | What it holds |
|---|---|
| [docs/architecture.md](./docs/architecture.md) | one turn end to end, and where each piece lives |
| [docs/decisions.md](./docs/decisions.md) | what was decided and why, and what is still open |
| [docs/models.md](./docs/models.md) | the model for each role, and the measurements behind it |
| [docs/measurements.md](./docs/measurements.md) | what each component costs, measured live |
| [docs/security.md](./docs/security.md) | attacking the guard, what got through, what was fixed |
| [docs/accessibility.md](./docs/accessibility.md) | the interface audited with axe-core |
| [DEMO.md](./DEMO.md) | the live demo, step by step |

The harnesses behind these measurements need several provider keys and cost money to run, so
they are not part of this repository.

## License

Apache License 2.0, see [LICENSE](./LICENSE).
