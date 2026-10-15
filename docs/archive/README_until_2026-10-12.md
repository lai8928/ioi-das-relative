# ioi-das-relative

A small IOI research project that separates the causal variable being studied from the token position where an intervention is applied. Phase 0/1 preserves the original POSITION-task sampling rules, saves fixed base/source pairs, and audits factual name anchors and positions relative to each prompt's end. Phase 2 is complete for one GPT-2 DAS condition: layer 8, `block_output`, `END/N`, rank 1, and `target_variable="position"`. The latest execution evidence is in [docs/STATUS.md](docs/STATUS.md).

The implementation brief is [CODEX_IOI_DAS_BOOTSTRAP.txt](CODEX_IOI_DAS_BOOTSTRAP.txt). Read [docs/STATUS.md](docs/STATUS.md) for execution evidence and the continuation command, [docs/PLAN.md](docs/PLAN.md) for contracts and future acceptance criteria, and [docs/UPSTREAM.md](docs/UPSTREAM.md) for attribution, hashes, and documented adaptations.

## Environment and runnable commands

The existing `ioi-das-v2` Conda environment was discovered at `/home/ilingl/.conda/envs/ioi-das-v2/bin/python`. The project uses that interpreter without installing packages or changing CUDA. The inspected versions are Python 3.10.21, torch 2.5.1+cu121, transformers 4.57.6, tokenizers 0.22.2, pyvene 0.1.8, numpy 2.2.6, pytest 9.1.1, and packaging 26.3. Phase 1 uses tokenizers and standard Python code; it does not load language-model weights or require a GPU. Phase 2 uses the existing external pyvene dependency and cached GPT-2 safetensors on CUDA.

Run from this project root:

```bash
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli audit --config configs/audit.json
```

Run the focused checks with the same interpreter:

```bash
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m pytest -q
```

The configuration pins tokenizer `gpt2` to revision `607a30d783dfa663caf39e06633721c8d4cfcd7e` and enables `local_files_only`. Fast tokenizer offsets identify character spans; token IDs are compared with the corresponding slow GPT-2 tokenizer. Only tokenizer assets are needed for the audit. Configuration paths are resolved relative to the config directory and its explicit `project_root`; they do not depend on the process's working directory once the config path is supplied.

## Run the single Phase 2 condition

The model and tokenizer use the same pinned revision and `local_files_only=true`. GPT-2 weights are loaded from the existing cache in float32 with eager attention. The environment and cached model need no dependency changes or weight download. CUDA is required; the experiment fails with an actionable message when a restricted execution sandbox hides the server GPU.

Run a separately labeled smoke check from the project root:

```bash
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib CUDA_VISIBLE_DEVICES=0 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli run --config configs/phase2.json --smoke
```

The smoke check uses 20 saved training pairs, five from each of the four pairings, and four saved test pairs, two from each held-out pairing. It performs one optimizer update. Its artifacts are saved under `outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/smoke/`. Smoke metrics describe this small check and do not replace the full experiment.

Run the configured full condition:

```bash
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib CUDA_VISIBLE_DEVICES=0 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli run --config configs/phase2.json
```

The full run reuses all 200 training and 100 test pairs. Ten epochs with batch size 20 give 100 optimizer updates and 2,000 training presentations. It saves artifacts under `outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/`. A nonempty run directory is preserved and rejected. To repeat the experiment, append `--output-dir outputs/phase2/gpt2-layer8-block-output-N-rank1-repeat1` or another unused root; `smoke/` or `full/` is created below that root.

Only alignment parameters are optimized. GPT-2 remains frozen and in evaluation mode while gradients propagate through its computations to the intervention. The optimizer is Adam with base learning rate 0.01, betas `[0.9, 0.999]`, epsilon `1e-8`, and zero weight decay. The upstream `LinearLR` behavior is preserved explicitly: `start_factor=1/3`, `end_factor=0.1`, `total_iters=10`, stepped after every **batch**. The effective rate starts at approximately 0.0033333, reaches 0.001 after ten updates, and remains there for the other 90 updates. This is the upstream schedule rather than an epoch-based decay.

Factual IOI accuracy and counterfactual IIA use argmax over the entire vocabulary and retain exact counts and unrounded ratios. Both training and evaluation use the same masked intervention forward function, independent base/source locations, and each base's `N` for next-token readout. The test split is used only for evaluation. Preflight and final checks cover nonzero alignment gradients, identity intervention, unchanged model tensor hashes, original mixed lengths, synthetic 18/22-token pairs at `N` and `N-2`, alignment save/reload, and hook cleanup.

| File in each Phase 2 run directory | Purpose |
| --- | --- |
| `config.json`, `environment.json` | Resolved configuration, run kind, exact dependencies, GPU, cached model/tokenizer assets, and hashes. |
| `training_steps.jsonl`, `training.json` | Per-update loss, learning rates, gradients, sample IDs, counts, and epoch aggregates. |
| `initial_train_predictions.jsonl` | Predictions before optimization: 200 rows in the full run. |
| `train_predictions.jsonl`, `test_predictions.jsonl` | Final per-example factual/counterfactual predictions, labels, probabilities, losses, and actual indices: 200/100 rows in the full run. |
| `metrics.json` | Factual accuracy and IIA counts, full-precision ratios, losses, and `mean_target_logit`. |
| `initial_alignment.pt`, `alignment.pt` | Initial alignment and final raw orthogonal state; final checkpoint also retains the effective projection. |
| `validation.json` | Frozen-state, gradient, identity, independent-position, batch/individual, reload, and cleanup evidence. |
| `result.json`, `summary.md` | Completion record with hashes and an English summary. |

Failed runs preserve `failure.json` and any preceding artifacts. The eight-condition sweep and plotting remain later phases.

The completed full run performed all 100 updates on the server's `cuda:0` NVIDIA GeForce RTX 2080 Ti. The saved dataset hashes stayed unchanged. Its actual results are:

| Evaluation | Factual IOI accuracy | Counterfactual IIA |
| --- | --- | --- |
| Training before optimization | 190/200 = 0.95 | 94/200 = 0.47 |
| Training after optimization | 190/200 = 0.95 | 173/200 = 0.865 |
| Held-out test after optimization | 98/100 = 0.98 | 79/100 = 0.79 |

All Phase 2 validation checks passed, including identical GPT-2 state hashes, exact identity logits, independent positions and masks, checkpoint reload, and cleanup. The test suite passed 15 tests and 305 subtests. The full run took approximately 34.37 seconds and reported 672.9 MiB peak PyTorch allocated GPU memory. See [full-run metrics](outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/metrics.json), [validation](outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/validation.json), and [completion evidence](outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/result.json). The separate one-update smoke run's test IIA was 0/4 and is not the full-run result. To run either command again, use a new `--output-dir` because these evidence directories are already populated.

## Inspect the Phase 2 process in a notebook

Open [notebooks/phase2_walkthrough.ipynb](notebooks/phase2_walkthrough.ipynb) to follow the saved experiment from data construction and token positions through the intervention, optimization, predictions, and validation. The executed notebook contains 34 cells, 20 code cells, and 12 embedded figures. The saved outputs can be read without starting a kernel.

For interactive inspection, open the notebook in an editor or Jupyter connected to this server, select the existing **Python (ioi)** kernel, and run the cells in order. That viewer kernel has different package versions from the recorded training environment; the first cell shows both contexts. The original `ioi-das-v2` interpreter has no `ipykernel` installed. The embedded outputs were executed with that interpreter using an in-process IPython shell, as recorded in the notebook metadata and [execution.json](outputs/notebooks/phase2_walkthrough/execution.json). No kernel registration or package installation was needed.

**Run All reads the completed artifacts and renders figures.** It performs no language-model load, optimizer update, or sweep. The walkthrough verifies the saved run, dataset, configuration, and experiment-source hashes, then recomputes accuracy counts from the saved predictions. It distinguishes online epoch measurements from final fixed-weight evaluation, and same-pattern training identity pairs from cross-pattern examples.

Use these editable values to inspect specific details:

| Control | What to inspect |
| --- | --- |
| `PROJECT_ROOT_OVERRIDE`, `RUN_DIR_OVERRIDE` | Select a different checkout or full-run artifact directory. Leave both as `None` for this project. |
| `SAMPLE_ID` | Select a saved base/source pair for factual roles and token-position diagrams; rerun that cell and the following token cell. |
| `STEP_TO_INSPECT` | Select an update from 1 to 100 to see its exact training sample IDs. |
| `EXAMPLE_IDS` | Compare saved predictions and initial/final target probabilities for selected training examples. Test examples show final results only. |
| `DETAIL_ID` | Display one pair's complete prompts, targets, argmax predictions, probabilities, and counterfactual loss. |

Start with `train-0050` for a successful POSITION intervention, `train-0054` for a target-probability increase that still misses the argmax, and `test-0004` for a pronoun prediction that fails full-vocabulary IIA. Training IDs range from `train-0000` to `train-0199`; test IDs range from `test-0000` to `test-0099`.

To rebuild and execute the walkthrough offline with the existing training interpreter, run:

```bash
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B /home/ilingl/projects/ioi-das-relative/scripts/render_phase2_notebook.py --project-root /home/ilingl/projects/ioi-das-relative
```

This command refreshes the notebook and its analysis exports under [outputs/notebooks/phase2_walkthrough/](outputs/notebooks/phase2_walkthrough/). It preserves the completed Phase 2 run and saved datasets. Each figure is exported as PNG and SVG in [figures/](outputs/notebooks/phase2_walkthrough/figures/); [overview.json](outputs/notebooks/phase2_walkthrough/overview.json) records recomputed metrics and alignment geometry, and [figure_manifest.json](outputs/notebooks/phase2_walkthrough/figure_manifest.json) records export hashes. The effective alignment direction is reconstructed from saved raw tensors on CPU, with no GPT-2 execution.

## Conda selection and GPU diagnostics

The project-local `.conda` prefix was created with Python 3.11 only. At inspection it has Python 3.11.17, pip, and packaging, but lacks torch, transformers, tokenizers, numpy, pyvene, and pytest. Creating a prefix does not activate it or install project dependencies. The existing `ioi-das-v2` prefix has the dependencies needed for the completed checkpoint.

Use the verified existing environment to test the entire implemented Phase 0/1 checkpoint:

```bash
cd /home/ilingl/projects/ioi-das-relative
source /home/ilingl/miniforge3/etc/profile.d/conda.sh
conda activate /home/ilingl/.conda/envs/ioi-das-v2
export PYTHONPATH="$PWD/src"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python -B -m pytest -q
python -B -m ioi_das.cli audit --config configs/audit.json
CUDA_VISIBLE_DEVICES=0 python -B -m ioi_das.cli doctor --require-gpu --output outputs/environment/manual-gpu.json
```

The `doctor` command prints the actual interpreter, installed dependency versions, selected environment variables, and optional GPU evidence. With `--require-gpu`, it runs a small float32 CUDA matrix multiplication, synchronizes, and verifies the result and device. Missing dependencies or unavailable CUDA cause exit code 2; it never silently substitutes a CPU operation. `--device cuda:0` selects a logical device after `CUDA_VISIBLE_DEVICES` mapping. Setting `CUDA_VISIBLE_DEVICES=0` exposes physical GPU 0 as logical `cuda:0`.

The server check observed seven NVIDIA GeForce RTX 2080 Ti GPUs with 11 GiB each and NVIDIA driver 535.129.03. Using `ioi-das-v2` (torch 2.5.1+cu121, CUDA runtime 12.1), the actual 256x256 matrix multiplication passed on `cuda:0`. This proves CUDA availability for the selected environment. The Phase 1 tokenizer audit itself runs on CPU; this diagnostic does not train DAS or load a language model.

Machine-readable reports are under `outputs/environment/`: `project-conda.json` records missing local dependencies, `ioi-das-v2-server.json` records the successful server GPU operation, and `ioi-das-v2-sandbox.json` records the restricted tool sandbox's lack of GPU visibility. The sandbox result does not describe the server driver's health.

To inspect the local prefix without activating or changing it:

```bash
PYTHONPATH=src .conda/bin/python -B -m ioi_das.cli doctor
```

No packages were installed into either environment during inspection. Prefer the verified existing environment until the project-local prefix is explicitly provisioned.

## Saved artifacts

The initial audit creates or validates `data/generated/train.jsonl`, `data/generated/test.jsonl`, and `data/generated/manifest.json`. These retain 200 training pairs and 100 test pairs, textual roles, occurrence spans, counterfactual names, generator revision, seed, tokenizer metadata, and file hashes. Repeated runs reuse the saved examples across conditions. These are newly generated fixed samples rather than a reconstruction of historical examples.

Audit artifacts under `outputs/audit/` are:

| File | Purpose |
| --- | --- |
| `pairs.jsonl` | Stable pair IDs, separate base/source tokens and masks, valid lengths, name spans, resolved anchors, and answer-token checks. |
| `summary.json` | Machine-readable aggregate audit evidence. |
| `summary.md` | English summary with a small subset of examples of different lengths and both patterns. |
| `focused_checks.json` | Focused role, counterfactual, occurrence, padding, unequal-length, invalid-offset, and unsupported-answer evidence. |
| `environment.json` | Interpreter and installed package versions used for the run. |

`GOAL_NAME` selects the factual indirect object's occurrence within each input. The scalar anchor is the last token of that complete name span. `N` is the last non-padding input token, and `N-k` is resolved independently for every base and source. Model readout remains at base `N` regardless of the intervention location. Unsupported multi-token answers are preserved and reported instead of silently taking their first token.

The completed audit covers all 300 pairs: 600 input and 1,800 answer-continuation comparisons agree between fast and slow GPT-2 tokenizers, and 2,400 batch/individual position comparisons agree. All original-rule answer checks support single-token evaluation. Training prompts have lengths 15 or 19; test prompts range from 14 to 20 tokens. Preserved source resampling gives equal lengths within these sampled pairs, so separately labeled synthetic 18/22-token pairs verify unequal-length behavior. Focused checks also diagnose invalid offsets and retain an unsupported two-token `Mary Jane` answer. See [audit evidence](outputs/audit/summary.md) and [current status](docs/STATUS.md) for the final validation record.

## Source and scope

Eight upstream files are preserved unchanged under `vendor/pyvene_upstream/` at Stanford pyvene commit `9e333904dcf9e597ca76170010d17f4d4580de8d`, with machine-readable [provenance](vendor/pyvene_upstream/provenance.json). Adapted generation code credits [activation-patching-illusion](https://github.com/amakelov/activation-patching-illusion), as upstream does. The upstream Apache 2.0 license is included in `vendor/pyvene_upstream/LICENSE`.

The implementation includes `data.py`, `tokenization.py`, `positions.py`, `checks.py`, `audit.py`, `environment.py`, `intervention.py`, `train.py`, `evaluate.py`, `validation.py`, `experiment.py`, and the CLI. The current request authorizes the single Phase 2 condition. Phases 3–4 remain plans; no sweep runner or plotting module is implemented.
