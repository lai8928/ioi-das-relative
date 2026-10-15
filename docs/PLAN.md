# Current plan

- Based on: [2026-10-12 meeting](meetings/2026-10-12.md)
- Period: 2026-10-12 → 2026-10-15 meeting (14:30). Rewritten after that meeting.
- Next meeting brief: [2026-10-15](meetings/2026-10-15.md)

## Questions this cycle

1. At the last token (N), which GPT-2 Small layers carry the POSITION
   variable? (Answered by layer-sweep: layers 7–9, peak at layer 8.)
2. Does that picture hold with a larger model and with more training data?

## This cycle

### layer-sweep: bring the completed results onto `main`

- Try: register the results from branch `m3-complete-20261015` on `main`
  without rewriting them.
- Evidence to bring: per-layer validation/test IIA table and figures (done;
  see the 2026-10-15 brief).
- Depends on: the generic config/pipeline refactor below, so that the same
  code can reproduce the layer-8 result.
- Briefs: [config-pipeline](briefs/2026-10-15-config-pipeline.md),
  [layer-sweep](briefs/2026-10-15-layer-sweep.md).

### model-scale: GPT-2 Medium, same protocol

- Try: the layer-sweep protocol (N, rank 1, block_output, legacy training data,
  `val_indist_v1` selection, seeds 42/43/44) on GPT-2 Medium, all 24 layers.
- Evidence to bring: per-layer validation IIA curve for Medium next to Small.
- Depends on: the loader accepting GPT-2 family names; GPT-2 Medium weights in
  the local cache (currently absent; downloading needs user approval).
- Brief: [gpt2-family-loader](briefs/2026-10-15-gpt2-family-loader.md).

### data-scale: larger training sets

- Try: nested training sets of 200 / 1000 / 5000 pairs from one fixed pool,
  at a fixed layer chosen before the run, with validation and test unchanged.
- Evidence to bring: IIA as a function of training size, three seeds.
- Depends on: a generator with configurable pairs per combination and
  deduplication against existing splits.
- Brief: [training-size-datasets](briefs/2026-10-15-training-size-datasets.md).

## Other work

- [x] Restructure AGENTS and docs around meeting cycles and task IDs.
- [x] Mirror meeting notes to Notion (Chinese and English).
- [x] Write CONVENTIONS, CLAUDE.md, and briefs for Codex.
- [x] config-pipeline brief merged (`649d454`); parity verified.
- [ ] Codex implements the remaining briefs: layer-sweep →
  gpt2-family-loader and training-size-datasets.

## Deferred

- Phase 2 figure guide: explain each figure, field, and comparison.
- Earlier M4/M5 protocol drafts remain on branch `m3-complete-20261015` for
  reference only.

## Open questions

- Test other token positions (N-1, N-2, name tokens) at layers 7–9?
- Is a 200-pair in-distribution validation set enough?
