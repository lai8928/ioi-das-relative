# Status

Updated: 2026-10-15 · Cycle since: [2026-10-12](meetings/2026-10-12.md)

## Tasks

| ID | Title | Status | Since | Formerly |
| --- | --- | --- | --- | --- |
| `position-audit` | Original IOI data and per-example position audit | done | 2026-10-12 | Phase 0–1 |
| `single-condition-das` | One DAS run: GPT-2 Small, layer 8, N, rank 1 | done | 2026-10-12 | Phase 2 |
| `layer-sweep` | Every layer at the last token, GPT-2 Small | done | 2026-10-15 | M3 / A |
| `model-scale` | Same protocol on a larger GPT-2 | active | 2026-10-12 | M4 / B |
| `data-scale` | Larger training sets | active | 2026-10-12 | M5 / C |

## Infrastructure

- Config pipeline (`649d454`, tag `brief/config-pipeline`): `ioi-das run`,
  `ioi-das report`, inherited schema-validated configs, grids, `run.json`
  provenance, resume.
- Datasets and selection (`03dad11`): `data/registry.json`, one dataset
  loader, `ioi-das data build` and `ioi-das data audit` (the legacy `audit`
  command is removed), validation-only selection lock, post-lock evaluation,
  and baselines in every condition.
- Both merges were reviewed by Claude Code with independent GPU reruns.

## model-scale

- Goal: rerun the layer-sweep protocol on GPT-2 Medium (24 layers).
- State: [gpt2-family-loader brief](briefs/2026-10-15-gpt2-family-loader.md)
  open; code and smoke only, full run later (possibly on a faster machine).
- Blockers: loader and schema accept only `gpt2`; GPT-2 Medium weights are
  not cached (download approval goes in the message that hands over the
  brief).
- Estimate: 72 conditions; about 1.5–2.5 h on one RTX 2080 Ti.

## data-scale

- Goal: IIA versus training size (200 / 1000 / 5000 pairs) at layer 8.
- State: [training-size-datasets brief](briefs/2026-10-15-training-size-datasets.md)
  open; code, dataset builds and audits, and smoke only.
- Open decision: equal updates or equal epochs across sizes (both will be
  supported; the config chooses).

## Closed tasks

### layer-sweep (done 2026-10-15)

GPT-2 Small, rank-1 DAS on block_output at N, layers 0–11 × seeds 42/43/44,
36/36 complete. Layer 8 selected on validation (`val_indist_v1`) before any
test evaluation.

| Layer | 0–6 | 7 | 8 | 9 | 10 | 11 |
| --- | --- | --- | --- | --- | --- | --- |
| Validation (mean of 3 seeds) | 0.00 | 0.17 | **0.83** | 0.64 | 0.02 | 0.00 |
| Test (descriptive) | 0.00 | 0.08 | **0.79** | 0.51 | 0.04 | 0.00 |

Baselines: no-intervention and untrained-alignment validation IIA are 0 at
every layer; train IIA has a 0.47 floor from same-pattern pairs (94/200).
Every checkpoint matches the reference run on branch `m3-complete-20261015`
and an independent rerun bit for bit. Evidence:
`outputs/layer-sweep/20261015-gpt2-small/` (`summary.md`, `selection.json`,
`layer_summary.csv`, `figures/`). Config: `configs/layer-sweep/gpt2-small.json`.

### single-condition-das (done 2026-10-12)

GPT-2 Small, layer 8, block_output, N, rank 1, seed 42: train IIA 0.47 →
0.865, test IIA 0.79. Original evidence:
`outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/`; reproduced
bit for bit by the config pipeline in
`outputs/single-condition-das/20261015-layer8-seed42/`. Walkthrough:
`notebooks/phase2_walkthrough.ipynb`.

### position-audit (done 2026-10-12)

All 300 legacy pairs audited with the real GPT-2 tokenizer: 600 fast/slow
input comparisons, 1,800 continuation comparisons, and 2,400 batch/individual
position comparisons agree; 0 unsupported answers. Original evidence:
`outputs/audit/summary.md`; reproduced by `ioi-das data audit --dataset
legacy_v1` in `outputs/data-audit/20261015-legacy_v1/`.

## Verification on main

```bash
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m pytest -q
```

Last result on `main` (2026-10-15): 145 passed, 1 skipped (opt-in GPU
regression), 305 subtests.
