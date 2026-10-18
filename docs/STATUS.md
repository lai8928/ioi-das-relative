# Status

Updated: 2026-10-17 · Cycle since: [2026-10-15](meetings/2026-10-15.md)

## Tasks

| ID | Title | Status | Since | Formerly |
| --- | --- | --- | --- | --- |
| `position-audit` | Original IOI data and per-example position audit | done | 2026-10-12 | Phase 0–1 |
| `single-condition-das` | One DAS run: GPT-2 Small, layer 8, N, rank 1 | done | 2026-10-12 | Phase 2 |
| `layer-sweep` | Every layer at the last token, GPT-2 Small | done | 2026-10-15 | M3 / A |
| `model-scale` | Same protocol on a larger GPT-2 | done | 2026-10-15 | M4 / B |
| `data-scale` | Larger training sets | paused | 2026-10-17 | M5 / C |
| `rank-sweep` | DAS rank 1/2/4/8, GPT-2 Medium and Small, with an optimization check | active | 2026-10-15 | |
| `object-names` | Object nouns in place of person names: behavior and DAS | active | 2026-10-15 | |

## Infrastructure

- Config pipeline (`649d454`, tag `brief/config-pipeline`): `ioi-das run`,
  `ioi-das report`, inherited schema-validated configs, grids, `run.json`
  provenance, resume.
- Datasets and selection (`03dad11`): `data/registry.json`, one dataset
  loader, `ioi-das data build` and `ioi-das data audit` (the legacy `audit`
  command is removed), validation-only selection lock, post-lock evaluation,
  and baselines in every condition.
- Both merges were reviewed by Claude Code with independent GPU reruns.
- GPT-2 family loader and portable runs (`bf94a3e`, from
  [gpt2-family-loader](briefs/2026-10-15-gpt2-family-loader.md)): pinned
  `gpt2`/`gpt2-medium`/`-large`/`-xl`, early failure with the download
  command when weights are missing, `ioi-das status`,
  `environment/requirements-lock.txt` checked by `doctor`, README section
  "Run on another machine".
- Training-size datasets and budgets (`c578921`, from
  [training-size-datasets](briefs/2026-10-15-training-size-datasets.md)):
  `train_pool_v1` and nested `train_n200_v1` / `train_n1000_v1` /
  `train_n5000_v1`, built and audited (0 unsupported, balanced, nested, no
  overlap with validation or test); `training.max_updates` as an alternative
  to `epochs`; `data.train` as a grid axis.
- The loader and training-size merges were approved by the user; evidence
  is in the merge commit bodies.
- Second machine: UCI HPC3 (Slurm, partition `free-gpu`, NVIDIA A30, driver
  580). Environment matches the lock file (`doctor` passed with no
  differences); full test suite, all dataset audits, `doctor --require-gpu`,
  and a Medium smoke passed there on `c578921`.

## model-scale

- Goal: rerun the layer-sweep protocol on GPT-2 Medium (24 layers).
  Done; the follow-up (rank, learning rate, budget) is task `rank-sweep`.
- State: full run complete (`f833245`), 72/72 conditions plus 72/72
  post-lock, on HPC3 (one A30, Slurm job 58157400, 46 min, mean 33 s per
  condition). Source `c578921`, `protected_tree_clean=true` (`clean_tree`
  false only because of untracked check outputs). Config
  `configs/model-scale/gpt2-medium.json`, SHA-256 `76a6dd7f…8334de`.
- Result: layer 14 selected on validation (`val_indist_v1`) before test.

  | Layer | 0–11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20–23 |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | Validation (mean of 3 seeds) | 0.00 | 0.10 | 0.18 | **0.28** | 0.17 | 0.15 | 0.04 | 0.01 | 0.01 | 0.00 |
  | Test (descriptive) | 0.00 | 0.07 | 0.29 | **0.47** | 0.19 | 0.20 | 0.10 | 0.06 | 0.03 | 0.00–0.01 |
  | Train | 0.41 | 0.44 | 0.49 | 0.53 | 0.47 | 0.47 | 0.44 | 0.41 | 0.42 | 0.41 |

  Seed SD ≤ 0.03 everywhere. Baselines: untrained-alignment and
  no-intervention validation IIA are 0 at every layer; train IIA has a 0.41
  floor from same-pattern pairs (81/200). Same shape as GPT-2 Small (one
  mid-depth peak; relative depth 14/24 = 0.58 vs 8/12 = 0.67), but a much
  lower peak (0.28 vs 0.83), and train IIA at the peak is only 0.53: the
  alignment barely fits its own training data. Rank, learning rate, and
  budget were kept from GPT-2 Small and have not been varied.
- Evidence: `outputs/model-scale/20261015-gpt2-medium/` (`summary.md`,
  `selection.json`, `layer_summary.csv`, `figures/`).
- Cross-GPU check (not in the repository): on HPC3, the opt-in GPU
  regression (`layer8-seed42`, GPT-2 Small, Slurm job 58156709) reproduced
  every per-epoch and final IIA count of the RTX 2080 Ti reference (train
  173/200, test 79/100) but failed the exact-float check: losses differ at
  about 1e-6 (initial counterfactual loss 2.4105420 vs 2.4105425).
  Output kept on HPC3 under `~/hpc3-checks/`.

## rank-sweep

- Goal: does DAS rank 1/2/4/8 change IIA (GPT-2 Medium layers 12–16, GPT-2
  Small layers 6–10), and is any difference due to optimization?
- State: per-rank configs committed
  (`configs/rank-sweep/gpt2-{medium,small}-rank{1,2,4,8}.json`, 15
  conditions each); not run yet. One config per rank because selection
  groups by layer only. Rank 8 checked on CPU before launch (GPT-2 Small,
  layer 8, 8 cross-pattern pairs): nonzero finite alignment gradient,
  identity intervention reproduces factual logits exactly. Next: HPC3 run
  (A30) of all 8 configs.

## object-names

- Goal: object nouns in place of person names; compare behavior and DAS.
- State: not started. Design decisions pending (vocabulary, articles,
  transfer vs. retrain).

## data-scale

- Goal: IIA versus training size (200 / 1000 / 5000 pairs) at layer 8.
- State: code, datasets, audits, and smoke runs of both budgets merged
  (`c578921`). No full run yet.
- Paused: not in the 2026-10-15 cycle. Blocker: equal updates or equal
  epochs across sizes is an advisor decision. The configs in `configs/data-scale/` carry `placeholder` in their
  names until it is made.

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

Last result on `main` (2026-10-17, before the rank-sweep configs commit): 282 passed, 1 skipped (opt-in
GPU regression), 305 subtests.
