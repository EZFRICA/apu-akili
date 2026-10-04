# The course registry

This turns the curriculum into what a device downloads: embedded course files, the system
prompts, and a manifest describing both. No model is called here: courses are embedded with the
same local ONNX model the device uses, and a model is only called on the device, at question
time.

## Layout

- `config/curriculum.yaml`: the grades and subjects to build. `config/settings.py`: publishing
  settings, and deliberately no embedding model.
- `courses/<grade>/<subject>/*.md`: one chapter per file (`index.md` is skipped); the system
  prompts are in `courses/prompts/`.
- `pipeline/batch_pipeline.py`: reads the chapters, embeds them, writes Parquet, exports the
  prompts and the manifest, and uploads with `--upload`. `manifest_generator.py` and
  `prompt_exporter.py` redo one step alone.
- `registry/`: the build output, not tracked by git; the bucket is the distribution channel.

The device side is `apu/sync/sync_manager.py`, driven from the Streamlit sidebar.

## The embedding model is shared with the device

The pipeline and the device must embed with **the same model**: a mismatch raises nothing, it
returns noise ranked as though it were relevant. Both read `LOCAL_EMBEDDING_MODEL` and
`LOCAL_EMBEDDING_DIM` from `apu/config.py`, so never name a model in this folder: a registry was
once published at 3072 dimensions while devices queried at 384.

The manifest carries a stamp (`"embedding": {"model": ..., "dim": 384}`), and a device refuses to
download from a registry built with another model. The pipeline stops if the embedder's width is
not `LOCAL_EMBEDDING_DIM`. **Changing the model means republishing the whole registry.**

## Build and publish

From the repository root. Build locally into `cloud_registry/registry/` and inspect it:

```bash
uv run python cloud_registry/pipeline/batch_pipeline.py
```

Then set `GCS_BUCKET_NAME` in `.env`, authenticate (`GOOGLE_APPLICATION_CREDENTIALS`, or
`gcloud auth application-default login`) with write access, and publish:

```bash
uv run python cloud_registry/pipeline/batch_pipeline.py --upload
```

Devices find it through `REGISTRY_MANIFEST_URL`, and read the bucket name from that URL. To
regenerate the manifest alone:

```bash
uv run python cloud_registry/pipeline/manifest_generator.py <bucket>
```

## Known issues

Inherited, and pinned by tests where it matters:

- **Devices need Google credentials** to download, not only the network.
- **The manifest's `url` fields say `/courses/<file>`** while files sit at the bucket root; the
  device never reads `url`.
- **`manifest_generator.py` writes no embedding stamp**, so a device falls back to checking the
  dimension only.
- **`prompt_exporter.py` writes `registry/prompts.json`**, where the device reads
  `registry/prompts/prompts_v1.json`.
- **"Check for updates" refreshes the prompts only**, never the courses.
