# Current plan

- Based on: [2026-10-15 meeting](meetings/2026-10-15.md)
- Period: 2026-10-15 → next meeting (date not set).
- Next meeting brief: not created yet.

## Questions this cycle

1. Does the DAS subspace rank (1 / 2 / 4 / 8) change IIA on GPT-2 Medium and
   GPT-2 Small, and is any difference due to rank or to optimization?
2. With object nouns in place of person names, does GPT-2 still solve IOI,
   and does the POSITION alignment still apply?
3. Does a larger training set raise GPT-2 Medium's IIA at any rank, and is
   any gain due to more data or to more updates?

## This cycle

### rank-sweep: DAS rank 1 / 2 / 4 / 8

- Try (sweep): rank 1 / 2 / 4 / 8 × seeds 42 / 43 / 44, otherwise the
  layer-sweep protocol (N, block_output, legacy training data,
  `val_indist_v1` selection, test after the lock). GPT-2 Medium all 24
  layers (widened from 12–16 on 2026-10-18; see the meeting amendment);
  GPT-2 Small layers 6–10 (peak 8 ± 2) as the reference. The best
  layer is selected per rank on validation. All runs on HPC3 (A30), so every
  rank shares one GPU type; rank 1 repeats existing results as a check.
  - Runs as one config per model and rank
    (`configs/rank-sweep/gpt2-{medium,small}-rank{1,2,4,8}.json`), with no
    code change. One config with a rank grid axis is not usable yet:
    selection groups by layer only and fails after all training ("Duplicate
    seed 42 for layer 12"), and the report would average ranks together.
  - [x] GPT-2 Medium, all four ranks (2026-10-19; see STATUS).
  - [ ] GPT-2 Small, all four ranks.
- Try (optimization check): at the layer each model's earlier sweep
  selected (Medium 14, Small 8), rank 1 / 2 / 4 / 8 × learning rate ×
  budget × 3 seeds. Proposed values: learning rate 0.01 / 0.03 / 0.1 (the
  legacy schedule multiplies it by 0.1 after update 10), 10 / 40 epochs.
  Pick each rank's best setting on validation, then compare ranks at their
  own best setting.
- Evidence to bring: validation IIA by layer, one curve per rank, Small and
  Medium side by side; a table with each rank's untrained-alignment
  baseline; post-lock test IIA (descriptive); the optimization check.
- Caveat: a higher rank gives the optimizer more freedom to find a subspace
  that changes the output without being the one the model uses (Makelov et
  al. 2023). Read every rank against its baseline, on validation and test.
- Depends on: brief
  [grouped-selection-compare](briefs/2026-10-18-grouped-selection-compare.md)
  (selection within groups of grid values, cross-run comparison) for the
  optimization check and the side-by-side figure. The sweep itself does not
  wait for it.

### data-scale: training-set size × rank on GPT-2 Medium

Added 2026-10-19 (see the meeting amendment).

- Try (main): nested `train_n200_v1` / `train_n1000_v1` / `train_n5000_v1`
  × rank 1 / 2 / 4 / 8 × layers 11–20 × seeds 42 / 43 / 44. Training is
  10 epochs (equal epochs, so 100 / 500 / 2,500 updates); everything else
  follows the rank sweep. The best layer is selected per run on validation
  before test. Layers 11–20 cover every layer where any rank had nonzero IIA
  (12–19), plus one layer of margin on each side.
- Try (control): `train_n200_v1` at layer 14 for 2,500 updates, every rank.
  Against the main runs at layer 14, this separates data from updates:
  - n200 at 2,500 vs. n5000 at 2,500 updates: same updates, 25× the data;
  - n200 at 100 vs. n200 at 2,500 updates: same data, 25× the updates.
- Configs: `configs/data-scale/gpt2-medium-rank{1,2,4,8}-n{200,1000,5000}.json`
  (30 conditions each) and `…-n200-updates2500.json` (3 each). One config
  per rank and size, for the same selection reason as the rank sweep.
- All on HPC3 (A30), so results compare directly with the rank sweep. The
  legacy-data rank sweep is a reference point but is not nested with these
  sets; compare sizes within `train_n*_v1`.
- Evidence to bring: validation IIA vs. training size, one line per rank,
  at the selected layer and by layer; the control comparison at layer 14;
  train IIA (switch-required pairs) to judge fit.

### object-names: object nouns in place of person names

- Try:
  1. Fix the design: object vocabulary (single-token answers, disjoint from
     the template objects ring, kiss, bone, basketball, computer, necklace,
     drink, snack), train/test halves, article handling; templates, places,
     patterns, and the counterfactual rule unchanged.
  2. Build, audit, and register object-noun datasets (train, validation,
     test) the same way as the name datasets.
  3. Behavior check: factual IOI accuracy of GPT-2 Small and Medium on object
     prompts vs. name prompts. If the model does not solve IOI with objects,
     IIA on them cannot be interpreted.
  4. DAS: (a) evaluate the name-trained alignment (Small layer 8, Medium
     layer 14, rank 1) on object data with fixed weights, to test whether the
     same role-swap mechanism carries over; (b) train new alignments on
     object data at the same layers.
- Evidence to bring: example prompts; names vs. objects table (factual
  accuracy, IIA); representative successes and failures from saved
  per-example predictions.
- Depends on: the design decisions in step 1; briefs
  [entity-vocabulary-datasets](briefs/2026-10-18-entity-vocabulary-datasets.md)
  (blocked on those decisions) and
  [alignment-transfer-eval](briefs/2026-10-18-alignment-transfer-eval.md).

## Other work

- [x] Write the briefs above for Codex (2026-10-18).
- [ ] Codex implements grouped-selection-compare and alignment-transfer-eval;
  entity-vocabulary-datasets waits for the design decisions.
- [ ] Consolidate results for the next meeting: settings recorded per run,
  unified IIA figures across conditions, supported conclusions, uncertain
  observations, and questions for next time.

## Deferred

- data-scale on GPT-2 Small at layer 8 (the `placeholder` configs): still
  waits for the budget decision. The Medium runs above may settle it.
- Phase 2 figure guide: explain each figure, field, and comparison.
- Earlier M4/M5 protocol drafts remain on branch `m3-complete-20261015` for
  reference only.

## Open questions

- Attention-head swapping (candidate task `head-patching`): replace one
  head's output at N with its output on the source, starting with GPT-2
  Small's 144 heads, and measure IIA per head. Method and timing undecided.
- Larger data: same distribution first, or unseen names or templates first?
- Test other token positions (N-1, N-2, name tokens) at the peak layers?
- Is a 200-pair in-distribution validation set enough?
- May results from different GPU types be compared directly?
