# Brief: Generic config loader and experiment pipeline

- Branch: `feat/config-pipeline`
- Task: infrastructure for `layer-sweep`, `model-scale`, `data-scale`
- Status: merged 2026-10-15 (`649d454`)
- Written: 2026-10-15, from [meeting 2026-10-12](../meetings/2026-10-12.md)
- Depends on: none

## Goal

Every experiment is defined by one config file and run by one generic code
path: `ioi-das run --config <file>`. A single condition is a grid of size 1.
The existing single-condition result is reproduced exactly by the new path.

## Context

- Rules: [CONVENTIONS](../CONVENTIONS.md) sections 1–6; [PROTOCOL](../PROTOCOL.md).
- Current code: `experiment.py` (`load_phase2_config`, `run_condition`) hard-codes
  layer 8, rank 1, `gpt2`, and the legacy training values; `cli.py`
  (`load_config`) hard-codes the audit's locations. Building blocks
  (`data`, `tokenization`, `positions`, `intervention`, `train`, `evaluate`,
  `validation`) are already mostly parameterized.
- Reference result to reproduce:
  `outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/` — initial
  train IIA 94/200, final train IIA 173/200, test IIA 79/100; tensors in
  `alignment.pt` and `initial_alignment.pt`; per-example rows in
  `*_predictions.jsonl`; per-update rows in `training_steps.jsonl`.
- A previous implementation exists on branch `m3-complete-20261015`
  (`src/ioi_das/m3.py`, `plot.py`, `scripts/check_m3_legacy_parity.py`). Read
  it for ideas only; do not merge it or copy its milestone-named structure.

## Scope

- Add `src/ioi_das/config.py`: load JSON, resolve `extends`, deep-merge,
  validate against `configs/schema.json` (use the installed `jsonschema`),
  apply `--override key.path=value`, return a typed resolved config.
- Add `src/ioi_das/pipeline.py`: expand `grid`; `run_condition` (one
  condition, explicit inputs); `run_experiment` (all conditions, `run.json`,
  output layout from CONVENTIONS §4, clean-tree check, `--resume` with hash
  verification, smoke mode).
- Add `src/ioi_das/report.py`: rebuild CSVs, `summary.md`, and figures from
  saved files only (no torch or model import).
- Refactor `experiment.py` and `cli.py` so the building blocks receive
  explicit parameters. Remove phase wording from identifiers, docstrings, and
  error messages.
- CLI: `run --config [--smoke] [--resume] [--override ...]`,
  `report --experiment-dir`. Keep `audit` and `doctor` working unchanged.
- Add `configs/schema.json`, `configs/base.json`, and
  `configs/single-condition-das/layer8-seed42.json`.
- Add `tests/test_conventions.py` (the (tested) rules in CONVENTIONS) and a
  regression test for the reference result (GPU-marked, skippable).
- Update README commands.

## Out of scope

- Validation data, selection, and multi-layer runs (layer-sweep brief).
- Model families other than `gpt2` (gpt2-family-loader brief); dataset sizes (training-size-datasets brief).
- Editing anything under `outputs/`, `data/generated/`, `vendor/`, or the
  legacy configs `configs/audit.json` and `configs/phase2.json`.
- Re-rendering `notebooks/phase2_walkthrough.ipynb`. Its source-integrity
  cell refers to commit `e7477e4`; note that in STATUS rather than changing it.

## Acceptance

1. `$PY -B -m pytest -q` passes, including `test_conventions.py`.
2. `$PY -B -m ioi_das.cli audit --config configs/audit.json` still passes and
   reuses the saved dataset.
3. Smoke: `CUDA_VISIBLE_DEVICES=<free> $PY -B -m ioi_das.cli run --config configs/single-condition-das/layer8-seed42.json --smoke`
   writes `outputs/single-condition-das/smoke-<date>-layer8-seed42/` with
   `run.json`.
4. Full run of the same config on a clean tree reproduces the reference
   exactly: IIA counts 94/200, 173/200, 79/100; `torch.equal` on every
   initial and final alignment tensor; identical per-example prediction
   fields and per-update losses (excluding timing fields).
5. `$PY -B -m ioi_das.cli report --experiment-dir <that run>` regenerates the
   summary without importing torch.
6. `git grep -nE "phase ?[0-9]|Phase ?[0-9]|m[0-9]_|milestone" -- src` returns
   nothing.

## Notes for the implementer

- Keep the config object read only at the pipeline layer; pass plain values
  down.
- Name the legacy schedule `legacy_per_update_linearlr` and keep its exact
  semantics (PROTOCOL, Training).
- Seeds: preserve how the current code seeds the alignment and the
  `numpy.random.RandomState(seed)` shuffle; the parity check depends on it.
