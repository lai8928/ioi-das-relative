# Brief: Evaluate saved alignments on other datasets

- Branch: `feat/alignment-transfer-eval`
- Task: `object-names`
- Status: open
- Written: 2026-10-18, from [meeting 2026-10-15](../meetings/2026-10-15.md)
- Depends on: none (the object-noun datasets come from
  [entity-vocabulary-datasets](2026-10-18-entity-vocabulary-datasets.md);
  this brief is tested on existing datasets)

## Goal

Evaluate alignments saved by a completed, selection-locked run on other
registered datasets, with fixed weights and no training. Each evaluation
records factual accuracy, IIA, baselines, and per-example predictions.
Two uses:

- Check whether the name-trained POSITION alignment also works on
  object-noun prompts.
- Measure GPT-2's factual IOI accuracy on a new dataset (the behavior
  check).

## Context

- PLAN: [object-names](../PLAN.md), steps 3–4. PROTOCOL: Evaluation and
  selection; Correctness checks.
- `experiment.evaluate_checkpoint` already evaluates one saved
  `alignment.pt`. It runs only after verifying the source run's selection
  lock and the checkpoint hash, checks frozen weights and hook cleanup, and
  writes per-example predictions. Today it writes only into the source run's
  `post_lock/`.
- Completed outputs are immutable, so evaluations on new datasets must go to
  a new experiment directory that references the source run.
- Every condition saves `alignment.pt` (trained) and `initial_alignment.pt`
  (untrained). The untrained one gives the untrained-alignment baseline on
  any new dataset.
- Source runs on `main`:

  | Run | Selected layer | Rank |
  | --- | --- | --- |
  | `outputs/layer-sweep/20261015-gpt2-small` | 8 | 1 |
  | `outputs/model-scale/20261015-gpt2-medium` | 14 | 1 |

## Scope

- A config form for evaluation-only experiments in
  `configs/<task-id>/<name>.json`. It names:
  - the source experiment directory;
  - which conditions to evaluate: `"selected"` (every seed at the locked
    choice) or explicit condition paths;
  - the registered dataset splits to evaluate.
- Model, tokenizer, and intervention settings (revision, layer, rank,
  component, location) come from the source run's resolved config. The new
  config cannot override them.
- Before evaluating, verify:
  - the source run is complete;
  - its `selection.json` matches the hash in its `run.json`;
  - each checkpoint matches the hashes in its `result.json`.
- For each chosen condition and split, evaluate both the trained and the
  untrained alignment. Save per-example predictions and the same metric keys
  as a training condition (factual accuracy, IIA, no-intervention IIA,
  pattern groups).
- Output goes to `outputs/<task-id>/<YYYYMMDD>-<name>/`. `run.json` records
  a distinct `run_kind`, the source run's and checkpoints' hashes, and the
  dataset hashes. A report gives a CSV and `summary.md` with means and seed
  SD per split.
- Entry point: dispatch from `ioi-das run --config` on the config form, or
  add `ioi-das evaluate --config`. Either way, share one evaluation path
  with `evaluate_checkpoint`; do not fork it.

## Out of scope

- Building object-noun datasets (separate brief).
- Training alignments on new data; that is an ordinary run config once the
  datasets exist.
- Changing metrics, selection, or the source runs.

## Acceptance

1. `$PY -B -m pytest -q` passes. New tests cover refusal on:
   - an incomplete source run;
   - a changed selection lock or checkpoint;
   - a config that tries to override model or intervention settings;
   - an unregistered dataset.
2. Code-path equivalence: evaluating the selected checkpoints of
   `outputs/layer-sweep/20261015-gpt2-small` must reproduce saved results
   exactly.
   - On `legacy_v1/test`: the metrics and per-example predictions saved in
     that run's `post_lock/`.
   - On `val_indist_v1/validation`: the saved `validation` metrics (trained)
     and `initial_validation` metrics (untrained) of the same conditions.
   - Run on the same GPU type as the source run (RTX 2080 Ti on the lab
     server); record the commands and results in the merge commit body.
3. A GPU evaluation of the GPT-2 Medium layer-14 checkpoints on
   `val_indist_v1/validation` completes and matches their saved validation
   metrics.

## Notes for the implementer

- The source run's `selection.json` is the lock for this evaluation: the
  alignment was chosen before any of the new data was seen.
