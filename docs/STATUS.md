# Phase 2 checkpoint and prior evidence

Completed on 2026-10-12 (America/Los_Angeles). Project root: `/home/ilingl/projects/ioi-das-relative`.

Phase 0, Phase 1, and the authorized Phase 2 single condition are complete. Phase 2 loaded existing cached GPT-2 weights and trained only the alignment on the server GPU. No packages were installed, no model weights were downloaded, and no Python/CUDA/system environment was changed. Phase 3/4 and a multi-condition sweep remain unstarted and require a new request.

Earlier follow-up on 2026-10-12: inspected the newly created project-local Conda prefix, reran Phase 0/1, and verified an actual CUDA matrix multiplication on the server. The added `doctor` command is an environment diagnostic. The user subsequently authorized the Phase 2 run recorded below.

GitHub follow-up on 2026-10-12: the user explicitly authorized creating a new personal repository and uploading this checkpoint. The private repository is `lai8928/ioi-das-relative`: https://github.com/lai8928/ioi-das-relative. Git was initialized in this project, using branch `main` and the personal account's noreply commit identity. This later authorization supersedes the bootstrap restriction on repository creation and pushing; the restriction on later experiment phases remains in effect.

## Completed Phase 2 condition

Configuration: `configs/phase2.json`. Model and tokenizer: GPT-2 at revision `607a30d783dfa663caf39e06633721c8d4cfcd7e`, cached safetensors, float32, eager attention. Condition: zero-based layer 8 (`transformer.h[8]`), `block_output`, END/N, rank 1, `target_variable="position"`; readout remains each base N. Runtime: `/home/ilingl/.conda/envs/ioi-das-v2/bin/python`, CUDA logical device 0 / physical GPU 0, NVIDIA GeForce RTX 2080 Ti.

The full run reused exactly the saved 200 training / 100 test pairs, with unchanged file and manifest hashes. It completed 10 epochs, batch size 20, 100 optimizer updates, and 2,000 training presentations. Only 768 alignment parameters were trainable. GPT-2's 124,439,808 parameters remained frozen and in eval mode; autograd remained active through downstream model operations during alignment training.

| Metric | Numerator / denominator | Full-precision ratio |
| --- | --- | --- |
| Initial train IIA | 94 / 200 | 0.47 |
| Final train IIA | 173 / 200 | 0.865 |
| Held-out test IIA | 79 / 100 | 0.79 |
| Train factual accuracy | 190 / 200 | 0.95 |
| Test factual accuracy | 98 / 100 | 0.98 |

Train counterfactual loss measured before/after alignment: 2.4105425281450152 -> 0.9297437125071883. Online epoch mean loss: 2.110920417308807 at epoch 1 -> 0.9336423873901367 at epoch 10. Full run elapsed time recorded in `result.json`: 34.36936328187585 seconds; peak allocated GPU memory: 705,610,240 bytes (approximately 672.9 MiB). These timings describe this run, not a benchmark.

Full artifacts: `outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/`.

- `config.json`: resolved configuration and explicit full-run label.
- `environment.json`: actual interpreter/packages/CUDA/model device, model/tokenizer asset hashes, and empty dependency-change list.
- `training_steps.jsonl`: all 100 shuffled batches, sample IDs, loss, exact correct/total counts, gradient norms, and learning rates before/after each update.
- `training.json`: epochs, counts, schedule, presentation total, and aggregate training results.
- `initial_train_predictions.jsonl`, `train_predictions.jsonl`, `test_predictions.jsonl`: 200 + 200 + 100 full-vocabulary factual/counterfactual predictions, labels, scores, lengths, positions, and base-N readouts.
- `metrics.json`: counts and full-precision factual accuracy / IIA, losses, and `mean_target_logit`; no mislabeled KL divergence.
- `initial_alignment.pt`, `alignment.pt`: raw orthogonal-parametrization state; the final checkpoint also includes the effective 768x1 projection and condition/model metadata.
- `validation.json`: actual pretrained-model checks before and after optimization, saved-weight reload, and cleanup evidence.
- `result.json`, `summary.md`: condition/result summary, source/config/dataset hashes, artifact hashes, and English readable results.

The separate smoke directory `.../smoke/` contains a balanced 20-training-pair / 4-test-pair, one-update run. Its test IIA was 0/4. It is only a pipeline check and is not the full 79/100 result. The full run started from a fresh seeded intervention, not the smoke checkpoint.

## Phase 2 implementation and compatibility

New modules: `intervention.py`, `train.py`, `evaluate.py`, `experiment.py`, and `validation.py`; the CLI adds `run`. The existing generation, tokenization, and position modules are reused unchanged. No `run_sweep()` or plot/training extension is implemented. `AGENTS.md` and `docs/PLAN.md` now reflect the user's explicit Phase 2 authorization.

The optimizer/scheduler follow the preserved upstream exactly: Adam nominal LR 0.01, betas [0.9, 0.999], eps 1e-8, weight decay 0; LinearLR start factor 1/3, end factor 0.1, total_iters 10, stepped every batch. Thus the effective initial LR is 0.003333333333333333, reaches approximately 0.001 after the first 10 updates, and stays there through update 100. This unusual schedule is intentional compatibility with the tutorial; it was not changed to epoch stepping. NumPy RandomState(seed) preserves upstream MT19937 permutation behavior while keeping shuffle state independent of validation.

Intentional fixes: remove the fixed-18-token assumption; pass both sides' attention masks; resolve source/base indices independently; retain each base-N readout; keep full-precision metrics and strict actual-continuation labels; preserve gradient flow through a frozen language model. Installed pyvene 0.1.8 globally removes model hooks during cleanup; a project-local subclass instead tracks and removes only condition-owned handles, including after failed forwards. No installed package was patched. The optional nnsight-backend notice requires no installation for the native pyvene backend used here.

The initial smoke invocation exposed a PyTorch 2.5.1 allocator-statistics initialization requirement (`Invalid device argument` before model loading). Explicit CUDA device initialization before resetting peak-memory statistics resolved it without an environment change. Matplotlib's optional import cache uses writable `/tmp/ioi-das-relative-matplotlib` via a process environment variable.

## Phase 2 validation evidence

The full pretrained run passed:

- Nonzero finite alignment gradients with no language-model gradients, both before and after training. Initial validation gradient norm: 0.37450703453877865; trained validation norm: 1.0021908913053563. Validation used zero optimizer steps and left alignment state unchanged.
- Every language-model parameter and buffer remained bit-identical. SHA-256 before and after: `0a55e4d995d2759030f7d4c2f85983069c42db3bbc6b91e456cbf941dce43d1b`. Raw alignment state changed and remained finite.
- Identity intervention (each base as its own source at matching indices) reproduced factual logits exactly: maximum difference 0, before and after learning.
- Complete 50,257-vocabulary logits for actual saved mixed-length inputs agreed between batched and individual forwards with documented `atol=1e-4`, `rtol=1e-4`; argmax predictions matched. The trained actual-batch maximum absolute difference was 0.00025177001953125, within the combined absolute/relative tolerance.
- Separately labeled synthetic base/source lengths 18/22 and 22/18 validated independent masks, END indices [17,21] versus [21,17], and N-2 intervention with readout still at base N. Synthetic cases never entered training or research metrics.
- Raw saved alignment state reloaded and reproduced exact readout logits.
- No condition-owned hooks or activation caches remained after cleanup. Unrelated hooks and failed-forward cleanup are also covered by focused tests.

Independent artifact verification is saved separately in `outputs/phase2/verification.json`, leaving the full-run artifacts immutable. It recomputed all 13 run-file hashes, all 13 module hashes, config/manifest/dataset hashes, and all metrics from 500 retokenized prediction rows. It verified 100 updates with every training ID presented exactly ten times, the exact seeded shuffle order and per-batch learning-rate schedule, finite/nonzero gradients, recorded CUDA device, and unchanged installed versions. A fresh CPU intervention strictly loaded the saved initial/final raw state and reconstructed the final effective 768x1 projection within 5.960464477539063e-08; its norm was 0.9999999403953552. This independently validates recovery of the learned direction beyond the same-pattern logits reload probe. No extra language-model load or training was used for this verification.

Test command run successfully:

```bash
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m pytest -q
```

Result: `15 passed, 305 subtests passed in 15.38s`. The four new tests use a small random nine-layer GPT-2 and the real pinned tokenizer; they validate gradients/frozen state, identity, batching, hook preservation/failure cleanup, unsupported answers, and full-vocabulary evaluation counts. They are separate from the completed real pretrained GPT-2 GPU run.

Exact full-run command executed:

```bash
env PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib CUDA_VISIBLE_DEVICES=0 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli run --config configs/phase2.json
```

The same command with `--smoke` executed the separate pipeline check. CUDA commands required execution outside the tool sandbox, whose NVIDIA devices are hidden. The existing Conda environment, tokenizer cache, and model cache met all prerequisites; no dependency changes were needed.

## Current blockers and exact next command

No unresolved Phase 2 acceptance blockers remain. Preserve both run directories, the original datasets, and the pretrained cache. Phase 2 CLI refuses nonempty run directories; an intentional repeat requires a new `--output-dir`, with the same configuration and data. Results reflect one seed and one condition; no selection or tuning used the held-out test split.

The next action is to inspect the completed evidence, without starting another run:

```bash
cat /home/ilingl/projects/ioi-das-relative/outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/summary.md
```

For an explicitly requested repeat, preserve the old run and use the full command above with `--output-dir outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42-repeat`. Do not begin Phase 3, a multi-condition sweep, or hyperparameter tuning without a new request. The Phase 2 source and artifacts are included in the follow-up GitHub synchronization checkpoint described below.

## Detailed notebook walkthrough

The user requested a detailed notebook with figures after Phase 2 completion. Created `notebooks/phase2_walkthrough.ipynb`, with 34 cells, 20 executed code cells, and 12 embedded PNG figures. The explanations, source excerpts, plot labels, and CLI remain in English. This is a saved-result walkthrough of the completed condition, not a new training run or Phase 3 sweep.

The notebook verifies the source run, experiment modules, configuration, and fixed dataset hashes before interpreting them. It then shows the original splits and prompt lengths; a selectable base/source example with IO/S1/S2 and full token tables; GOAL_NAME/N/N-1/N-2 positions; a rank-1 transfer schematic and real implementation excerpts; every saved optimizer update; online loss/IIA, actual per-batch learning rate, and gradient norms; final metrics and pairing-specific scores; selectable predictions and failures; initial/final effective directions; and frozen-state/identity/batching/reload/cleanup evidence. It includes separate synthetic 18/22-token position diagrams.

Important interpretation retained in the viewer:

- Half the training pairs are identical-input identity cases. Cross-pattern train IIA changes from 0/100 to 79/100; overall final train IIA 173/200 also includes 94 correct identity pairs. Test contains cross-pattern pairs only.
- Epoch-10 online IIA is 172/200, whereas fixed final-weight train evaluation is 173/200. The plot labels distinguish these measurements.
- Test outcomes are 79 counterfactual targets, 13 retained base factual IO names, and 8 other vocabulary tokens (six ' her', two ' his'). Full-vocabulary argmax matters.
- No initial test predictions, per-step/epoch alignment checkpoints, full top-k distributions, or hidden activations were saved. The notebook does not invent those histories or treat descriptive length groups as causal evidence.
- Raw orthogonal state is reconstructed with the same PyTorch parametrization for initial/final direction plots; the raw parameter is not mislabeled as the effective direction. The final projection matches the saved effective tensor within 1.043081283569336e-07.

Controls are ordinary editable notebook variables: `PROJECT_ROOT_OVERRIDE`, `RUN_DIR_OVERRIDE`, `SAMPLE_ID`, `STEP_TO_INSPECT`, `EXAMPLE_IDS`, and `DETAIL_ID`. Held-out-only selections show final-only results, because initial test predictions do not exist. Unknown example IDs produce an actionable error instead of an empty or misleading chart.

Exports are separate from immutable experiment outputs: `outputs/notebooks/phase2_walkthrough/figures/` contains 12 PNG and 12 SVG files. `overview.json` contains recomputed metrics, outcome counts, and projection geometry; `figure_manifest.json` fingerprints the displayed exports; `execution.json` records the notebook hash, actual executor/interpreter, cell and embedded-image counts, and zero training updates. Core package modules, original data, and full Phase 2 artifacts were not modified.

Execution used the existing `/home/ilingl/.conda/envs/ioi-das-v2/bin/python` with nbformat 5.11.1, IPython 8.39.0, matplotlib 3.10.9, pandas 2.3.3, and numpy 2.2.6. This environment lacks ipykernel/jupyter_client, so `scripts/render_phase2_notebook.py` executes the cells in-process through IPython and captures actual text/HTML/PNG outputs. The executor is explicitly labeled; it is not presented as a nbclient or Jupyter-kernel run. No package or environment changes were applied.

The notebook metadata selects the already registered `ioi` kernel for interactive viewing. Its interpreter is `/home/ilingl/miniforge3/envs/ioi/bin/python`; its torch/transformers versions differ from the recorded training environment. The setup cell reports both contexts. Saved-artifact analysis and CPU alignment inspection do not retrain under this alternative environment. Embedded outputs are viewable without executing any cell.

The final notebook was also verified through that actual existing Jupyter kernel: all 20 code cells passed, 12 PNG outputs were observed, and the held-out-only EXAMPLE_IDS interaction passed. Hashes confirmed 62 original input/canonical export files were unchanged. Evidence is in `outputs/notebooks/phase2_walkthrough/interactive_kernel_check.json`. The sandbox blocked local Jupyter sockets; the normal outside-sandbox retry succeeded. No compatibility issue or dependency change remains. nbformat validation, 20 sequential execution counts, no error outputs, 12 embedded figures, and all 24 PNG/SVG export hashes passed independently.

Exact command used to regenerate and execute the notebook and export figures:

```bash
cd /home/ilingl/projects/ioi-das-relative
env MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib IPYTHONDIR=/tmp/ioi-das-relative-ipython /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B scripts/render_phase2_notebook.py
```

Expected result: 20 code cells executed successfully, valid nbformat, 12 embedded figures, and zero language-model loads / optimizer updates. The next viewing action is to open `notebooks/phase2_walkthrough.ipynb` in the notebook editor and read its existing outputs from top to bottom.

## Workspace and environment inspection

The initial directory contained the implementation brief and empty managed metadata directories. No applicable ancestor or project `AGENTS.md` existed. `git status --short` returned `fatal: not a git repository`; the empty managed `.git` directory is not a working repository. No repository, remote, commit, or push was created. This directory is the project root, rather than a nested copy of an existing project.

The existing environment was discovered through `/home/ilingl/.conda/environments.txt`. Actual interpreter: `/home/ilingl/.conda/envs/ioi-das-v2/bin/python`, Python 3.10.21. Installed versions recorded in `outputs/audit/environment.json`: torch 2.5.1+cu121, transformers 4.57.6, tokenizers 0.22.2, pyvene 0.1.8, numpy 2.2.6, pytest 9.1.1, packaging 26.3. pyvene is an external optional dependency for later phases and is not imported by this prototype.

The cached GPT-2 tokenizer at revision `607a30d783dfa663caf39e06633721c8d4cfcd7e` supports fast offsets and the corresponding slow reference tokenizer. Every audit uses this revision with `local_files_only=true`. Tokenizer asset paths and SHA-256 hashes are in the runtime evidence. No tokenizer download was necessary.

## Completed artifacts

- Eight unchanged originals from Stanford pyvene commit `9e333904dcf9e597ca76170010d17f4d4580de8d`, preserving repository-relative paths under `vendor/pyvene_upstream/`. `docs/UPSTREAM.md` and `vendor/pyvene_upstream/provenance.json` record retrieval URLs, date, byte counts, hashes, attribution, module mappings, and adaptations.
- `README.md`, `AGENTS.md`, `docs/PLAN.md`, and this continuation record. `pyproject.toml` is this project's own configuration, not a copy of upstream packaging.
- `src/ioi_das/data.py`: original-rule sampling, construction-time occurrence spans, roles, POSITION counterfactual names, deterministic JSONL persistence, and corruption diagnostics.
- `src/ioi_das/tokenization.py`: pinned fast/reference GPT-2 encoding, full name token spans, actual continuation checks, separate right-padded base/source batches with attention masks, and independent batch-tokenizer validation.
- `src/ioi_das/positions.py`: per-example GOAL_NAME/IO/S1/S2/END/N anchors and offsets; separate base/source arrays; invalid-anchor and bounds diagnostics.
- `src/ioi_das/audit.py`, `checks.py`, and `cli.py`: config-based saved-data reuse, integrity validation, full audit, focused evidence, English summaries, and runnable CLI.
- `configs/audit.json`, fixed `data/generated/train.jsonl` / `test.jsonl`, their `manifest.json`, four focused test files, and complete `outputs/audit/` evidence.

Only the documented deterministic ordering change alters sampling implementation: `list(set(pattern))` becomes first-occurrence symbol order. The original splits, 50-pair combination blocks, RNG draw order, source resampling, and counterfactual rule are preserved. Saved samples are new reproducible examples, not historical tutorial samples. Reusing them with another tokenizer is supported without changing the text dataset; the manifest retains the tokenizer used at generation and each audit records its own tokenizer.

## Validation evidence

Full real-tokenizer audit command executed successfully:

```bash
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli audit --config configs/audit.json
```

The initial run created the dataset. Subsequent runs verified hashes and reported `Dataset reused`. One successful repeat ran from `/tmp` with absolute source/config paths, confirming artifact paths do not depend on the current directory.

`outputs/audit/summary.json`, `pairs.jsonl`, `summary.md`, `focused_checks.json`, and `environment.json` provide the complete evidence:

- All 200 training pairs audited: ABB->ABB, ABB->BAB, BAB->ABB, BAB->BAB, 50 each.
- All 100 test pairs audited: ABB->BAB and BAB->ABB, 50 each.
- 600 full input encodings and 1,800 actual answer continuations matched the slow GPT-2 reference. All 1,800 original-rule answer checks supported one continuation token and preserved the prompt boundary; unsupported count was zero.
- Both fast and slow real batch encodings agreed with individual encoding plus right padding on 30 base/source batch sides.
- 2,400 GOAL_NAME/N/N-1/N-2 batch-versus-individual position comparisons passed. Every readout index remained at base N.
- All occurrence spans decode to the intended factual IO or first/second subject occurrence. No prompts were truncated, discarded, rewritten, or extended with an answer.
- Training valid lengths: 15 tokens (87 pairs), 19 (113). Test lengths: 14 (17), 15 (45), 16 (7), 17 (11), 18 (10), 20 (10). Base/source lengths agree within all original-rule pairs because sources preserve the template, object/place, and single-token name multiset.
- The separately labeled synthetic mixed batch uses base lengths [18, 22] and source lengths [22, 18]. Literal expected N-1 indices are base [16, 20] and source [20, 16]; END/END-1/END-2 and factual name anchors agree with independent tokenization. These synthetic cases are excluded from research samples.
- Invalid anchors, out-of-range offsets, and left-padding masks produce sample-specific actionable diagnostics. A synthetic Mary Jane answer retains both tokens [5335, 12091], is marked `unsupported_multi_token`, and has no scalar answer token. Its GOAL_NAME selects the last token of its full span.

Focused test command:

```bash
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m pytest -q
```

Final result: `11 passed, 305 subtests passed`. Checks include hand-derived roles and unrelated-name source counterfactuals, repeated-name occurrence spans, original split boundaries and counts, JSONL corruption diagnostics, a dependency-free AST extraction of upstream methods compared against all 300 generated pairs, complete dataset SHA-256 equality across two PYTHONHASHSEED values, real-tokenizer mixed batches, and protection against silent regeneration on hash/seed changes. Dataset reuse preserves file bytes and modification times. A separate read-only review independently checked all 300 output rows, 600 prompt records, 1,800 answers, positions, masks, and artifact hashes.

Fixed dataset hashes:

| File | SHA-256 |
| --- | --- |
| `data/generated/train.jsonl` | `3867b316d469df4b4c2d80136324c8cda4e001c617c584c30703283ad75db346` |
| `data/generated/test.jsonl` | `dd7e6de16f4ccb0e295086ba97d80abf8b6bcda01852f1ee8bb61ff3154f8ded` |

The manifest includes the seed, adapted generator revision/source hash, upstream commit/file hashes, generation tokenizer, pairing counts, and dataset hashes. Audit output records config and implementation hashes, full token IDs/readable tokens, offsets, full spans, separate masks/positions, and answer checks.

## Known issues and boundaries

There are no unresolved Phase 0/1 acceptance blockers. The initial sandbox download failed with `curl: (6) Could not resolve host: raw.githubusercontent.com`; the approved external curl retry retrieved all eight pinned originals successfully. Their hashes are verified before every audit.

The configured offline tokenizer requires the existing cache on this machine. On another machine, populate only the pinned tokenizer assets or explicitly enable tokenizer downloads; model weights remain unnecessary. Single-token evaluation deliberately reports multi-token or boundary-incompatible continuations as unsupported while retaining the examples.

At the prior Phase 0/1 checkpoint, factual accuracy, IIA, intervention-forward, frozen-weight, gradient, and training validation were deferred. Those are now completed for the one Phase 2 condition above. The original utility's 18-token assertion was removed from the adaptation, and its mislabeled `kl_div` is recorded accurately as `mean_target_logit`. Preserve held-out test data and add a separate validation split before future tuning.

## Phase 1 audit command (prior checkpoint)

The next safe action is to rerun the completed checkpoint using the saved files and inspect `outputs/audit/summary.md`. This works from any directory:

```bash
env PYTHONPATH=/home/ilingl/projects/ioi-das-relative/src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli audit --config /home/ilingl/projects/ioi-das-relative/configs/audit.json
```

Expected result: 200 train / 100 test pairs, zero unsupported original answer checks, and `Dataset reused`. Do not regenerate or replace the saved samples. Phase 2 is now implemented and complete as recorded above; this remains the independent tokenizer audit command.

## Follow-up environment and GPU verification

The user created `/home/ilingl/projects/ioi-das-relative/.conda` using `conda create --prefix ./.conda python=3.11`. At inspection its Python was 3.11.17, with pip 26.2.1 and packaging 26.3, but without torch, transformers, tokenizers, pyvene, numpy, and pytest. Actual attempts failed with `No module named pytest` and `Audit failed: No module named 'transformers'`. This prefix could not run the complete checkpoint or use PyTorch CUDA. No packages were installed to remedy it; Phase 2 used the existing ioi-das-v2 environment instead.

The inspection tool's shell did not have an activated Conda environment; its unqualified `python` resolved to `/usr/bin/python`, Python 2.7.18. Explicit activation or the recorded absolute interpreter path is necessary. Conda initialization is `/home/ilingl/miniforge3/etc/profile.d/conda.sh`; prefer the already provisioned `/home/ilingl/.conda/envs/ioi-das-v2` for current testing.

Actual server GPU evidence:

- `nvidia-smi` outside the restricted sandbox lists seven NVIDIA GeForce RTX 2080 Ti devices, each 11264 MiB, with driver 535.129.03.
- `ioi-das-v2` torch 2.5.1+cu121 reports CUDA runtime 12.1, `cuda_available=true`, and `visible_device_count=7`.
- A 256x256 float32 matrix multiplication with inputs and output on `cuda:0` passed; every output element equaled the expected 256. This was a small environment check, not training or a benchmark.
- The tool sandbox has no `/dev/nvidia*` visibility. Inside it `nvidia-smi` cannot communicate with the driver and PyTorch reports no CUDA devices. The approved outside-sandbox check succeeds, so this is an execution-boundary restriction rather than a server GPU failure.

Added `src/ioi_das/environment.py` and `python -m ioi_das.cli doctor`, including `--require-gpu`, `--device`, and optional explicit `--output`. The report records interpreter, prefix, dependency versions, selected environment variables, CUDA evidence, and actionable errors. Missing dependencies or required GPU verification failures return exit code 2. It never falls back to CPU. Added `.conda/` to `.gitignore` to exclude local environment binaries from future version control.

Evidence files:

- `outputs/environment/project-conda.json`: selected local interpreter, missing dependencies, and missing torch.
- `outputs/environment/ioi-das-v2-sandbox.json`: ready Phase 1 dependencies but no sandbox GPU access.
- `outputs/environment/ioi-das-v2-server.json`: ready dependencies and a successful real server GPU operation.

The original saved data, upstream files, and Phase 0/1 contracts remain unchanged. Full tests and the 200/100-pair audit were rerun with the verified existing interpreter after adding diagnostics; see the current audit artifacts for implementation hashes and unchanged dataset hashes.

Exact commands to activate the working environment and test the implemented checkpoint:

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

Expected results for the current Phase 2 checkout: 15 tests and 305 subtests passed; audit passes 200 train / 100 test pairs with saved data reused; doctor reports `status="passed"`, `gpu.status="passed"`, and a CUDA result device. The audit is tokenizer-only CPU work even when GPUs are available. Setting CUDA_VISIBLE_DEVICES chooses visible devices for the GPU diagnostic; it does not turn the Phase 1 audit into GPU work.

## GitHub repository and synchronization

Repository: https://github.com/lai8928/ioi-das-relative (private). The project uses local branch `main` and HTTPS remote `origin`. The initial checkpoint includes the implementation, brief, documentation, configuration, focused tests, eight preserved upstream originals with provenance, fixed datasets/manifest, complete audit outputs, and environment/GPU diagnostic reports.

The upload review found 41 project files, approximately 4.64 MB, with no recognized credential patterns or environment executables. Upstream, data, configuration, implementation, and audit artifact hashes matched the recorded evidence. `.conda/`, `.venv/`, Python/pytest caches, and `.agents/`, `.aws/`, `.codex/` are excluded by `.gitignore`. No experiment scope was expanded for publication.

To inspect the synchronized checkout:

```bash
cd /home/ilingl/projects/ioi-das-relative
git status --short --branch
git remote -v
git log -1 --oneline
```

Future project changes should be reviewed and tested before committing and pushing to `origin/main`. Phase 1 audit and Phase 2 single-condition commands are recorded above. Phase 3/4 still require a new request.

## Phase 2 and notebook publication checkpoint

On 2026-10-12, the user explicitly requested uploading the completed changes to the existing personal GitHub repository. This follow-up checkpoint includes the Phase 2 configuration and implementation, focused tests, immutable full/smoke results and alignment checkpoints, independent result verification, the executed walkthrough notebook and renderer, all exported figures and notebook verification evidence, and updated documentation. It also retains the existing audit timestamp update and the successful manual tokenizer audit under `outputs/audit-manual-check/`; that audit reused all 200 training / 100 test pairs and reported zero unsupported answer checks.

The pre-publication test command recorded above passed again: `15 passed, 305 subtests passed in 10.24s`. Staged whitespace checks passed for all files except the automatically generated SVG exports, whose original formatting is retained to preserve their recorded hashes. The publication review checked 110 project files (approximately 19.6 MiB total, largest file approximately 2.26 MiB), found no recognized credential patterns, environment directories, caches, or pretrained-model binaries, and verified upstream, dataset, experiment, notebook, and figure hashes. Remote `origin/main` was inspected before synchronization and pointed to the initial checkpoint `3fb28077502ef3e2cbec9c3d57f538128fc51370`. No new model load, training, sweep, dependency installation, or environment change was needed for publication.

No experiment acceptance blockers remain. After synchronization, the exact next command to inspect this checkpoint is:

```bash
git -C /home/ilingl/projects/ioi-das-relative log -1 --oneline
```
