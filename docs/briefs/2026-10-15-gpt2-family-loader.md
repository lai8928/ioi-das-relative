# Brief: GPT-2 family models

- Branch: `feat/gpt2-family-loader`
- Task: `model-scale`
- Status: draft — confirm model size at the 2026-10-15 meeting
- Written: 2026-10-15, from [meeting 2026-10-12](../meetings/2026-10-12.md)
- Depends on: [config-pipeline](2026-10-15-config-pipeline.md); results use
  [layer-sweep](2026-10-15-layer-sweep.md)

## Goal

Run the layer-sweep protocol unchanged on a larger GPT-2 (initial candidate:
GPT-2 Medium, 24 layers, hidden size 1024) by changing only the config.

## Context

- `intervention.load_model` accepts only `name == "gpt2"` and always uses
  `GPT2LMHeadModel`; `build_intervention` already validates layer and rank
  against `model.config`.
- The local HuggingFace cache contains only `models--gpt2`. Downloading model
  weights requires the user's approval (AGENTS, Environment).
- GPUs: RTX 2080 Ti, 11 GB each. Medium in float32 is about 1.4 GB of weights.

## Scope

- Accept GPT-2 family names (`gpt2`, `gpt2-medium`, `gpt2-large`, `gpt2-xl`, or
  their `openai-community/` ids) with a pinned revision. Model and tokenizer
  must name the same family and revision.
- Derive layer count and hidden size from the loaded model; `"all"` in the
  grid uses that layer count.
- When weights are not cached, fail before any work with the exact download
  command for the user to run; never download automatically.
- `configs/model-scale/gpt2-medium.json`: extends
  `configs/layer-sweep/gpt2-small.json` and changes only `model` and
  `tokenizer`.
- Record model size, layer count, and hidden size in `run.json`.

## Out of scope

- Non-GPT-2 architectures.
- Changing data, location, rank, training budget, or seeds.

## Acceptance

1. `$PY -B -m pytest -q` passes; loader validation is unit-tested without
   downloading (for example with a small config object).
2. The GPT-2 Small regression from the config-pipeline brief still passes exactly.
3. Missing-cache failure shows the download command.
4. After the user provides the weights: real-tokenizer audit of the legacy and
   validation data with the Medium tokenizer passes; smoke run on layer 12
   passes; peak GPU memory is recorded.
5. Full run (24 layers × 3 seeds) only after the user confirms.
