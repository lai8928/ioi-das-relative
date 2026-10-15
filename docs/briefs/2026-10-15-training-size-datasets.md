# Brief: Larger training sets

- Branch: `feat/training-size-datasets`
- Task: `data-scale`
- Status: draft — confirm sizes and training budget at the 2026-10-15 meeting
- Written: 2026-10-15, from [meeting 2026-10-12](../meetings/2026-10-12.md)
- Depends on: [config-pipeline](2026-10-15-config-pipeline.md),
  [layer-sweep](2026-10-15-layer-sweep.md) (dataset builder and selected layer)

## Goal

Measure IIA as a function of training-set size at one fixed layer, with the
validation and test sets unchanged.

## Context

- `data.generate_pairs` hard-codes 50 base prompts per pattern combination.
- Training resource pools: 49 names, 4 objects, 4 places, templates 0–1. This
  gives about 2 × C(49, 2) × 4 × 4 ≈ 37,600 distinct semantic groups, so
  5,000 unique pairs should fit; verify before building.
- Proposed design (to confirm): nested sets of 200 / 1000 / 5000 pairs from one
  pool, balanced across the four pattern combinations, deduplicated against
  `legacy_v1/test` and `val_indist_v1`; layer fixed to the layer-sweep
  selection (layer 8 for GPT-2 Small).
- Open decision for the meeting: equal number of optimizer updates across
  sizes (fair compute) or equal epochs (each example seen equally often).

## Scope

- Make pairs per combination a parameter of the generator. The default must
  regenerate `legacy_v1` byte-identically (regression test on both files'
  SHA-256 in `data/REGISTRY.md`).
- Dataset specs `configs/datasets/train_pool_v1.json` and nested subsets
  (`train_n200_v1`, `train_n1000_v1`, `train_n5000_v1`) built with the
  layer-sweep brief's builder; register them.
- Training option for a fixed update budget (for example
  `training.max_updates`) alongside epochs; the schedule semantics stay
  explicit.
- `configs/data-scale/gpt2-small-layer8.json` with
  `grid: {"data.train": [...], "seed": [42, 43, 44]}`.

## Out of scope

- Generalization splits (unseen names, templates, lengths): a later task.
- Re-selecting the layer per training size.

## Acceptance

1. `$PY -B -m pytest -q` passes, including the `legacy_v1` regeneration
   regression.
2. Each new dataset passes `data audit` with 0 unsupported answers; nesting
   and zero overlap with validation/test are verified and saved in its
   manifest.
3. Smoke run of the data-scale config passes.
4. Full run (3 sizes × 3 seeds) only after the budget decision is recorded in
   PLAN.
