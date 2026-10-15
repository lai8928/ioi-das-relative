# Brief: GPT-2 family models and portable runs

- Branch: `feat/gpt2-family-loader`
- Task: `model-scale`
- Status: merged 2026-10-15 (`bf94a3e`)
- Written: 2026-10-15, from [meeting 2026-10-12](../meetings/2026-10-12.md)
- Depends on: [layer-sweep](2026-10-15-layer-sweep.md) (merged first)

## Goal

Run the layer-sweep protocol unchanged on any GPT-2 size by changing only the
config, and make full runs easy to start and monitor on another machine. In
this brief only smoke runs are executed; full runs happen later, possibly on
a faster machine.

## Context

- `intervention.load_model` and `configs/schema.json` accept only
  `name == "gpt2"`; `build_intervention` already validates layer and rank
  against `model.config`, and `pipeline` reads the layer count from the cached
  model config.
- The local HuggingFace cache contains only `gpt2`. Downloading other weights
  requires the user's approval (AGENTS, Environment); the user's message that
  hands over this brief states whether GPT-2 Medium may be downloaded.
- Initial candidate: GPT-2 Medium (24 layers, hidden size 1024, about 1.4 GB
  of float32 weights). RTX 2080 Ti GPUs have 11 GB each.
- A GPT-2 Small sweep takes about 25 minutes (about 37 s per condition at
  roughly 27% GPU utilization). A Medium sweep has 72 conditions.

## Scope

- Accept GPT-2 family names (`gpt2`, `gpt2-medium`, `gpt2-large`, `gpt2-xl`,
  or their `openai-community/` ids) with a pinned 40-hex revision, in both
  `load_model` and the schema. Model and tokenizer must name the same family
  and revision.
- When weights are not cached, fail before any work with the exact download
  command; never download implicitly during a run.
- Record model name, revision, parameter count, layer count, and hidden size
  in `run.json` and each condition result.
- `ioi-das status --experiment-dir <dir>`: read `run.json` only; print
  completed / failed / pending conditions and post-lock records, elapsed
  time, and an estimated finish time from the mean condition duration.
- Portability:
  - `environment/requirements-lock.txt` with the exact versions of the
    packages the project imports (Python 3.10; torch 2.5.1+cu121;
    transformers 4.57.6; tokenizers 0.22.2; pyvene 0.1.8; numpy 2.2.6;
    jsonschema 4.26.0; safetensors; huggingface-hub; pytest 9.1.1).
  - `doctor` compares installed versions with that file and reports
    differences.
  - A README section "Run on another machine": clone, environment, model
    download for the pinned revisions, GPU check, smoke, full run in `tmux`,
    `status`, and how results come back (commit on that machine, or copy
    `outputs/<task>/<experiment-id>/` back and commit here).
- `configs/model-scale/gpt2-medium.json`: extends
  `configs/layer-sweep/gpt2-small.json` and changes only `task`, `name`,
  `model`, and `tokenizer`.

## Out of scope

- Non-GPT-2 architectures; float16/bfloat16.
- Changing data, location, rank, training budget, or seeds.
- Full Medium runs (run later by the user).
- Running one experiment across several GPUs.

## Acceptance

1. `$PY -B -m pytest -q` passes; loader and schema validation are
   unit-tested without downloading.
2. The GPT-2 Small regression still passes exactly
   (`IOI_DAS_RUN_GPU_REGRESSION=1`).
3. With GPT-2 Medium absent from the cache, a run fails early and prints the
   download command.
4. If the user approved the download: `data audit` of `legacy_v1` and
   `val_indist_v1` with the Medium tokenizer passes, and a smoke run of
   `configs/model-scale/gpt2-medium.json` restricted to layer 12, seed 42
   (via `--override`) completes; record its time and peak GPU memory.
5. `status` reports correct counts and an ETA for the existing layer-sweep
   run and for a run in progress.
6. `doctor` reports no differences on this machine.
