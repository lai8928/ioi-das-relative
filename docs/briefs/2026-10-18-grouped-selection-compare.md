# Brief: Selection within groups and cross-run comparison

- Branch: `feat/grouped-selection-compare`
- Task: `rank-sweep`
- Status: open
- Written: 2026-10-18, from [meeting 2026-10-15](../meetings/2026-10-15.md)
- Depends on: none

## Goal

Three capabilities, all driven by config, with no change to training:

1. Choose settings on validation separately within groups of grid values,
   for example the best layer for each rank, or the best learning rate and
   budget for each rank.
2. Report one run whose grid varies more than layer and seed without
   averaging the extra axes together.
3. Combine several saved experiments (GPT-2 Small and Medium, or one run
   per rank) into side-by-side tables and figures without loading a model.

## Context

- PLAN: [rank-sweep](../PLAN.md). PROTOCOL: Evaluation and selection
  (validation only, lock written before any test evaluation; read every
  rank against its untrained-alignment baseline). CONVENTIONS §1, §3, §4.
- `selection.choose_layer` groups validation results by layer only. Any
  other varying axis gives two results per (layer, seed) and raises
  `Duplicate seed 42 for layer 12` (verified 2026-10-17). This happens in
  `pipeline._evaluate_locked`, after every condition has trained. The
  schema fixes `selection.metric`, `aggregate`, and `tie_break`
  (`lowest_layer`) as constants.
- `report._layer_summaries` groups rows by layer, plus train dataset when
  `data.train` is a grid axis (`group_train` facets). Any other axis is
  averaged into the layer mean, and per-seed curves overwrite each other.
- The model cannot be a grid axis, because `model.*` and `tokenizer.*` must
  change together. Small vs. Medium therefore always come from separate
  runs, so a cross-run comparison is needed in any case.
- Because of the selection limit, the rank sweep runs as one config per model
  and rank: `configs/rank-sweep/gpt2-{medium,small}-rank{1,2,4,8}.json`
  (Medium layers 0–23, Small layers 6–10, seeds 42/43/44). Its outputs are
  produced on HPC3 and committed to `main` separately.
- Inputs available on `main` now: `outputs/layer-sweep/20261015-gpt2-small`
  and `outputs/model-scale/20261015-gpt2-medium`. Both are rank 1, share
  `val_indist_v1`, and have a selection lock and post-lock test.
- Planned use after merge (config only, values decided later): an
  optimization check at Medium layer 14 and Small layer 8 with grid
  `intervention.rank × training.learning_rate × training.epochs × seed`,
  choosing learning rate and epochs per rank.

## Scope

1. Selection
   - Add optional `selection.group_by`: a list of grid axes. A separate
     choice is made for each combination of their values.
   - Add optional `selection.choose`: the grid axes chosen over. Default
     `["intervention.layer"]`.
   - Seeds are always aggregated with `mean_over_seeds`. Every group must
     have complete, matching seed sets.
   - Tie-break: highest mean, then lowest values in `choose` order. Keep
     `lowest_layer` valid for the default case. Name the general rule in the
     schema.
   - `selection.json` records every group's choice with its contributing
     values and hashes.
   - A config without the new keys must produce selection evidence identical
     to today's, apart from `locked_at_utc`. This keeps resume and
     verification of existing runs working.
   - Post-lock evaluation still covers every condition.
2. Report
   - Group rows by every grid axis other than `intervention.layer` and
     `seed`, generalizing the `data.train` facets.
   - `layer_summary.csv` gets one column per such axis.
   - Figures draw one curve per group (or one facet per group) with seed-SD
     error bars.
   - `summary.md` lists each group's selection.
   - Runs without extra axes regenerate byte-identically.
3. Comparison
   - Command: `ioi-das compare --config configs/<task-id>/<name>.json`.
   - The comparison file lists saved experiment directories and names the
     settings used as panels and series (for example `model.name` as panel,
     `intervention.rank` as series).
   - Output goes to `outputs/<task-id>/<YYYYMMDD>-<name>/`, with the path
     derived as for runs.
   - `run.json` records `run_kind: "comparison"`, the git state, the
     comparison file and its SHA-256, and the SHA-256 of each input's
     `run.json` and `selection.json`.
   - Writes a combined CSV with one row per condition. Columns: model, layer,
     rank, learning rate, budget (epochs or max updates), train dataset,
     seed; train, validation, and post-lock test IIA; untrained-alignment
     (`initial_*`) and no-intervention baselines; whether the condition is
     at its group's selected setting.
   - Also writes per-group means with seed SD and `summary.md`.
   - Figures:
     - Validation IIA by layer: one curve per series, one panel per model,
       panels side by side, seed-SD error bars, untrained-alignment
       baseline drawn.
     - Validation and train IIA at each group's selected setting vs. rank:
       one line per model. Train is shown to judge fit.
     - Post-lock test, labelled descriptive.
   - Refuses inputs that are incomplete, fail hash verification, or use
     different validation datasets.
   - Never loads a model or writes into an input directory.
4. Schema for comparison files: a separate schema file or a discriminated
   form of `configs/schema.json`. `tests/test_conventions.py` must accept it
   (task matches the directory, name matches the file stem).
5. Example comparison config `configs/rank-sweep/gpt2-rank1-small-medium.json`
   over the two existing rank-1 runs listed in Context.

## Out of scope

- Experiment configs with learning-rate or budget values (added after merge
  by Claude Code).
- Any change to training, evaluation metrics, or datasets.
- Choosing anything on test.
- Running the rank sweep or the optimization check.

## Acceptance

1. `$PY -B -m pytest -q` passes. New tests cover:
   - grouped selection on synthetic results (two ranks × layers × seeds,
     including ties and an incomplete group);
   - choosing over non-layer axes;
   - unchanged default evidence;
   - report grouping;
   - comparison refusals (incomplete input, hash mismatch, different
     validation dataset).
2. For `outputs/layer-sweep/20261015-gpt2-small` and
   `outputs/model-scale/20261015-gpt2-medium`, rebuilding the selection
   evidence from saved results (in a temporary copy) equals their
   `selection.json` apart from `locked_at_utc`.
3. `ioi-das report` on both runs leaves `git diff --stat outputs/` empty.
4. `ioi-das compare --config configs/rank-sweep/gpt2-rank1-small-medium.json`
   completes. Its figures show Small (layers 0–11) and Medium (layers 0–23)
   side by side with baselines, and its CSV reproduces the per-layer
   validation means in both runs' `layer_summary.csv`.
5. A smoke run with a rank grid axis plus `selection.group_by` completes.
   Smoke runs skip selection, so the full selection path is covered by the
   unit tests in item 1.
6. The GPT-2 Small GPU regression is unchanged.

## Notes for the implementer

- A relative-depth x-axis option (layer / layer count) for the by-layer
  comparison figure would help compare Small and Medium; optional.
- Keep `choose_layer` as a thin case of the general function, or replace it
  and update its callers. Do not keep two selection code paths.
