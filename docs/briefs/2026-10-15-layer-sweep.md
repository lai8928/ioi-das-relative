# Brief: Rebuild the all-layer sweep at the last token

- Branch: `feat/layer-sweep`
- Task: `layer-sweep`
- Status: open
- Written: 2026-10-15, from [meeting 2026-10-12](../meetings/2026-10-12.md)
- Depends on: [config-pipeline](2026-10-15-config-pipeline.md)

## Goal

Run rank-1 DAS at the last token (N) for every GPT-2 Small layer, three seeds
each. Select a layer on a fixed validation set only, lock the choice, then
evaluate all checkpoints on the legacy test set and report all layers.

## Context

- Protocol: [PROTOCOL](../PROTOCOL.md), sections Data, Evaluation and
  selection.
- Reference results from branch `m3-complete-20261015` (commit `d78221c`),
  `outputs/m3_end_layer_sweep/m3_20261015_a/layer_summary.csv`. Mean IIA over
  seeds 42/43/44:

  | Layer | 0–6 | 7 | 8 | 9 | 10 | 11 |
  | --- | --- | --- | --- | --- | --- | --- |
  | Validation | 0 | 0.168333 | 0.831667 | 0.636667 | 0.021667 | 0.001667 |
  | Test | 0 | 0.083333 | 0.79 | 0.51 | 0.043333 | 0 |

- Reference validation set: `val_indist_v1`, 200 pairs (100 ABB→BAB, 100
  BAB→ABB) sampled from the legacy training resource pools with candidate
  seeds starting at 314159, rejecting any pair whose prompt text or semantic
  group (template, unordered names, object, place) overlaps legacy train/test
  or an already accepted pair. SHA-256 of `validation.jsonl` on the branch:
  `f62945c14803c2d9b8832b736bf5dd0d79226ea2e5fa7727b5aaa32aa54ba8e5`. Branch
  implementation for reference: `src/ioi_das/m3_data.py`.

## Scope

- A generic split builder in the package (for example `ioi_das.datasets`):
  build a named dataset from a dataset spec, deduplicate against listed
  existing datasets, bound the number of candidate batches, write
  `data/generated/<name>/{<split>.jsonl,manifest.json}`, and refuse to
  overwrite.
- Dataset specs live in `configs/datasets/<name>.json` (add this directory to
  CONVENTIONS §3 and the schema).
- CLI: `data build --config configs/datasets/<name>.json` and
  `data audit --dataset <name>` (real tokenizer audit, as `audit` does today).
- Selection stage in the pipeline: after all grid conditions complete, write
  `selection.json` (metric, aggregate, tie-break, all contributing values,
  hashes); only then evaluate every checkpoint on `evaluate_after_lock`
  splits, in separate hashed records.
- Report: per-layer validation curve (mean, seeds, SD), train vs. validation
  curve, and post-lock test curve; CSVs with all layers and seeds.
- `configs/layer-sweep/gpt2-small.json` extending `base.json`.
- Register `val_indist_v1` in `data/REGISTRY.md` with its path on `main`.

## Out of scope

- Other token positions, components, or ranks.
- Changing the legacy training data or the legacy test set.

## Acceptance

1. `$PY -B -m pytest -q` passes, including new tests for deduplication,
   bounded generation failure, selection tie-break, and "no test evaluation
   before the lock".
2. `data build` for `val_indist_v1` produces `validation.jsonl` with the
   reference SHA-256 above. If an exact match is impossible, report the first
   differing record and why before continuing.
3. `data audit --dataset val_indist_v1` passes with 0 unsupported answers.
4. Smoke run of `configs/layer-sweep/gpt2-small.json` passes.
5. Full run: 36/36 conditions complete; layer 8 selected; per-layer mean IIA
   matches the reference table to 6 decimal places.
6. `report` regenerates all CSVs and figures from saved files.
7. Commit results as `results(layer-sweep): <experiment-id> — layer 8, val IIA 0.83`
   and update STATUS.

## Notes for the implementer

- About 31 s and 0.7 GB GPU memory per condition on one RTX 2080 Ti; the full
  run takes about 20 minutes. Check `nvidia-smi` first and run long jobs in
  `tmux`.
