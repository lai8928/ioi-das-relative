# Brief: Rebuild the all-layer sweep at the last token

- Branch: `feat/layer-sweep`
- Task: `layer-sweep`
- Status: in review (revision requested 2026-10-15: baselines)
- Written: 2026-10-15, from [meeting 2026-10-12](../meetings/2026-10-12.md)
- Depends on: [config-pipeline](2026-10-15-config-pipeline.md) (merged)

## Goal

Run rank-1 DAS at the last token (N) for every GPT-2 Small layer, three seeds
each. Select a layer on a fixed validation set only, lock the choice, then
evaluate all checkpoints on the legacy test set and report all layers. Along
the way, make datasets generic: a machine-readable registry, one dataset
loader, and one `data audit` command that replaces the legacy `audit`.

## Context

- Protocol: [PROTOCOL](../PROTOCOL.md), sections Data, Evaluation and
  selection. Conventions: [CONVENTIONS](../CONVENTIONS.md), especially §3–§5
  and "Legacy entry points".
- Current dataset handling on `main` that this brief replaces:
  - `pipeline._dataset_inputs` parses the Markdown table in
    `data/REGISTRY.md`, accepts only `legacy_v1` train/test from one
    directory, and hard-codes dataset seed 42.
  - `audit.ensure_saved_pairs` requires the current `data.py` hash to equal
    the generator hash in the manifest; `LEGACY_MANIFEST_SHA256` special-cases
    the legacy manifest to get around that. Any edit to `data.py` would break
    reuse of every future dataset the same way.
  - `ioi-das audit --config configs/audit.json` is a legacy entry point tied
    to the old config format.
- Reference audit numbers for `legacy_v1` (`outputs/audit/summary.json`):
  600 fast/slow input comparisons, 1,800 continuation comparisons, 2,400
  batch/individual position comparisons, 1,800 supported single-token
  answers, 0 unsupported answers, focused checks passed.
- Reference validation set: `val_indist_v1`, 200 pairs (100 ABB→BAB, 100
  BAB→ABB) sampled from the legacy training resource pools with candidate
  seeds starting at 314159, rejecting any pair whose prompt text or semantic
  group (template, unordered names, object, place) overlaps legacy train/test
  or an already accepted pair. SHA-256 of `validation.jsonl` on branch
  `m3-complete-20261015`:
  `f62945c14803c2d9b8832b736bf5dd0d79226ea2e5fa7727b5aaa32aa54ba8e5`. Branch
  implementation for reference only: `src/ioi_das/m3_data.py`.
- Reference sweep results from the same branch
  (`outputs/m3_end_layer_sweep/m3_20261015_a/layer_summary.csv`). Mean IIA
  over seeds 42/43/44:

  | Layer | 0–6 | 7 | 8 | 9 | 10 | 11 |
  | --- | --- | --- | --- | --- | --- | --- |
  | Validation | 0 | 0.168333 | 0.831667 | 0.636667 | 0.021667 | 0.001667 |
  | Test | 0 | 0.083333 | 0.79 | 0.51 | 0.043333 | 0 |

## Scope

### Datasets

- `data/registry.json` becomes the single machine-readable registry: for
  each dataset name, its directory, splits (file, pair count, SHA-256),
  manifest SHA-256, and purpose. `legacy_v1` points at the existing files in
  `data/generated/` without moving them. Delete `data/REGISTRY.md` and update
  its references in `README.md`, `AGENTS.md`, `docs/CONVENTIONS.md`, and
  `docs/PROTOCOL.md` to `data/registry.json`.
- One dataset loader used by the pipeline and `data audit`: resolve
  `<dataset>/<split>` references from the registry, any number of splits
  (train, validation, test) from different dataset directories.
- Reuse check: verify split-file and manifest SHA-256 against the registry.
  The generator hash in a manifest is provenance only; it is recorded but
  does not block reuse. Remove `LEGACY_MANIFEST_SHA256` and its special case.
- Dataset builder (for example `ioi_das.datasets`): build a named dataset from
  `configs/datasets/<name>.json`, deduplicate by prompt text and semantic group
  against listed datasets, bound the number of candidate batches, write
  `data/generated/<name>/{<split>.jsonl,manifest.json}`, refuse to overwrite,
  and add the registry entry. Give dataset specs their own JSON Schema.
- CLI: `data build --config configs/datasets/<name>.json` and
  `data audit --dataset <name>`. The audit writes to
  `outputs/data-audit/<YYYYMMDD>-<dataset>/` with `run.json`.

### Legacy audit removal

- Remove the `audit` subcommand and the legacy `cli.load_config`. Keep
  `configs/audit.json` and `outputs/audit/` unchanged as history.
- Tests that read tokenizer settings from `configs/audit.json` use
  `configs/base.json` instead.

### Sweep, selection, and report

- Validation is a normal configured split: training uses `train`, selection
  uses `validation`, and splits listed in `selection.evaluate_after_lock` are
  never evaluated before the lock.
- Selection stage: after all grid conditions complete, write
  `selection.json` (metric, aggregate, tie-break, every contributing value,
  config/data/source hashes); only then evaluate every checkpoint on the
  locked splits, in separate hashed records that never rewrite the condition
  records.
- Add `selection` to `configs/schema.json`.
- Report: per-layer validation curve (mean, each seed, seed SD), train vs.
  validation curve, post-lock test curve, and CSVs covering every layer and
  seed, including failed or pending cells.
- `configs/layer-sweep/gpt2-small.json`: extends `base.json`, adds
  `data.validation: "val_indist_v1/validation"`,
  `grid: {"intervention.layer": "all", "seed": [42, 43, 44]}`, and the
  `selection` block from CONVENTIONS §3.

### Baselines (added in review, required by PROTOCOL "Evaluation and selection")

- For every condition and every pre-lock split (train, validation), save:
  - untrained-alignment metrics (`initial_<split>`), evaluated before the
    first optimizer step;
  - no-intervention IIA: the unmodified model's prediction scored against
    the counterfactual target;
  - per-pairing groups (`ABB->ABB`, `ABB->BAB`, `BAB->ABB`, `BAB->BAB`) plus
    `switch_required` and `unchanged_target`, each with IIA and
    no-intervention IIA counts.
- Post-lock records get the same no-intervention and per-pairing fields for
  the locked splits.
- `layer_summary.csv` gets `initial_validation` and no-intervention rows; the
  report shows baselines next to trained values.

## Out of scope

- Other token positions, components, ranks, or models.
- Changing the bytes of legacy data, legacy outputs, `configs/audit.json`, or
  `configs/phase2.json`.
- Grid axes over `data.*` (handled in the training-size-datasets brief).

## Acceptance

1. `$PY -B -m pytest -q` passes, including new tests for: registry
   resolution, hash-mismatch rejection, reuse after an edit to `data.py`,
   deduplication, bounded-generation failure, selection tie-break, and "no
   locked-split evaluation before `selection.json` exists".
2. `data audit --dataset legacy_v1` reports exactly the reference audit
   numbers above.
3. `data build --config configs/datasets/val_indist_v1.json` produces
   `validation.jsonl` with the reference SHA-256. If an exact match is
   impossible, stop and report the first differing record and why.
4. `data audit --dataset val_indist_v1` passes with 0 unsupported answers.
5. The single-condition GPU regression still passes exactly
   (`IOI_DAS_RUN_GPU_REGRESSION=1`).
6. Smoke run of `configs/layer-sweep/gpt2-small.json` passes and never
   evaluates the test split.
7. Full run on a clean tree: 36/36 conditions complete; layer 8 selected;
   per-layer mean validation and test IIA match the reference table to 6
   decimal places.
8. `report` regenerates all CSVs and figures from saved files without
   importing torch.
9. Baselines match branch `m3-complete-20261015` for every layer and seed,
   for example layer 8 / seed 42: train no-intervention 94/200
   (`unchanged_target` 94, `switch_required` 0); trained train
   `switch_required` 79/100; initial validation 0/200; validation
   no-intervention 0/200; trained validation 166/200 (`ABB->BAB` 79,
   `BAB->ABB` 87).
10. Adding baseline evaluations does not change training: all 36
    `alignment.pt` and `initial_alignment.pt` SHA-256 values equal those of
    run `20261015-gpt2-small` (commit `fab5595`).
11. Commit outputs as `results(layer-sweep): <experiment-id> — layer 8, val IIA 0.83`.
   Put the evidence log in that commit's body; do not edit `docs/STATUS.md`
   (Claude Code updates it after review).

## Notes for the implementer

- About 31 s and 0.7 GB GPU memory per condition on one RTX 2080 Ti; the full
  run takes about 20 minutes. Check `nvidia-smi` first and run long jobs in
  `tmux`.
- Commit the dataset and code before the full run; full runs require a clean
  tree.
