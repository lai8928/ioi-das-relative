# Status

Updated: 2026-10-15 · Cycle since: [2026-10-12](meetings/2026-10-12.md)

## Tasks

| ID | Title | Status | Since | Formerly |
| --- | --- | --- | --- | --- |
| `position-audit` | Original IOI data and per-example position audit | done | 2026-10-12 | Phase 0–1 |
| `single-condition-das` | One DAS run: GPT-2 Small, layer 8, N, rank 1 | done | 2026-10-12 | Phase 2 |
| `layer-sweep` | Every layer at the last token, GPT-2 Small | active (rebuild on `main`) | 2026-10-12 | M3 / A |
| `model-scale` | Same protocol on a larger GPT-2 | active | 2026-10-12 | M4 / B |
| `data-scale` | Larger training sets | active | 2026-10-12 | M5 / C |

## Config/pipeline implementation

- Branch: `feat/config-pipeline`; implementation commit `748cb37`. Not merged.
- Brief: `docs/briefs/2026-10-15-config-pipeline.md`. All six acceptance
  items passed; no remaining blockers for this brief.
- Implemented inherited, immutable schema-validated configs, ordered grids,
  per-condition runs, source/data/artifact hash verification on resume,
  clean-source checks, and saved-file-only CSV/Markdown/SVG reports.
- Resolved reference config SHA-256 (canonical settings plus grid order):
  `f9c74ce47dc4ac9a94c090a533d6628544e0cdf93fb5a5ae850f898243015f5b`.

Acceptance results:

1. Suite: **79 passed, 305 subtests passed, no skips**, 11.66 s. Includes
   `test_conventions.py` and the opt-in GPU regression against the completed
   real GPU run. The preceding default suite passed 78 tests and skipped only
   that opt-in regression.
2. Audit: passed; reused 200 train / 100 test pairs, 0 unsupported answer
   checks. New evidence: `/tmp/ioi-das-audit-czpw59ra/summary.md`. Existing
   completed audit, registered data, upstream originals, legacy configs,
   notebook, and legacy outputs are byte-for-byte unchanged from `0876518`.
3. Final smoke from committed source: complete on physical GPU 6,
   `outputs/single-condition-das/smoke-20261015-layer8-seed42-3/`;
   `run.json`, one update, 20 train / 4 test pairs. This is execution
   evidence, not a full scientific result.
4. Full run: `outputs/single-condition-das/20261015-layer8-seed42/`, condition
   `conditions/intervention.layer=8/seed=42/`. `run.json` records commit
   `911272137f13ee992f13b97e73b428b8f38f8054`, `clean_tree=true`, and
   `protected_tree_clean=true` before output allocation. Initial train IIA
   **94/200**, final train IIA **173/200**, descriptive test IIA **79/100**.
   Every initial/final raw alignment tensor passes `torch.equal`; all 500
   per-example prediction records and 100 per-update records match exactly
   (only update timing excluded). All aggregate metrics and `training.json`
   also match exactly. 100 optimizer updates; 33.600745506584644 s;
   GPU peak allocation 705610240 bytes. Both checkpoint file SHA-256s also
   match the original reference:
   - `initial_alignment.pt`:
     `250b53cce7164a4a346287d620ebf36ffad40944cb39d6fe41c84aff1915e5c0`
   - `alignment.pt`:
     `99e0b38582a600437b54480cd4fe654b06a9bb7adaa220f79d956e03a918c148`
   - Full `run.json`:
     `d5e6832537971f01ea17c80c85ced02f82f7ea41d99fa759f174e9561a93ab86`
   - Condition `result.json`:
     `3d0bd28b30b4917ffcf07d959cfa46628ed6648f1e5f5672d56b07ebb90ccd74`
5. Actual full-run `report --experiment-dir` passed. A separate import
   blocker verified no torch/transformers/pyvene import; rebuilt CSV,
   Markdown, and SVG bytes are identical and all source artifacts unchanged.
6. The exact source grep below returned no matches (expected exit status 1).

Additional checks: completed full-run resume verified hashes, performed no
training, and preserved all 16 files including mtimes. Focused tests cover
corruption rejection, preserved completed/partial conditions, exact named
schedule/shuffle behavior, and report failure handling. `doctor` passed
without loading model weights or training. No packages or weights were
installed or downloaded.

Retained attempts:

- `outputs/single-condition-das/smoke-20261015-layer8-seed42/`: failed because
  sandbox CUDA was unavailable; its original failed run metadata is retained.
- `outputs/single-condition-das/smoke-20261015-layer8-seed42-2/`: completed
  during development and superseded by final smoke because source files
  changed during it. Its original metadata and artifacts are retained.
- GPU smoke/full commands ran outside the sandbox with approval, after
  `nvidia-smi` confirmed physical GPU 6 was idle.

Dataset hashes remained:

- Train: `3867b316d469df4b4c2d80136324c8cda4e001c617c584c30703283ad75db346`
- Test: `dd7e6de16f4ccb0e295086ba97d80abf8b6bcda01852f1ee8bb61ff3154f8ded`
- Manifest: `9f47c403b39c12b93f3d27d4e26416e081172914f276f9bc7fdcd1f6eb44653c`

Frozen notebook: its source-integrity cell still refers to commit `e7477e4`;
it was not changed or re-rendered. New source hashes naturally differ from
those saved in the historical notebook.

Commands executed (project root, existing Conda interpreter):

```bash
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m pytest -q
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli audit --config configs/audit.json
env CUDA_VISIBLE_DEVICES=6 PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli run --config configs/single-condition-das/layer8-seed42.json --smoke
env CUDA_VISIBLE_DEVICES=6 PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli run --config configs/single-condition-das/layer8-seed42.json
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib IOI_DAS_RUN_GPU_REGRESSION=1 IOI_DAS_REGRESSION_DIR=outputs/single-condition-das/20261015-layer8-seed42 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m pytest -q
env PYTHONPATH=src /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli report --experiment-dir outputs/single-condition-das/20261015-layer8-seed42
env PYTHONPATH=src /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B /tmp/ioi_das_verify_report.py outputs/single-condition-das/20261015-layer8-seed42
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B /tmp/ioi_das_verify_resume.py outputs/single-condition-das/20261015-layer8-seed42
git grep -nE "phase ?[0-9]|Phase ?[0-9]|m[0-9]_|milestone" -- src
git diff --exit-code 0876518 -- data/generated vendor outputs/audit outputs/audit-manual-check outputs/environment outputs/notebooks outputs/phase2 configs/audit.json configs/phase2.json notebooks
```

Exact next command (review only; merge is not authorized):

```bash
git diff --stat main...feat/config-pipeline
```

## layer-sweep

- Goal: independent rank-1 DAS at block_output, last token N, every layer,
  seeds 42/43/44; choose the layer on validation only.
- Where: branch `m3-complete-20261015`, commit `d78221c`. Not yet on `main`.
  - Config: `configs/m3_end_layer_sweep.json`
  - Validation data: `val_indist_v1` (see `data/REGISTRY.md`)
  - Experiment: `outputs/m3_end_layer_sweep/m3_20261015_a/` (summary.md,
    selection.json, layer_summary.csv, figures/)
  - Smoke: `outputs/m3_end_layer_sweep/m3_smoke_20261015_a/`
- Result: 36/36 conditions complete; layer 8 selected (validation 0.83, test
  0.79); layer 9 validation 0.64, layer 7 0.17, all other layers ≤ 0.02. Seed
  SD < 0.01 everywhere. Layer 8 / seed 42 reproduces `single-condition-das`
  exactly. About 31 s and 0.7 GB peak GPU memory per condition.
- Next: rebuild on `main` with the generic config/pipeline. The branch code
  (`m3.py`, `m3_data.py`, `plot.py`) is not merged; its results serve as the
  parity reference for the rebuild.

## model-scale

- Goal: rerun the layer-sweep protocol on GPT-2 Medium (24 layers).
- State: not started.
- Blockers:
  - `load_model` accepts only `name == "gpt2"`
    (`src/ioi_das/intervention.py`).
  - Only `models--gpt2` is in the local HuggingFace cache; GPT-2 Medium needs a
    download, which requires user approval.
- Estimate: 72 conditions (24 layers × 3 seeds); Medium is roughly 3× Small
  per condition, so a few hours on one RTX 2080 Ti (11 GB). All 7 GPUs were
  idle at 2026-10-15 02:40.

## data-scale

- Goal: IIA versus training size (200 / 1000 / 5000 pairs) at a fixed layer.
- State: not started.
- Blocker: `generate_pairs` is fixed at 50 pairs per pattern combination
  (`src/ioi_das/data.py`); the training name pool has 49 names and 2 templates,
  so unique-prompt limits must be checked before choosing sizes.

## Closed tasks

### position-audit (done 2026-10-12)

All 300 legacy pairs audited with the real GPT-2 tokenizer: 600 fast/slow
input comparisons, 1,800 continuation comparisons, and 2,400 batch/individual
position comparisons agree; 0 unsupported answers. Evidence:
`outputs/audit/summary.md`. Details:
`archive/STATUS_until_2026-10-12.md`.

### single-condition-das (done 2026-10-12)

GPT-2 Small, layer 8, block_output, N, rank 1, seed 42: train IIA 0.47 →
0.865, test IIA 0.79; all correctness checks passed. Evidence:
`outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/`. Walkthrough:
`notebooks/phase2_walkthrough.ipynb`. Details:
`archive/STATUS_until_2026-10-12.md`.

## Verification on main

```bash
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m pytest -q
```
