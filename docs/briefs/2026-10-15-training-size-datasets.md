# Brief: Larger training sets

- Branch: `feat/training-size-datasets` (branch from `feat/gpt2-family-loader`)
- Task: `data-scale`
- Status: merged 2026-10-15 (`c578921`)
- Written: 2026-10-15, from [meeting 2026-10-12](../meetings/2026-10-12.md)
- Depends on: [layer-sweep](2026-10-15-layer-sweep.md),
  [gpt2-family-loader](2026-10-15-gpt2-family-loader.md)

## Goal

Measure IIA as a function of training-set size at one fixed layer, with the
validation and test sets unchanged. The code must support both training
budgets so the choice can be made in the config later. In this brief only
smoke runs are executed; datasets are built and audited in full.

## Context

- `data.generate_pairs` hard-codes 50 base prompts per pattern combination.
- Training resource pools: 49 names, 4 objects, 4 places, templates 0–1:
  about 2 × C(49, 2) × 4 × 4 ≈ 37,600 distinct semantic groups, so 5,000
  unique pairs should fit; verify before building.
- `pipeline.expand_grid` rejects every `data.*` grid axis.
- Open decision for the advisor: equal number of optimizer updates across
  sizes (equal compute) or equal epochs (each example seen equally often).
  Both must be supported; the experiment config selects one.

## Scope

- Make pairs per combination a parameter of the generator. The default must
  regenerate `legacy_v1` byte-identically (regression test against the
  SHA-256 values in `data/registry.json`).
- Build one training pool and nested subsets of 200 / 1000 / 5000 pairs,
  balanced across the four pattern combinations, deduplicated by prompt text
  and semantic group against `legacy_v1/test` and `val_indist_v1`, with dataset
  specs in `configs/datasets/` (`train_pool_v1`, `train_n200_v1`,
  `train_n1000_v1`, `train_n5000_v1`), registered in `data/registry.json`.
  Sizes come from the specs, not code.
- Training budget option alongside epochs, for example
  `training.max_updates`; the schema requires exactly one of the two. The
  legacy per-update LinearLR semantics stay explicit and unchanged.
- Allow `data.train` as a grid axis; keep rejecting `data.validation` and
  `data.test`. Record the train dataset reference and hash per condition.
- `configs/data-scale/gpt2-small-layer8.json`: GPT-2 Small, layer 8, seeds
  42/43/44, `grid: {"data.train": [...], "seed": [...]}`, with a placeholder
  budget clearly marked in `name` (for example `-equal-updates`) and a second
  config for the other budget.

## Out of scope

- Generalization splits (unseen names, templates, lengths): a later task.
- Re-selecting the layer per training size.
- Full data-scale runs (run later by the user).

## Acceptance

1. `$PY -B -m pytest -q` passes, including the `legacy_v1` regeneration
   regression and tests for both budget options and the `data.train` grid
   axis.
2. All new datasets pass `data audit` with 0 unsupported answers; nesting and
   zero overlap with validation and test are verified and recorded in their
   manifests.
3. Smoke runs of both data-scale configs complete.
4. The GPT-2 Small regression and the layer-sweep results are unchanged.
