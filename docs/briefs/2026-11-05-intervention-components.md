# Brief: DAS at attention, MLP, and single-head activations

- Branch: `feat/intervention-components`
- Task: `intervention-sites`
- Status: open
- Written: 2026-11-05, from [meeting 2026-11-02](../meetings/2026-11-02.md)
- Depends on: none

## Goal

A config chooses which activation DAS intervenes on: the residual after a
layer (`block_output`, today's only site), the attention or MLP branch
output, the MLP hidden activation, or one attention head's output. A
condition can also record the full-vector patch at its site, a reference
that needs no training.

## Context

- PLAN: [intervention-sites](../PLAN.md). PROTOCOL: Training; Evaluation
  and selection (no test evaluation before the lock); Correctness checks.
  CONVENTIONS §1 (one code path; new behavior is a named option registered
  in one place), §3 (every key in the schema), §6 (tests and regression).
- `block_output` is fixed today in:
  - `configs/schema.json`: `intervention.component` is
    `{"const": "block_output"}`;
  - `intervention.build_intervention(model, layer, rank)`: hard-coded
    component, rank checked against `n_embd`;
  - `intervention.intervention_forward`: locations built for `unit="pos"`
    only;
  - its callers `experiment.run_condition`, `experiment.evaluate_checkpoint`,
    and `pipeline._evaluate_locked_records` (which passes no component).
- Sites (pyvene 0.1.8, `pyvene/models/gpt2/modelings_intervenable_gpt2.py`):

  | `intervention.component` | Hook | Dimension (Small / Medium) | pyvene unit |
  | --- | --- | --- | --- |
  | `block_output` | output of `h[l]` | 768 / 1024 | `pos` |
  | `attention_output` | output of `h[l].attn.resid_dropout` | 768 / 1024 | `pos` |
  | `mlp_output` | output of `h[l].mlp` | 768 / 1024 | `pos` |
  | `mlp_activation` | output of `h[l].mlp.act` | 3072 / 4096 | `pos` |
  | `head_attention_value_output` | input of `h[l].attn.c_proj`, one head's 64 columns | 64 | `h.pos` |

  The head site is the head's output z_h before W_O. pyvene has no
  per-head site after W_O because `c_proj` sums the heads.
- Feasibility, checked 2026-11-05 on CPU with GPT-2 Small layer 8 (head 6)
  and 8 validation pairs, using `ScopedIntervenableModel`
  (`scripts/adhoc/20261105-intervention-site-probe.py`):
  - `VanillaIntervention` equals a manual forward-hook patch at N exactly
    (max |diff| 0) at all four new sites.
  - Rank-1 `LowRankRotatedSpaceIntervention` with base as source
    reproduces the factual logits bit for bit; alignment gradients are
    nonzero.
  - pyvene sizes the rotation from the component (768 / 768 / 3072 / 64);
    `low_rank_dimension` is the only size input.
  - Head locations: each side of the single intervention is a pair
    `[heads, positions]` with `heads = [[h]] * batch_size` and
    `positions = [[p] for p in positions]`, that is
    `{"sources->base": ([[heads, source_positions]], [[heads, base_positions]])}`.
  - A rotation of full rank equals the full patch only to about 6e-5, so
    the full patch uses `VanillaIntervention`.
- Reference numbers (RTX 2080 Ti, `val_indist_v1`, full-vocabulary
  argmax; `scripts/adhoc/20261019-medium-ceiling.py small`, rerun
  2026-11-05): replacing the whole `block_output` vector at N gives
  validation IIA 17/200 at layer 7, 140/200 at layer 8, 70/200 at layer 9.
- The GPU regression (`tests/test_regression.py`) compares raw alignment
  tensors, prediction fields (added fields allowed), and training steps; it
  does not require byte-identical `.pt` files. The layer-sweep reference ran
  on an RTX 2080 Ti; A30 reruns match its counts but not its exact floats.
- Unit tests use a tiny random GPT-2 (`n_embd=16`, `n_head=2`, so 8
  dimensions per head) in `tests/test_intervention.py`.
- Every saved alignment holds torch's d × d orthogonal base (38 MB per file
  for Small `mlp_activation`). Running `mlp_activation` is deferred for that
  reason, but the code supports it.

## Scope

1. Config and schema
   - `intervention.component`: the five values in the table.
   - `intervention.head`: integer ≥ 0, required for
     `head_attention_value_output` and rejected for every other component,
     with a message that names the component. Checked against the model's
     head count when the grid is expanded, like `intervention.layer`;
     `"all"` resolves to every head, as it does for layers. Usable as a
     grid axis.
   - `intervention.rank` must lie between 1 and the site's dimension. Check
     it before any training, with a message that names the site and its
     dimension.
   - An optional switch that records the full-patch baseline (suggested:
     `intervention.full_patch_baseline: true`). Absent means off.
   - No defaults for the new keys are written into resolved configs, so
     every existing config keeps its resolved-config SHA-256 and saved runs
     still resume and verify.
   - The cached model metadata (or the grid expansion) provides the head
     count.
2. Intervention building blocks (`intervention.py`)
   - One registry from component to pyvene unit and dimension, with
     dimensions derived from the model config (`n_embd`; `n_inner` or
     4 · `n_embd`; `n_embd / n_head`).
   - One code path builds either a low-rank alignment or a full patch
     (`VanillaIntervention`) at a site (layer, component, head).
   - `intervention_forward` builds locations from the site's unit.
     `identity_forward`, the preflight checks (identity, gradients,
     mixed-length batching, cleanup), training, evaluation, and checkpoint
     reload work at every site.
3. Conditions, checkpoints, and locked evaluation
   - `run_condition`, `evaluate_checkpoint`, and `pipeline` pass the
     component and head.
   - `condition` in `alignment.pt` and `result.json` also records the head
     (null when the site is not a head) and the site dimension.
4. Full-patch baseline, when switched on
   - Evaluate every split the condition evaluates with the full patch at
     the site and token location, through `evaluate.evaluate_condition`.
     Save its metrics as `full_patch_<split>` in `metrics.json` and its
     predictions as `full_patch_<split>_predictions.jsonl`, with the same
     fields as the other evaluations.
   - Locked splits (test) get the full patch only in the post-lock
     evaluation, after the lock. Store it so that the report and the
     post-lock checks accept it.
   - The switch must not change the alignment's initialization, training,
     or any other artifact.
5. Report
   - `conditions.csv` gains `head` and the full-patch columns;
     `layer_summary.csv` and the by-layer figures gain the full-patch series
     when present.
   - Runs without the new keys regenerate byte-identically.

## Out of scope

- Selection or report grouping by component or head, and heat maps (brief
  [grouped-selection-report](2026-11-05-grouped-selection-report.md)).
- Several heads in one intervention; `block_input`, `attention_input`,
  `mlp_input`, Q / K / V, `attention_weight`; other units.
- The checkpoint format, including the saved d × d orthogonal base.
- PROTOCOL changes; experiment configs for intervention-sites (Claude Code
  adds them after the merge); running the sweeps.

## Acceptance

1. `$PY -B -m pytest -q` passes. New tests (the tiny random GPT-2 is
   enough) cover:
   - schema and grid expansion: each component; `head` required and
     rejected; head and rank bounds, failing before training;
     `intervention.head: "all"`;
   - at each site: the full patch equals a manual forward-hook patch
     exactly; rank-1 base-as-source reproduces the factual logits; nonzero
     alignment gradients; batched and per-example results agree with mixed
     lengths; checkpoint reload reproduces the logits;
   - a head patch changes only that head's columns of the `c_proj` input,
     at each example's own N;
   - the full patch is never evaluated on a locked split before the lock;
   - existing configs keep their resolved-config SHA-256.
2. The GPU regression (`IOI_DAS_RUN_GPU_REGRESSION=1`, RTX 2080 Ti) passes
   unchanged.
3. On an RTX 2080 Ti, a full run of
   `configs/single-condition-das/layer8-seed42.json` with
   `--override 'data.validation="val_indist_v1/validation"'` and the
   full-patch switch:
   - passes the reference parity check
     (`IOI_DAS_REGRESSION_DIR=<run> IOI_DAS_RUN_GPU_REGRESSION=1`
     `$PY -B -m pytest -q tests/test_regression.py`);
   - records a full-patch validation IIA of 140/200.
4. Smoke runs (`--smoke`) of the same config complete with
   `intervention.component` set to `attention_output`, `mlp_output`, and
   `mlp_activation`, and with `head_attention_value_output` plus
   `intervention.head=6`, each with the full-patch switch on.
5. `ioi-das report` on every existing run leaves `git diff --stat outputs/`
   empty.

Put the commands, counts, and run directories of items 2–4 in the merge
commit body; do not commit those run directories.

## Notes for the implementer

- Build the full-patch intervention after the alignment has been
  initialized (after `set_seed` and `build_intervention`), so that it
  cannot shift the alignment's random initialization.
- `report._add_post_lock_metrics` rejects any post-lock metric key that is
  not a configured locked split; full-patch metrics there need an explicit
  rule.
- pyvene's representation key encodes the component and unit (for example
  `layer_8_comp_block_output_unit_pos_nunit_1#0`); `block_output` must keep
  today's key, because the regression compares state keys.
- A JSON Schema `if`/`then` on `component` can express the head rule; a
  check in `validate_config` with a clear message is also fine.
