# Brief: Selection within groups and reports by site

- Branch: `feat/grouped-selection-report`
- Task: `intervention-sites`
- Status: open
- Written: 2026-11-05, from [meeting 2026-11-02](../meetings/2026-11-02.md)
- Depends on: [intervention-components](2026-11-05-intervention-components.md)
  (the `intervention.component` and `intervention.head` axes and the
  full-patch metrics)

## Goal

1. Choose settings on validation separately within groups of grid values
   (for example the best layer for each component), or jointly over several
   axes (for example the best layer and head).
2. Report a run whose grid varies more than layer and seed without
   averaging the extra axes together, with a layer × head map when heads
   vary.

## Context

- PLAN: [intervention-sites](../PLAN.md). Two configs follow this brief:
  components (grid `intervention.component` × `intervention.layer` ×
  `seed`, best layer per component) and heads (grid `intervention.layer` ×
  `intervention.head` × `seed`, best layer and head). PROTOCOL: Evaluation
  and selection (validation only; lock written before any test
  evaluation). CONVENTIONS §1, §3, §4.
- `selection.choose_layer` groups validation results by layer only. Any
  other varying axis gives two results per (layer, seed) and raises
  `Duplicate seed 42 for layer 12` (verified 2026-10-17 with a rank axis).
  This happens in `pipeline._evaluate_locked`, after every condition has
  trained. The schema fixes `selection.metric`, `aggregate`, and
  `tie_break` (`lowest_layer`) as constants.
- `report._layer_summaries` groups rows by layer, plus train dataset when
  `data.train` is a grid axis (`group_train` facets). Any other axis is
  averaged into the layer mean, and per-seed curves overwrite each other.
- The figures are hand-written SVG in `report.py`; no plotting library is
  used.
- This brief takes over the selection and report parts of the dropped
  [grouped-selection-compare](2026-10-18-grouped-selection-compare.md);
  its cross-run comparison command is deferred.

## Scope

1. Selection
   - Add optional `selection.group_by`: a list of grid axes. A separate
     choice is made for each combination of their values.
   - Add optional `selection.choose`: the grid axes chosen over, jointly.
     Default `["intervention.layer"]`.
   - Seeds are always aggregated with `mean_over_seeds`. Every candidate
     must have complete, matching seed sets.
   - Tie-break: highest mean, then lowest values in `choose` order. Keep
     `lowest_layer` valid for the default case. Name the general rule in
     the schema.
   - `selection.json` records every group's choice with its contributing
     values and hashes.
   - A config without the new keys must produce selection evidence
     identical to today's, apart from `locked_at_utc`. This keeps resume and
     verification of existing runs working.
   - Post-lock evaluation still covers every condition.
2. Report
   - Group rows by every grid axis other than `intervention.layer`,
     `intervention.head`, and `seed`, generalizing the `data.train` facets.
     `layer_summary.csv` gets one column per such axis.
   - By-layer figures draw one curve or one facet per group, with seed-SD
     error bars and the untrained-alignment and (when present) full-patch
     baselines.
   - When `intervention.head` varies: `head_summary.csv` (layer, head,
     split, mean, seed SD, baselines), and layer × head heat maps of mean
     validation IIA, full-patch validation IIA (when present),
     untrained-alignment validation IIA, and post-lock test IIA (labelled
     descriptive), with the selected (layer, head) marked.
   - `summary.md` lists each group's selection.
   - Runs without extra axes regenerate byte-identically.

## Out of scope

- The cross-run comparison command (deferred in PLAN).
- Any change to training, evaluation metrics, intervention sites, or
  datasets.
- Choosing anything on test.
- Experiment configs for intervention-sites (Claude Code adds them after
  the merge); running them.

## Acceptance

1. `$PY -B -m pytest -q` passes. New tests cover:
   - grouped selection on synthetic results (two components × layers ×
     seeds, including ties and an incomplete group);
   - a joint choice over layer and head;
   - unchanged default evidence;
   - report grouping and the head heat maps on synthetic results.
2. For `outputs/layer-sweep/20261015-gpt2-small` and
   `outputs/model-scale/20261015-gpt2-medium`, rebuilding the selection
   evidence from saved results (in a temporary copy) equals their
   `selection.json` apart from `locked_at_utc`.
3. `ioi-das report` on every existing run leaves `git diff --stat outputs/`
   empty.
4. Smoke runs complete for a grid `intervention.component` × layers × seeds
   with `selection.group_by: ["intervention.component"]`, and for a grid
   layers × `intervention.head` × seeds with
   `selection.choose: ["intervention.layer", "intervention.head"]`; their
   reports show the per-component curves and the heat maps. Smoke runs skip
   selection, so the selection path is covered by the unit tests in item 1.
5. The GPT-2 Small GPU regression is unchanged.

Put the commands and results of items 2–5 in the merge commit body; do not
commit the smoke run directories.

## Notes for the implementer

- Keep `choose_layer` as a thin case of the general function, or replace
  it and update its callers. Do not keep two selection code paths.
- For a full GPT-2 Small head grid the map is 12 × 12; Medium is 24 × 16.
