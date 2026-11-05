# Current plan

- Based on: [2026-11-02 meeting](meetings/2026-11-02.md). The direction was
  concluded on [2026-10-19](meetings/2026-10-19.md) and confirmed on
  2026-11-02; rank-sweep, data-scale, and object-names were closed on
  2026-11-05 (Amendment in the 2026-11-02 file).
- Period: 2026-11-02 → next meeting (date not set).
- Next meeting brief: not created yet.

## Questions this cycle

1. Besides the residual stream after a layer (`block_output`), which
   activations at the last token N support the POSITION swap: the
   attention branch output, the MLP branch output, or single attention
   heads? How do their layer profiles compare with `block_output`?
2. In GPT-2 Small, which heads carry the POSITION signal at N, and do they
   match the IOI circuit of Wang et al. (2022)?

## This cycle

### intervention-sites: DAS on attention, MLP, and head outputs

- Sites (pyvene 0.1.8 names; GPT-2 Small dimensions):

  | Site | `intervention.component` | Dimension | What it is |
  | --- | --- | --- | --- |
  | Residual after layer l | `block_output` | 768 | Current site; reference |
  | Attention branch | `attention_output` | 768 | Sum of all heads after W_O, added to the residual |
  | MLP branch | `mlp_output` | 768 | MLP output, added to the residual |
  | Head h of layer l | `head_attention_value_output`, `intervention.head` | 64 | Head output z_h before W_O (the `c_proj` input) |

- Settings for both runs: GPT-2 Small, token location N, rank 1, legacy
  training data, 10 epochs, seeds 42 / 43 / 44, selection on
  `val_indist_v1`, test after the lock. This is the layer-sweep protocol
  with only the site changed. Every condition also records the full-vector
  patch at its site (the whole activation at N replaced with the source's,
  no training) next to the untrained-alignment and no-intervention
  baselines; on test only after the lock.
- Try (components): `block_output` / `attention_output` / `mlp_output` ×
  layers 0–11 × 3 seeds = 108 conditions in one config, best layer chosen
  per component. `block_output` repeats the layer sweep inside the same
  run: it must reproduce `outputs/layer-sweep/20261015-gpt2-small` bit for
  bit (raw alignment tensors and predictions, as in the GPU regression),
  and it puts the reference in the same tables and figures.
- Try (heads): all 144 heads (12 layers × 12 heads) × 3 seeds = 432
  conditions in one config, best (layer, head) chosen on validation.
- Where: the local RTX 2080 Ti GPUs, the GPU type of the layer-sweep
  reference, so the `block_output` repeat can match bit for bit. At the
  layer sweep's median of 35 s per condition: about 1.1 h for components
  and 4.2 h for heads on one GPU. Check GPU use before launching.
- Configs: `configs/intervention-sites/gpt2-small-components.json` and
  `configs/intervention-sites/gpt2-small-heads.json`, written by Claude
  Code after both briefs below merge.
- Reading the results:
  - Base and source share both names and the factual answer in every
    validation and test pair; only the order differs. The counterfactual
    (the base subject) is neither prompt's own answer. A head that only
    carries which name to say (for example the name mover heads 9.6, 9.9,
    10.0 of Wang et al.) should stay near 0 even though it matters for
    IOI. IIA here measures whether a site carries the subject-position
    signal, not whether the site matters.
  - Expected from Wang et al.: S-inhibition heads (7.3, 7.9, 8.6, 8.10) at
    N. `block_output` peaks at layers 7–9.
  - `attention_output` and `mlp_output` are one layer's increment;
    `block_output` is the sum of everything written so far. If the signal
    is written over layers 7 and 8, swapping one layer's branch may give
    less than `block_output` at layer 8.
  - Several heads may share the signal, so a low single-head IIA does not
    rule out a role.
  - In 64 dimensions a random direction overlaps a fixed one more (cos² ≈
    1/64 vs 1/768), so the untrained-alignment baseline may be above 0.
  - The head site is z_h before W_O. Low-rank DAS there is not the same as
    on the head's 768-dimensional write z_h·W_O^h; only the full patch is
    identical.
  - With 200 validation pairs, one IIA has a standard error of up to 0.035,
    and the best of 144 heads is biased upward; the post-lock test is the
    check.
- Evidence to bring: validation IIA by layer for the three components (one
  curve each, with untrained, no-intervention, and full-patch baselines); a
  layer × head map of validation IIA next to the full-patch map; the
  selected sites with post-lock test IIA (descriptive); train IIA on
  switch-required pairs to judge fit; the comparison with the Wang et al.
  heads; the `block_output` reproduction check.
- Depends on: briefs
  [intervention-components](briefs/2026-11-05-intervention-components.md)
  (the sites, the head index, the full-patch baseline) and then
  [grouped-selection-report](briefs/2026-11-05-grouped-selection-report.md)
  (selection per component or over layer and head, reports that keep these
  axes apart, the layer × head map). If the second is late, the components
  can run as one config per component with today's selection, without the
  shared figure; the heads need it.

## Other work

- [x] Record the 2026-10-19 and 2026-11-02 meetings; close rank-sweep,
  data-scale, and object-names (2026-11-05).
- [x] Check the sites in pyvene 0.1.8
  (`scripts/adhoc/20261105-intervention-site-probe.py`, 2026-11-05).
- [x] Write the briefs for Codex (2026-11-05).
- [ ] Codex implements intervention-components, then
  grouped-selection-report.
- [ ] Write the two configs, run them, and update STATUS.
- [ ] Consolidate results for the next meeting.

## Deferred

- GPT-2 Medium (24 layers, 16 heads per layer): 72 component and 1,152 head
  conditions, about 11 A30 hours at 33 s each. After the Small results are
  read.
- `mlp_activation` (3072 / 4096 dimensions). Supported by the
  intervention-components brief, but running it waits for a storage
  decision: each saved alignment holds the d × d orthogonal base (38 MB for
  Small, 67 MB for Medium), saved twice per condition although training
  does not change it, so 36 Small conditions add about 2.7 GB and 72 Medium
  conditions about 9.7 GB. It is also the site where Makelov et al. (2023)
  show the subspace illusion.
- Other token locations (S2, IO, S1, N − k), for heads that act there (for
  example duplicate-token and induction heads at S2). Config only once
  heads are supported.
- Several heads swapped together through one joint subspace (a separate
  capability).
- Q / K / V, `attention_input`, `mlp_input` (what a branch reads).
- A learning-rate check per site (activations differ in scale).
- A cross-run comparison command (from the dropped
  grouped-selection-compare brief), for Small vs Medium.
- Phase 2 figure guide: explain each figure, field, and comparison.
- Earlier M4/M5 protocol drafts remain on branch `m3-complete-20261015` for
  reference only.

## Open questions

- Should the full-vector patch become a standard reference for every task
  (a PROTOCOL change)? This cycle records it for intervention-sites only.
- Report a names-only score (S vs IO) next to the full-vocabulary argmax?
- How much to trust Medium's 0.3 at `block_output`, given that DAS exceeds
  the full-residual patch there (the checks of Makelov et al.)?
- "gave a bone to" prompts: Medium prefers " the". Report per object, or
  change the templates (a protocol decision)?
- Is a 200-pair in-distribution validation set enough?
- May results from different GPU types be compared directly?
