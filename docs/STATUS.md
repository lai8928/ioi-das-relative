# Status

Updated: 2026-11-05 · Cycle since: [2026-11-02](meetings/2026-11-02.md)

## Tasks

| ID | Title | Status | Since | Formerly |
| --- | --- | --- | --- | --- |
| `position-audit` | Original IOI data and per-example position audit | done | 2026-10-12 | Phase 0–1 |
| `single-condition-das` | One DAS run: GPT-2 Small, layer 8, N, rank 1 | done | 2026-10-12 | Phase 2 |
| `layer-sweep` | Every layer at the last token, GPT-2 Small | done | 2026-10-15 | M3 / A |
| `model-scale` | Same protocol on a larger GPT-2 | done | 2026-10-15 | M4 / B |
| `data-scale` | Larger training sets | done | 2026-11-05 | M5 / C |
| `rank-sweep` | DAS rank 1/2/4/8, GPT-2 Medium and Small, with an optimization check | done | 2026-11-05 | |
| `object-names` | Object nouns in place of person names: behavior and DAS | dropped | 2026-11-05 | |
| `intervention-sites` | DAS at other activations: attention and MLP outputs, single attention heads | active | 2026-10-19 | |

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
- Intervention sites (`b2c3b8e`, from
  [intervention-components](briefs/2026-11-05-intervention-components.md)):
  `intervention.component` selects `block_output`, `attention_output`,
  `mlp_output`, or one head's Z, Q, K, V with `intervention.head`. Written
  by Codex; reviewed by Claude Code (386 tests, GPU regression, six smoke
  runs, reports identical to `main`). Head and rank bounds are checked per
  condition, not at grid expansion. Regenerating reports changes 18 older
  saved runs (12 data-audit, 6 from 2026-10-15) on `main` as well; their
  saved files are left as they are.
- Second machine: UCI HPC3 (Slurm, partition `free-gpu`, NVIDIA A30, driver
  580). Environment matches the lock file (`doctor` passed with no
  differences); full test suite, all dataset audits, `doctor --require-gpu`,
  and a Medium smoke passed there on `c578921`.

## intervention-sites

- Goal: besides `block_output`, do the attention or MLP branch outputs at
  N support the POSITION swap, and which single heads carry it, through
  their output (Z), query, key, or value? GPT-2 Small first. Decided
  2026-10-19, confirmed 2026-11-02; staged into steps 0–2 on 2026-11-05
  (PLAN).
- Step 0, full-vector patch map (2026-11-05; RTX 2080 Ti; `val_indist_v1`,
  200 pairs; fixed weights, no training;
  `scripts/adhoc/20261105-full-patch-map.py`, whose `--csv` option writes
  the full per-site table, not kept in the repository). Each site's whole
  activation at its token location is replaced with the source's
  (`VanillaIntervention`). No intervention: IIA 0/200, IO top-1 195/200.
  Counts are IIA out of 200.

  | Site | Layers 0–6 | 7 | 8 | 9 | 10 | 11 |
  | --- | --- | --- | --- | --- | --- | --- |
  | `block_output` at N | 0 | 17 | 140 | 70 | 1 | 0 |
  | `attention_output` at N | 0 | 10 | 50 | 0 | 0 | 1 |
  | `mlp_output` at N | 0 | 0 | 0 | 0 | 0 | 0 |

  | Head | Z at N | Q at N | K at S2 | V at S2 |
  | --- | --- | --- | --- | --- |
  | 7.3 | 1 | 0 | 0 | 1 |
  | 7.9 | 1 | 0 | 0 | 2 |
  | 8.6 | 14 | 0 | 0 | 13 |
  | 8.10 | 4 | 0 | 0 | 4 |
  | 9.9 | 0 | 3 | 0 | 0 |
  | 10.0 | 0 | 1 | 0 | 0 |
  | the other 138 heads | 0 | 0 | 0 | 0 |

  - The `block_output` row reproduces the earlier hook-based script
    (`scripts/adhoc/20261019-medium-ceiling.py small`: 17 / 140 / 70 / 1),
    so the pyvene full patch and the hook agree.
  - Every head with an effect on Z or V is an S-inhibition head of Wang et
    al. (2022), and for each of them V at S2 gives about what Z at N gives,
    consistent with these heads reading the signal at S2. The name movers
    act only through Q, weakly.
  - Single heads are weak: the best (8.6) reaches 14/200, all of layer 8's
    attention 50/200, and the layer-8 residual 140/200. The signal is
    spread over heads and over layers 7–8, so single-head DAS is expected
    to stay low; read it against these counts.
  - Names-only counts (logit S > logit IO) are a few pairs higher, for
    example 149 for `block_output` layer 8, 59 for `attention_output`
    layer 8, and 17 for 8.6's Z.
- State: step 0 done (above). Step 1 merged:
  [intervention-components](briefs/2026-11-05-intervention-components.md)
  (`b2c3b8e`, reviewed by Claude Code with independent CPU and GPU
  reruns; see Infrastructure). Step 2 done (below).
- Step 2, DAS runs (2026-11-05; six local RTX 2080 Ti, source `831d2d9`,
  protected tree clean; 26 configs in `configs/intervention-sites/`,
  144/144 conditions plus post-lock test; median 40 s per condition).
  Rank 1, legacy training data, 10 epochs, seeds 42/43/44. Counts are means
  over seeds (validation out of 200, test out of 100); seed SD ≤ 1.2.
  Untrained-alignment validation IIA is 0 at every site. Table:
  `scripts/adhoc/20261105-site-das-summary.py` (pass the step-0 `--csv`
  table for the full-patch column).

  | Site | Layer | DAS validation | Full patch (step 0) | Test (descriptive) | Train, switch-required |
  | --- | --- | --- | --- | --- | --- |
  | `attention_output` at N | 7 | 23.0 | 10 | 8.0 | 9% |
  | `attention_output` at N | **8** (selected) | **87.3** | 50 | 37.3 | 38% |
  | `mlp_output` at N | every layer | ≤ 1 | 0 | 0 | ≤ 2% |
  | `block_output` at N (layer sweep) | 8 | 166 | 140 | 79 | |

  Other `attention_output` layers: 0. Heads (every other site, including
  all K and the control head 9.6, gives 0–1):

  | Head | Site | DAS validation | Full patch | Test |
  | --- | --- | --- | --- | --- |
  | 8.6 | V at S2 | 9.0 | 13 | 3.3 |
  | 8.6 | Z at N | 7.7 | 14 | 3.3 |
  | 8.10 | V at S2 | 3.7 | 4 | 0.0 |
  | 8.10 | Z at N | 3.0 | 4 | 0.7 |
  | 9.9 | Q at N | 3.7 | 3 | 0.0 |
  | 7.9 | Z at N / V at S2 | 1.0 / 1.0 | 1 / 2 | 0 |
  | 7.3 | Z at N / V at S2 | 0.7 / 0.0 | 1 / 1 | 0 |

  - The MLP at N carries nothing; the signal at N is written by attention
    in layers 7–8.
  - No single head carries much (best 8.6: 9/200), while layer 8's
    attention as a whole reaches 87/200 with DAS and 50/200 as a full
    patch; the four S-inhibition heads' full patches of Z sum to 20. The
    signal is spread over heads.
  - Heads show no sign of the subspace illusion: DAS stays at or below the
    full patch, the control 9.6 stays at 0, and the untrained baseline is 0.
    `attention_output` does: DAS 87 vs full patch 50 (as `block_output`,
    166 vs 140), so the branch-level DAS numbers need caution.
  - For 8.6 and 8.10, V at S2 gives about what Z at N gives, while K at S2
    and Q at N give 0: these heads pass the signal through what they read
    at S2, not through where they look.
  - Train ≈ validation (attention layer 8: 38% vs 44% of switch-required
    pairs), so overfitting does not limit these numbers.
- Evidence: `outputs/intervention-sites/20261105-gpt2-small-*` (26 runs:
  `summary.md`, `selection.json`, `layer_summary.csv`, `figures/`).
  [grouped-selection-report](briefs/2026-11-05-grouped-selection-report.md)
  is deferred until the step-2 results are read.
- Feasibility (2026-11-05, CPU, fixed weights; GPT-2 Small layer 8, head 6,
  first 8 validation pairs;
  `scripts/adhoc/20261105-intervention-site-probe.py` and
  `scripts/adhoc/20261105-head-qkv-probe.py`): pyvene 0.1.8 (transformers
  4.57.6) intervenes on `attention_output`, `mlp_output`, `mlp_activation`,
  and one head's Z, Q, K, or V (unit `h.pos`). At every site a full
  replacement (`VanillaIntervention`) equals a manual forward-hook patch
  exactly (max |diff| 0); rank-1 identity reproduces the factual logits bit
  for bit; DAS gradients are nonzero and no GPT-2 parameter gets one;
  rotation sizes are 768 / 768 / 3072 / 64. Q at N changes only that
  head's attention row at N, K at S2 only that head's attention, and V at
  S2 no attention probability. A full-rank rotation differs from the exact
  patch by up to 6e-5.
- Facts that shape the reading (checked 2026-11-05):
  - In all 200 `val_indist_v1` and all 100 legacy test pairs, base and
    source use the same two names and have the same factual answer; only
    the name order differs. The counterfactual answer (the base subject) is
    neither prompt's own answer. A head that only carries which name to say
    has nearly the same output on base and source, so its IIA stays low
    even if it matters for IOI.
  - Each saved alignment holds the d × d orthogonal base of torch's
    parametrization, identical before and after training (layer-sweep
    layer 8, seed 42: 768 × 768, 2.4 MB per file, saved in both
    `initial_alignment.pt` and `alignment.pt`). For a head it is 64 × 64;
    for `mlp_activation` 3072 × 3072 (38 MB) or 4096 × 4096 (67 MB).
  - The layer-sweep reference ran on an RTX 2080 Ti; HPC3 A30 reruns match
    its IIA counts but not its exact floats (see model-scale).

## Closed tasks

### rank-sweep (done 2026-11-05)

Closed by the user's decision (2026-11-02 Amendment) with only the GPT-2
Medium part run. Not run: the GPT-2 Small ranks
(`configs/rank-sweep/gpt2-small-rank{1,2,4,8}.json`) and the learning-rate /
budget check; brief
[grouped-selection-compare](briefs/2026-10-18-grouped-selection-compare.md)
was dropped.

GPT-2 Medium, rank 1 / 2 / 4 / 8 × all 24 layers × seeds 42/43/44: 4 × 72/72
conditions plus post-lock test, on HPC3 (one A30 per rank, Slurm jobs
58223841–58223844, 46–48 min each, median 33 s per condition). Source
`0e448cb`, `clean_tree=true`. Results commit `77da9d3`. Rank barely changes
anything. Every rank selects layer 14 on validation. At layer 14 (mean of 3
seeds):

| Rank | Validation | Test (descriptive) | Train | Train, switch-required pairs |
| --- | --- | --- | --- | --- |
| 1 | 0.283 | 0.470 | 0.528 | 0.247 |
| 2 | 0.287 | 0.473 | 0.527 | 0.243 |
| 4 | 0.277 | 0.467 | 0.532 | 0.253 |
| 8 | **0.295** | 0.477 | 0.537 | 0.263 |

The by-layer profile is the same for every rank: validation 0 at layers
0–11 and 20–23, and nonzero at 12–19 (layer 12: 0.10–0.12; 17: 0.05–0.06;
19: ≤ 0.01). Validation seed SD ≤ 0.03. Untrained-alignment and
no-intervention validation IIA are 0 at every layer for every rank. Even
rank 8 fits only 26% of its own switch-required training pairs, so the
subspace dimension is not what limits Medium at this learning rate and
budget. Rank 1 matches `outputs/model-scale/20261015-gpt2-medium` bit for
bit (same A30 type): all 288 compared artifact hashes are identical
(alignment, initial alignment, train and validation predictions). Why rank
does not help: see data-scale below. Evidence:
`outputs/rank-sweep/20261018-gpt2-medium-rank{1,2,4,8}/` (`summary.md`,
`selection.json`, `layer_summary.csv`, `figures/`).

### data-scale (done 2026-11-05)

Closed by the user's decision (2026-11-02 Amendment) with 10 of 16 GPT-2
Medium configs complete. Not run: rank 1 n1000, rank 2 n200 / n1000, rank 8
n200, and the rank 2 / rank 8 controls (cancelled 2026-10-19 at the user's
request; `4cad294` contains partial directories with 0–1 of 30 conditions
for the first four), and the GPT-2 Small layer-8 configs (`placeholder` in
their names).

- Runs: HPC3, one A30 per job, Slurm jobs 58242123–58242137, 2026-10-19;
  source `43a0d06`, results commit `4cad294`. Main configs: 30/30
  conditions (layers 11–20 × 3 seeds, 10 epochs) plus post-lock test;
  controls: 3/3 (layer 14, 2,500 updates). Complete: rank 1 n200 / n5000 /
  control; rank 2 n5000; rank 4 all three sizes and control; rank 8 n1000 /
  n5000.
- Result: every complete run selects layer 14 on validation. At layer 14
  (mean of 3 seeds ± seed SD):

  | Rank | Training set | Updates | Validation | Test (descriptive) | Train, switch-required |
  | --- | --- | --- | --- | --- | --- |
  | 1 | n200 | 100 | 0.265 ± 0.000 | 0.497 | 0.320 |
  | 1 | n200 | 2,500 (control) | 0.265 ± 0.005 | 0.497 | 0.320 |
  | 1 | n5000 | 2,500 | 0.258 ± 0.008 | 0.473 | 0.268 |
  | 2 | n5000 | 2,500 | 0.282 ± 0.015 | 0.470 | 0.273 |
  | 4 | n200 | 100 | 0.253 ± 0.012 | 0.460 | 0.257 |
  | 4 | n200 | 2,500 (control) | 0.250 ± 0.013 | 0.457 | 0.290 |
  | 4 | n1000 | 500 | 0.293 ± 0.016 | 0.490 | 0.287 |
  | 4 | n5000 | 2,500 | 0.300 ± 0.023 | 0.487 | 0.292 |
  | 8 | n1000 | 500 | **0.322 ± 0.006** | 0.483 | 0.305 |
  | 8 | n5000 | 2,500 | 0.305 ± 0.018 | 0.483 | 0.304 |

  The by-layer profile matches the rank sweep (0 at layers 11 and 20,
  peak at 14). Untrained-alignment and no-intervention validation IIA are 0
  everywhere. Across all sizes and ranks, validation stays within
  0.25–0.32: 25× more data or 25× more updates changes it by at most 0.05.
- Why rank and size barely matter (analysis of saved outputs, plus a
  fixed-weight validation evaluation; scripts
  `scripts/adhoc/20261019-rank-data-plateau.py` and
  `scripts/adhoc/20261019-medium-ceiling.py`):
  - Not a bug: saved projections are 1024 × rank and pyvene swaps all rank
    dimensions; update counts are 100 / 500 / 2,500; re-evaluating saved
    alignments reproduces the saved IIA counts exactly.
  - Training finds the same direction every time: the trained rank-1
    direction is far from its random start (cos ≤ 0.08) and nearly
    identical across seeds and training sizes (|cos| 0.90–1.0). Every higher-rank
    subspace contains it (projection 0.91–1.0).
  - Underfitting, not overfitting: with the same 200 pairs, 100 and 2,500
    updates end at the same loss (1.705 vs 1.703) and the same IIA
    (train switch-required 0.320, validation 0.265). Train ≈ validation in
    every run.
  - The site holds little of the decision in Medium. Replacing the whole
    residual vector at N with the source's gives at most 0.105 validation
    IIA (layer 14) in Medium, vs 0.70 at layer 8 in Small. Medium itself
    answers IO top-1 on only 0.79 of validation prompts (Small 0.975) and
    puts " the" top-1 on 0.205.
  - Outcomes pooled over 42 layer-14 conditions (all ranks, sizes, seeds):
    S top-1 0.281, IO still top-1 0.394, another token (mostly " the")
    0.325. 91/200 validation pairs never flip in any condition; on those,
    Medium's own accuracy is 0.57. Counting only S vs IO, IIA is 0.35–0.41;
    the median logit(S) − logit(IO) moves from −3.1 to −0.2 / −0.3
    (Small: −3.1 → +1.6).
  - By object: 40 of Medium's 41 no-intervention " the" answers are on
    "gave a bone to" prompts (40/57; Small 5/57). Pooled layer-14 DAS IIA
    by object: bone 0.03 (" the" top-1 after DAS 0.95), kiss 0.29,
    basketball 0.42, ring 0.43; 0.38 without bone prompts. Small layer 8
    (seed 42): bone 0.61, others 0.90–0.93.
  - Caveat: DAS exceeds the full-residual patch at the same site (Medium
    0.27–0.32 vs 0.105; Small 0.83 vs 0.70). A subspace patch beating the
    full patch is the pattern Makelov et al. (2023) warn about, so part of
    Medium's IIA may use a path the model does not normally use. The
    untrained baseline cannot detect this.
- Evidence: `outputs/data-scale/20261019-gpt2-medium-*` (the ten complete
  runs: `summary.md`, `selection.json`, `layer_summary.csv`, `figures/`).
- Datasets: `train_pool_v1` and nested `train_n200_v1` / `train_n1000_v1` /
  `train_n5000_v1`, built and audited in `c578921`.

### object-names (dropped 2026-11-05)

Never started; dropped by the user's decision (2026-11-02 Amendment). Its
briefs [alignment-transfer-eval](briefs/2026-10-18-alignment-transfer-eval.md)
and
[entity-vocabulary-datasets](briefs/2026-10-18-entity-vocabulary-datasets.md)
are dropped.

### model-scale (done 2026-10-15)

- Goal: rerun the layer-sweep protocol on GPT-2 Medium (24 layers).
  The follow-up (rank, learning rate, budget) was task `rank-sweep`.
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
  alignment barely fits its own training data.
- Evidence: `outputs/model-scale/20261015-gpt2-medium/` (`summary.md`,
  `selection.json`, `layer_summary.csv`, `figures/`).
- Cross-GPU check (not in the repository): on HPC3, the opt-in GPU
  regression (`layer8-seed42`, GPT-2 Small, Slurm job 58156709) reproduced
  every per-epoch and final IIA count of the RTX 2080 Ti reference (train
  173/200, test 79/100) but failed the exact-float check: losses differ at
  about 1e-6 (initial counterfactual loss 2.4105420 vs 2.4105425).
  Output kept on HPC3 under `~/hpc3-checks/`.

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

Last result on `main` (2026-11-05, with the three new adhoc scripts):
282 passed, 1 skipped (opt-in GPU regression), 305 subtests.
