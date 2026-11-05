# Brief: Choose the intervention site: single heads (Z, Q, K, V) and branch outputs

- Branch: `feat/intervention-components`
- Task: `intervention-sites`
- Status: merged 2026-11-05 (`b2c3b8e`); evidence in the body of `6d3ea9a`
- Written: 2026-11-05, from [meeting 2026-11-02](../meetings/2026-11-02.md).
  Scope reduced the same day, before any implementation: the full-patch
  baseline and `mlp_activation` moved to PLAN Deferred; Q, K, and V were
  added.
- Depends on: none

## Goal

A config chooses which activation DAS intervenes on: the existing
`block_output`, the attention or MLP branch output, or one attention head's
output (Z), query (Q), key (K), or value (V). Training, evaluation,
selection, and reports stay as they are.

## Context

- PLAN: [intervention-sites](../PLAN.md), step 1. PROTOCOL: Training;
  Evaluation and selection; Correctness checks. CONVENTIONS §1 (one code
  path; new behavior is a named option registered in one place), §3 (every
  key in the schema), §6 (tests and regression).
- `block_output` is fixed today in:
  - `configs/schema.json`: `intervention.component` is
    `{"const": "block_output"}`;
  - `intervention.build_intervention(model, layer, rank)`: hard-coded
    component, rank checked against `n_embd`;
  - `intervention.intervention_forward`: locations built for `unit="pos"`
    only;
  - its callers `experiment.run_condition`, `experiment.evaluate_checkpoint`,
    and `pipeline._evaluate_locked_records` (which passes no component).
- Sites (pyvene 0.1.8 with transformers 4.57.6; sizes for GPT-2 Small):

  | `intervention.component` | Short name | Hook | Size per token | pyvene unit |
  | --- | --- | --- | --- | --- |
  | `block_output` | | output of `h[l]` | 768 | `pos` |
  | `attention_output` | | output of `h[l].attn.resid_dropout` (all heads after W_O) | 768 | `pos` |
  | `mlp_output` | | output of `h[l].mlp` | 768 | `pos` |
  | `head_attention_value_output` | Z | input of `h[l].attn.c_proj`, columns h·64 … h·64+63 | 64 | `h.pos` |
  | `head_query_output` | Q | output of `h[l].attn.c_attn`, query third, head h | 64 | `h.pos` |
  | `head_key_output` | K | output of `h[l].attn.c_attn`, key third, head h | 64 | `h.pos` |
  | `head_value_output` | V | output of `h[l].attn.c_attn`, value third, head h | 64 | `h.pos` |

  Sizes come from the model config (`n_embd`, `n_embd / n_head`); GPT-2
  Medium has 1024 and 16 heads of 64.
- Definitions. Z is one head's Z_h = A_h V_h, after the attention-weighted
  sum and before W_O; it is not V, the attention pattern A, the summed
  `attention_output`, or the residual. Q and K are taken after their
  projection and before QKᵀ; V after its projection and before AV. An
  interchange replaces only the DAS subspace of the chosen activation of one
  head at one token; everything else keeps base's values (for Q, the same
  head's K and V too). Later computation then runs normally; this is not
  path patching, and no model weight changes.
- Feasibility, checked 2026-11-05 on CPU with GPT-2 Small layer 8, head 6,
  and 8 validation pairs
  (`scripts/adhoc/20261105-intervention-site-probe.py`,
  `scripts/adhoc/20261105-head-qkv-probe.py`):
  - `VanillaIntervention` equals a manual forward-hook patch exactly (max
    |diff| 0) at all six new sites.
  - Rank-1 `LowRankRotatedSpaceIntervention` with base as source reproduces
    the factual logits bit for bit. DAS gradients are nonzero; no GPT-2
    parameter receives a gradient.
  - Q at N changes only head 6's attention row at N; K at S2 changes only
    head 6's attention; V at S2 leaves every attention probability
    unchanged.
  - pyvene sizes the rotation from the component; `low_rank_dimension` is
    the only size input.
  - Head locations: each side of the single intervention is a pair
    `[heads, positions]` with `heads = [[h]] * batch_size` and
    `positions = [[p] for p in positions]`:
    `{"sources->base": ([[heads, source_positions]], [[heads, base_positions]])}`.
- Positions: base and source are resolved separately
  (`positions.resolve_pair_positions`). In this data N and S2 have the same
  index in base and source; S1 and IO do not.
- Unit tests use a tiny random GPT-2 (`n_embd=16`, `n_head=2`, so 8
  dimensions per head) in `tests/test_intervention.py`.
- The GPU regression (`tests/test_regression.py`) compares raw alignment
  tensors, prediction fields (added fields allowed), and training steps; it
  does not require byte-identical `.pt` files. Its reference ran on an RTX
  2080 Ti.

## Scope

1. Config and schema
   - `intervention.component`: the seven values in the table.
   - `intervention.head`: integer ≥ 0, required for the four head sites and
     rejected for the others, with a message that names the component. It
     must be below the model's head count, checked before any training.
   - `intervention.rank` must lie between 1 and the site's size, checked
     before any training, with a message that names the site and its size.
   - No defaults for the new keys are written into resolved configs, so
     every existing config keeps its resolved-config SHA-256.
2. Intervention building blocks (`intervention.py`)
   - One registry from component to pyvene unit and size.
   - `build_intervention` takes the component and head.
   - `intervention_forward` builds locations from the site's unit.
     `identity_forward`, the preflight checks (identity, gradients,
     mixed-length batching, cleanup), training, evaluation, and checkpoint
     reload work at every site.
3. Conditions and locked evaluation
   - `run_condition`, `evaluate_checkpoint`, and `pipeline` pass the
     component and head.
   - `condition` in `alignment.pt` and `result.json` also records the head
     (null for sites that are not heads) and the site's size.

## Out of scope

- A full-patch baseline inside runs; selection or report grouping by
  component or head; heat maps; `intervention.head: "all"`; one config that
  scans several heads with selection (brief
  [grouped-selection-report](2026-11-05-grouped-selection-report.md),
  later).
- `mlp_activation`; several heads in one intervention; `block_input`,
  `attention_input`, `mlp_input`, `attention_weight`; other units.
- The checkpoint format; PROTOCOL changes; experiment configs (Claude Code
  adds them after the merge); running sweeps.

## Acceptance

1. `$PY -B -m pytest -q` passes. New tests (the tiny random GPT-2 on CPU is
   enough) cover:
   - schema: each component; `head` required and rejected; head and rank
     bounds, failing before training;
   - at each site: rank-1 base-as-source reproduces the factual logits;
     nonzero alignment gradients and no GPT-2 gradients; batched and
     per-example results agree with mixed lengths; checkpoint reload
     reproduces the logits;
   - at each head site: an interchange changes only that head's slice of
     the hooked tensor (Z: the `c_proj` input; Q, K, V: the `c_attn`
     output), at each example's own location;
   - Q and K change the layer's attention probabilities only for that head
     (Q: only the location's row); V leaves them unchanged;
   - existing configs keep their resolved-config SHA-256, and
     `block_output` keeps its pyvene representation key.
2. The GPU regression (`IOI_DAS_RUN_GPU_REGRESSION=1`, RTX 2080 Ti) passes
   unchanged.
3. Smoke runs (`--smoke`) of `configs/single-condition-das/layer8-seed42.json`
   complete with these overrides (one run each):
   - `intervention.component` = `attention_output`; = `mlp_output`;
   - `head_attention_value_output` and `head_query_output` with
     `intervention.head=6` (location N);
   - `head_key_output` and `head_value_output` with `intervention.head=6`
     and `intervention.location="S2"`.
4. `ioi-das report` on every existing run regenerates the same files as on
   `main`. (Corrected at review: 18 older runs, 12 of them data-audit,
   already differ from their saved reports when regenerated on `main`, so
   "leaves `git diff --stat outputs/` empty" cannot hold.)

Put the commands and results of items 2–4 in the merge commit body; do not
commit those run directories. If no GPU is available where you work, say
which items are unverified instead of skipping them silently.

## Notes for the implementer

- pyvene's representation key encodes the component and unit (for example
  `layer_8_comp_block_output_unit_pos_nunit_1#0`); `block_output` must keep
  today's key, because the regression compares state keys.
- Attention probabilities can be captured in tests with a forward hook on
  `h[l].attn.attn_dropout` (eager attention).
- The head rule can be a JSON Schema `if`/`then` on `component` or a check
  in `validate_config` with a clear message.
- Override syntax example:
  `--override 'intervention.component="head_key_output"' --override intervention.head=6 --override 'intervention.location="S2"'`.
