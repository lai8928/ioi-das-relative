# Current plan

- Based on: [2026-10-15 meeting](meetings/2026-10-15.md)
- Period: 2026-10-15 → next meeting (date not set).
- Next meeting brief: not created yet.

## Questions this cycle

1. Does the DAS subspace rank (1 / 2 / 4 / 8) change IIA on GPT-2 Medium and
   GPT-2 Small, and is any difference due to rank or to optimization?
2. With object nouns in place of person names, does GPT-2 still solve IOI,
   and does the POSITION alignment still apply?

## This cycle

### rank-sweep: DAS rank 1 / 2 / 4 / 8

- Try (sweep): rank 1 / 2 / 4 / 8 × seeds 42 / 43 / 44, otherwise the
  layer-sweep protocol (N, block_output, legacy training data,
  `val_indist_v1` selection, test after the lock). GPT-2 Medium layers
  12–16; GPT-2 Small layers 6–10 (peak 8 ± 2) as the reference. The best
  layer is selected per rank on validation. All runs on HPC3 (A30), so every
  rank shares one GPU type; rank 1 repeats existing results as a check.
  - Runs now as one config per model and rank
    (`configs/rank-sweep/gpt2-{medium,small}-rank{1,2,4,8}.json`), with no
    code change. One config with a rank grid axis is not usable yet:
    selection groups by layer only and fails after all training ("Duplicate
    seed 42 for layer 12"), and the report would average ranks together.
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
- Depends on: brief `grouped-selection-compare` (selection within groups of
  grid values, a cross-run comparison figure) for the optimization check and
  the side-by-side figure. The sweep itself does not wait for it.

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
  `entity-vocabulary-datasets` and `alignment-transfer-eval`.

## Other work

- [ ] Write the briefs above for Codex.
- [ ] Consolidate results for the next meeting: settings recorded per run,
  unified IIA figures across conditions, supported conclusions, uncertain
  observations, and questions for next time.

## Deferred

- data-scale full run: waits for the budget decision (equal updates or equal
  epochs).
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
