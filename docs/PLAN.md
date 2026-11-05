# Current plan

- Based on: [2026-11-02 meeting](meetings/2026-11-02.md). The direction was
  concluded on [2026-10-19](meetings/2026-10-19.md) and confirmed on
  2026-11-02; rank-sweep, data-scale, and object-names were closed on
  2026-11-05 (Amendment in the 2026-11-02 file). On 2026-11-05 the user
  chose a smaller first step (below) over sweeping every head at once.
- Period: 2026-11-02 → next meeting (date not set).
- Next meeting brief: not created yet.

## Questions this cycle

1. Besides the residual stream after a layer (`block_output`), do the
   attention branch output or the MLP branch output at the last token N
   support the POSITION swap? How do their layer profiles compare with
   `block_output`?
2. Which single heads of GPT-2 Small carry the POSITION signal, and is it
   in what a head outputs (Z), where it looks (Q, K), or what it reads (V)?
   Do they match the IOI circuit of Wang et al. (2022)?

## This cycle

### intervention-sites: DAS on attention, MLP, and single-head activations

GPT-2 Small only, in three steps; each step starts from the previous one's
results.

- Sites (GPT-2 Small sizes):

  | Site | `intervention.component` | Size | Token location |
  | --- | --- | --- | --- |
  | Residual after layer l | `block_output` | 768 | N (layer sweep, reference) |
  | Attention branch (all heads after W_O) | `attention_output` | 768 | N |
  | MLP branch | `mlp_output` | 768 | N |
  | Head output Z = A·V, before W_O | `head_attention_value_output` + head | 64 | N |
  | Query Q | `head_query_output` + head | 64 | N |
  | Key K | `head_key_output` + head | 64 | S2 |
  | Value V | `head_value_output` + head | 64 | S2 |

  K and V live at the attended tokens, so they use S2: the S-inhibition
  heads of Wang et al. attend from the end to S2, and in this data S2 has
  the same index in base and source, so only its context differs. A result
  at another location compares site and location together, never the site
  alone.
- Step 0: full-vector patch map (no training, validation only). Done
  2026-11-05 (`scripts/adhoc/20261105-full-patch-map.py`; tables in
  STATUS). The only heads with any effect are the S-inhibition heads 7.3,
  7.9, 8.6, 8.10 (Z at N and V at S2; at most 14/200, for 8.6) and the name
  movers 9.9 and 10.0 through Q at N (3/200 and 1/200). K at S2 and
  `mlp_output` at N give 0 everywhere; `attention_output` gives 10/200 at
  layer 7 and 50/200 at layer 8, against 17 and 140 for `block_output`.
- Step 1: code. Codex implements brief
  [intervention-components](briefs/2026-11-05-intervention-components.md):
  configs can choose the sites above; no other new feature.
- Step 2: small DAS runs after the merge. Rank 1, legacy training data, 10
  epochs, seeds 42 / 43 / 44, selection on `val_indist_v1`, test after the
  lock; local RTX 2080 Ti (35 s per condition in the layer sweep).
  - `attention_output` and `mlp_output`: one config each over layers 0–11,
    the layer-sweep form, so today's selection works. 72 conditions, about
    42 minutes.
  - Heads, chosen from step 0: 7.3, 7.9, 8.6, 8.10 (the S-inhibition
    heads, the only ones with full-patch effects on Z and V); 9.9 (name
    mover, the largest Q effect); and 9.6 (name mover with 0 at all four
    sites, a control: DAS far above 0 there would point to the subspace
    illusion). For each head Z and Q at N, K and V at S2: 6 × 4 × 3 seeds =
    72 conditions, about 42 minutes. One config per head and site, with
    only seeds varying, so today's selection works.
  - Configs `configs/intervention-sites/gpt2-small-attention-output.json`,
    `…-mlp-output.json`, and `…-l<layer>h<head>-<z|q|k|v>.json`, written by
    Claude Code after the merge.
- Reading the results:
  - Read every DAS result against the step-0 full patch at the same site
    and against the untrained-alignment baseline. DAS far above the full
    patch is the subspace-illusion pattern (Makelov et al., 2023). In 64
    dimensions a random direction overlaps a fixed one more (cos² ≈ 1/64
    vs 1/768), so the untrained baseline may be above 0.
  - Base and source share both names and the factual answer in every
    validation and test pair; the counterfactual (the base subject) is
    neither prompt's own answer. A head that only carries which name to say
    (for example the name movers 9.6, 9.9, 10.0) should stay near 0 even
    though it matters for IOI. IIA here measures whether a site carries the
    subject-position signal.
  - `attention_output` and `mlp_output` are one layer's increment;
    `block_output` is everything written so far. Several heads may share
    the signal, so a low single-head IIA does not rule out a role.
  - Z is the head's output before W_O; low-rank DAS there is not the same
    as on the head's 768-dimensional write to the residual.
  - With 200 validation pairs one IIA has a standard error of up to 0.035.
    The best site across configs is chosen on validation; test stays
    descriptive.
- Evidence to bring: the step-0 tables; validation IIA by layer for the two
  branches next to `block_output` (layer sweep), with baselines and the
  step-0 full patch; a per-head table of Z, Q, K, V (DAS validation IIA,
  full patch, untrained baseline, train fit on switch-required pairs);
  post-lock test (descriptive); the comparison with Wang et al.
- Depends on: brief
  [intervention-components](briefs/2026-11-05-intervention-components.md)
  (step 1).

## Other work

- [x] Record the 2026-10-19 and 2026-11-02 meetings; close rank-sweep,
  data-scale, and object-names (2026-11-05).
- [x] Check the sites in pyvene 0.1.8
  (`scripts/adhoc/20261105-intervention-site-probe.py`,
  `scripts/adhoc/20261105-head-qkv-probe.py`, 2026-11-05).
- [x] Step 0 (`scripts/adhoc/20261105-full-patch-map.py`, 2026-11-05).
- [x] Brief intervention-components, reduced to sites only (2026-11-05).
- [x] Codex implements intervention-components on its branch; Claude Code
  reviews it (merged 2026-11-05, `b2c3b8e`).
- [x] Write the step-2 configs, run them, and update STATUS (2026-11-05).
- [ ] Consolidate results for the next meeting.

## Deferred

- DAS on every head in one config (all 144 heads × Z, Q, K, V × 3 seeds =
  1,728 conditions, about 17 hours on one RTX 2080 Ti). Needs brief
  [grouped-selection-report](briefs/2026-11-05-grouped-selection-report.md)
  (selection over layer and head, heat maps). After step 2 is read.
- The full-patch baseline inside every run, as a package feature (step 0 is
  an ad hoc script for now).
- `mlp_activation` (3072 / 4096 dimensions): each saved alignment holds the
  d × d orthogonal base (38 MB for Small, 67 MB for Medium), saved twice per
  condition although training does not change it; 36 Small conditions add
  about 2.7 GB. Needs a storage decision first. It is also the site where
  Makelov et al. (2023) show the subspace illusion.
- GPT-2 Medium (24 layers, 16 heads per layer).
- Other token locations for each site (S1, IO, N − k; Z and Q at S2;
  duplicate-token and induction heads act at S2). Config only once the
  sites exist.
- Several heads swapped together through one joint subspace.
- `attention_input`, `mlp_input` (what a branch reads).
- A learning-rate check per site (activations differ in scale).
- A cross-run comparison command (from the dropped
  grouped-selection-compare brief).
- Phase 2 figure guide: explain each figure, field, and comparison.
- Earlier M4/M5 protocol drafts remain on branch `m3-complete-20261015` for
  reference only.

## Open questions

- Should the full-vector patch become a standard reference for every task
  (a PROTOCOL change)?
- Report a names-only score (S vs IO) next to the full-vocabulary argmax?
- How much to trust Medium's 0.3 at `block_output`, given that DAS exceeds
  the full-residual patch there (the checks of Makelov et al.)?
- "gave a bone to" prompts: Medium prefers " the". Report per object, or
  change the templates (a protocol decision)?
- Is a 200-pair in-distribution validation set enough?
- May results from different GPU types be compared directly?
