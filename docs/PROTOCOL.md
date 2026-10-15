# Experimental protocol

Rules that hold for every task unless a meeting decision changes them. Values
specific to one experiment (model, layers, seeds, sizes, optimizer settings)
belong in its config, not here. Each change is recorded in the change log
with the meeting that decided it.

## Data

- Preserve the original POSITION task: pairing counts per pattern
  combination, original asset halves (names, objects, places split at
  `len // 2`), the template split (templates 0–1 train, 2+ test),
  base-to-source resampling, and the counterfactual role rule.
- A source keeps its base's template, object, place, and name-to-symbol
  mapping; only the pattern changes.
- POSITION counterfactual label: if the first subject occurrence has the same
  NAME-order index in base and source, the answer is the base IO; otherwise
  it is the base subject.
- Track occurrence-level character spans during construction. Name lookup
  never searches for the first matching token ID.
- Splits must not share prompt text or semantic generation groups
  (template, unordered names, object, place).
- Never truncate, filter, rewrite, or append answers to prompts. Reject
  invalid positions with sample IDs. Report multi-token answer continuations
  as unsupported; never fall back to the first token.
- Datasets are generated once, hashed, registered in `data/registry.json`, and
  reused unchanged.

## Positions and readout

Three separate concepts:

- `target_variable`: the high-level causal variable and its counterfactual
  rule (currently `position`).
- `intervention_location`: an anchor plus optional offset, resolved per
  input.
- `readout_location`: always each base input's last valid token `N`.

| Anchor | Meaning within one prompt |
| --- | --- |
| `IO` / `GOAL_NAME` | The factual indirect object's occurrence; last token of its span |
| `S1`, `S2` | The subject's first and second occurrence; last token of each span |
| `END` / `N` | Last non-padding input token: `sum(attention_mask) - 1` |
| `N-k` | `N` with offset `-k`, bounds-checked per input |

Inputs are right-padded. Base and source positions, masks, and arrays are
resolved and kept independently.

## Training

- Language-model weights stay frozen and in eval mode; gradients still flow
  through the model to the intervention.
- Training and evaluation share the same intervention forward function.
- Each condition starts from a fresh alignment, optimizer, scheduler, and
  shuffle RNG. Nothing learned carries across conditions.
- The legacy per-update LinearLR schedule (`start_factor=1/3`,
  `end_factor=0.1`, `total_iters=10`, stepped every batch) is a named option.
  It is never silently switched to epoch stepping.

## Evaluation and selection

- Factual accuracy and IIA use argmax over the full vocabulary. Save exact
  counts and full-precision ratios; round only for display.
- Save per-example predictions, losses, and actual token indices, plus
  initial (untrained) and no-intervention baselines.
- Choose settings (for example, a layer) on validation only, and write the
  selection to disk before any test evaluation.
- The legacy 100-pair test set was inspected in earlier runs. Report it as a
  descriptive benchmark, not as an untouched held-out test.
- Legacy training includes 50% same-pattern pairs whose answer does not
  change, so training IIA has a floor near 0.47. Compare conditions on
  validation or test.
- Report every condition, including failed and pending ones. With multiple
  seeds, label the seed SD as seed variation, not a confidence interval.

## Correctness checks for intervention runs

- Model state hash identical before and after training.
- Finite, nonzero alignment gradients.
- Identity intervention reproduces factual logits.
- Batched and individual forwards agree on variable-length inputs.
- Saved alignment reloads to identical logits.
- Condition-owned hooks and caches are removed, including after failures.

## Change log

| Date | Change | Decided in |
| --- | --- | --- |
| 2026-10-15 | Consolidated from the phase-era AGENTS rules and plan contracts; added validation-only selection and the descriptive status of the legacy test set | [2026-10-12](meetings/2026-10-12.md) |
