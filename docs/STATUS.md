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
