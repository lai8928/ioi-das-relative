# Upstream snapshot and adaptations

Repository: [Stanford pyvene](https://github.com/stanfordnlp/pyvene).

Full pinned commit: `9e333904dcf9e597ca76170010d17f4d4580de8d`.

Retrieval date: 2026-10-12, using the client's America/Los_Angeles calendar date.

Retrieval method: HTTPS GET of the corresponding `raw.githubusercontent.com/stanfordnlp/pyvene/<commit>/<path>` URLs using `curl --fail --location`. The eight originals below are stored byte-for-byte unchanged under `vendor/pyvene_upstream/`, retaining repository-relative paths. The utility source was first retrieved to a temporary file and then copied without transformation. [provenance.json](../vendor/pyvene_upstream/provenance.json) records each exact raw URL, hash, and byte count. Upstream `pyproject.toml` is dependency reference only; it is not this project's packaging configuration.

## Extracted originals

| Repository-relative path | Bytes | SHA-256 |
| --- | ---: | --- |
| `LICENSE` | 11357 | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `pyproject.toml` | 2017 | `60de9d6dbd6ae5aadaff58bb5e4acd45d44fff9e4cd84d5ba32fc73bc92b9a78` |
| `tutorials/advanced_tutorials/IOI_with_DAS.ipynb` | 2336116 | `2f85fe706cd81517073bb85642926d5988fec5b5c7ece865943d4ccadad99c19` |
| `tutorials/advanced_tutorials/tutorial_ioi_utils.py` | 40757 | `a2773a4a34476e0cbd531cb4209d740e9540019291bdce838c60460a4c8fa90c` |
| `tutorials/advanced_tutorials/tutorial_data/names.json` | 1208 | `d1b6093c3f5e9c2a9e3fcb1723ba6966cc5873727b0e247529c141e65cb22d96` |
| `tutorials/advanced_tutorials/tutorial_data/objects.json` | 98 | `169a6909f1046ce692e3371d5ff7e354278f892c7d2d285a14fef36790dc0ef5` |
| `tutorials/advanced_tutorials/tutorial_data/places.json` | 103 | `3cdbddb752cb3c01ca0526df7994306edea56bb8cd50e3373879bcb59de5bd57` |
| `tutorials/advanced_tutorials/tutorial_data/templates.json` | 1404 | `8fd1037215ec8b6d5cc56586abacf15fb04932e701b2ad583af84cfa3438a523` |

The upstream license is Apache 2.0, preserved in `vendor/pyvene_upstream/LICENSE`. The tutorial identifies Zhengxuan Wu as its author. The dataset utility explicitly credits [activation-patching-illusion](https://github.com/amakelov/activation-patching-illusion) as the main source of dataset-generation code; adapted generation retains that attribution.

## Source-to-module mapping

| Upstream behavior or source | Local implementation or future destination |
| --- | --- |
| `Prompt`: formatting, IO/subject roles, canonical pattern semantics, resampling | `src/ioi_das/data.py`; add occurrence-level character spans and stable serialization. |
| `PromptDistribution.sample_one()` / `.sample_das()` | `src/ioi_das/data.py`; preserve original POSITION distribution, base-to-source resampling, and counterfactual role rule. |
| `find_variable_at()`: original POSITION train/test construction | `src/ioi_das/data.py`; move configuration and orchestration into `cli.py` and `audit.py`. |
| `PromptDataset`: tokenizer calls, prompt lengths, answer IDs | `src/ioi_das/tokenization.py`; retain offsets, full name spans, continuation IDs, masks, and independent side encoding. |
| Scalar token sites supplied to `find_variable_at()` | New `src/ioi_das/positions.py`; resolve factual named anchors and end-relative offsets separately for every prompt. |
| No upstream occurrence or unequal-length audit equivalent | New `src/ioi_das/checks.py`; independently validate hand-derived roles, exact positions, unsupported continuations, and diagnostic failures. |
| Four `tutorial_data/*.json` files | Immutable source assets consumed by `data.py`; original asset/template splits retained. |
| `get_last_token()` | `intervention.py` reads each base's logits at its own last valid token; shared by `train.py` and `evaluate.py`. |
| `single_d_low_rank_das_position_config()` and intervention branches in `find_variable_at()` | `intervention.py` builds one low-rank `block_output` intervention with independently resolved per-example base/source locations. |
| Optimization and `compute_metrics()` in `find_variable_at()` | `train.py` preserves explicit optimizer/scheduler behavior; `evaluate.py` saves full-vocabulary predictions, unrounded counts, losses, and `mean_target_logit`. |
| One configured `find_variable_at()` condition | `experiment.py` implements `run_condition()` with saved-data reuse, artifact hashes, checkpoint reload, and cleanup. Nested sweep loops remain deferred. |
| No complete upstream gradient/hash/variable-length validation equivalent | New `validation.py` checks identity, alignment gradients, exact frozen state, real and synthetic batching, and hook state. |
| Notebook figures and saved CSV reads | Planned `plot.py`; plots will read this project's results rather than upstream outputs. |
| `LICENSE` and `pyproject.toml` | Attribution/license preservation and external dependency reference. |

## Inspected dependencies

The utility imports standard-library modules, transformers, numpy, torch, pandas, joblib, tqdm, and pyvene intervention classes. The notebook imports the utility, pyvene model/helpers, pandas, matplotlib, and plotnine. Its plotting cells load tutorial CSV results; these are later-phase reference behavior and are not Phase 1 inputs.

The Phase 1 adaptation extracts prompt sampling into standard Python and loads GPT-2 tokenizers through the installed transformers/tokenizers packages. No additional source file is required: the four original JSON assets fully define generation, while tokenizers are external versioned dependencies. The whole advanced tutorial directory and the pyvene package are not vendored. The inspected upstream package version is 0.1.8; Phase 2 uses the existing external pyvene 0.1.8, torch, transformers, and numpy packages. GPT-2 model and tokenizer revision `607a30d783dfa663caf39e06633721c8d4cfcd7e` are already cached. No packages, Python/CUDA components, or model weights need downloading or replacing. The optional pyvene notice about missing `nnsight` does not affect this torch-backed intervention and does not require installation.

## Adapted behavior and compatibility fixes

- Replace `list(set(pattern))` with first-occurrence symbol order. Set iteration makes a seed insufficient to reproduce symbol assignments across processes. The adaptation preserves the distribution and upstream resampling/label semantics while making new samples deterministic; it does not claim to reconstruct historical samples.
- Capture spans while formatting the prompt, then map each occurrence using fast GPT-2 offsets. Retain full token spans and select the last token as the initial scalar anchor. Repeated subjects therefore have separate `S1` and `S2` sites.
- Compare fast GPT-2 IDs with slow GPT-2 IDs at the configured tokenizer revision. Keep right padding and attention masks explicit, and resolve separate base/source position arrays.
- Remove the tutorial's fixed-length assumption from the adaptation. All original prompts survive unchanged at their natural lengths; `N` is computed from each attention mask. There is no 18-token assertion or truncation/filtering to satisfy one.
- Keep `GOAL_NAME` factual within each input. It is neither the generated answer nor the POSITION counterfactual label. Readout remains at base `N` for training and evaluation.
- Check the full leading-space continuation at the actual prompt boundary, retaining all answer IDs. The upstream `[0]` answer-token selection is not adopted; multi-token answers remain present and are marked unsupported for initial single-token evaluation.
- Resolve configuration paths against explicit config/project locations rather than the utility's relative tutorial directory. Save immutable examples with IDs and manifest hashes and reuse them instead of resampling for every condition.
- Report invalid locations with the sample ID and valid bounds. Keep synthetic unequal-length cases separate from the original research distribution in focused checks.

## Phase 2 optimizer and intervention adaptation

The pinned utility's low-rank POSITION path uses ten epochs, batch size 20, and Adam at learning rate 0.01. The current brief selects GPT-2, `block_output`, layer 8, `END/N`, and rank 1 from that general path. The adaptation records Adam's default betas `[0.9, 0.999]`, epsilon `1e-8`, and zero weight decay explicitly. The upstream `LinearLR` default start factor is `1/3`; its configured end factor is 0.1 and `total_iters=n_epochs=10`. Upstream calls `scheduler.step()` after every batch. Phase 2 preserves that behavior instead of replacing it with decay over ten epochs or 100 updates: the rate starts at approximately 0.0033333, reaches 0.001 after ten updates, and remains there for the rest of the full 100-update run.

Training and evaluation share `intervention_forward()` with both attention masks, separate base/source positions, and each base's last valid-token readout. This intentionally corrects the tutorial's fixed 18-token location/readout assumptions. No prompt is changed, truncated, filtered, or extended with the answer. The language model remains frozen and in evaluation mode; optimization keeps autograd enabled so downstream frozen layers can propagate gradients to the alignment. Batch shuffling uses a local NumPy `RandomState(seed)`, preserving the upstream MT19937 permutation algorithm while insulating training order from the additional validation checks. The saved test split is used only for evaluation.

pyvene 0.1.8's standard cleanup removes all model forward and pre-forward hooks. The local `ScopedIntervenableModel` records its own registrations and removes only those handles, retaining unrelated user hooks and leaving the installed package unchanged. The shared forward cleans condition-owned activation/output state in a `finally` block; condition teardown also clears gradients and checks the remaining hook snapshot. Tests exercise both successful and failing forward paths.

Upstream `compute_metrics()` rounds accuracy and calls a mean target logit `kl_div`. The adaptation retains the full-vocabulary argmax definition but saves exact correct/total counts and full-precision ratios. It names the target-logit average `mean_target_logit` and separately records cross-entropy and probabilities. It never presents this quantity as KL divergence. Per-example results keep their sample IDs, original inputs, roles, continuation token IDs, decoded predictions, and actual intervention/readout indices.

Checkpointing saves the alignment's raw orthogonal-parametrization state and effective projection; a saved-state reload must reproduce exact probe logits. Validation verifies nonzero finite alignment gradients, unchanged GPT-2 tensor hashes, a base-as-source identity intervention, batch/individual full-vocabulary consistency, and independent 18/22-token synthetic positions at `N` and `N-2`. These synthetic examples are excluded from training and research metrics. Smoke runs and full runs have separate directories and labels. No sweep or plotting implementation is adapted in Phase 2. The notebook's outputs and CSVs are not evidence of runs in this project.

## Compatibility evidence

Focused tests execute the preserved upstream prompt-generation methods in isolation with only the declared set-order substitution, then compare text, names, factual roles, objects, places, and POSITION counterfactual labels for all 300 pairs. Separate process checks confirm identical serialized dataset hashes under different `PYTHONHASHSEED` values. The full audit verifies 600 input and 1,800 answer-continuation fast/slow GPT-2 comparisons at the pinned tokenizer revision. These checks establish compatibility for newly saved samples while retaining the documented determinism change.

Phase 2 completed the configured 100-update GPU condition using those unchanged files. Its real-model validation passed before and after training: frozen GPT-2 state hashes were identical, identity logits matched exactly, variable-length full-vocabulary batch/individual comparisons passed, and saved alignment reload and hook cleanup passed. Focused tests also cover full-vocabulary accuracy with a winning token outside the two names, correct sample weighting for an incomplete final batch, and preservation of unrelated hooks on normal and failing forwards. The complete suite passed 15 tests and 305 subtests. Actual metrics, dependencies, model-asset hashes, configuration, raw/effective weights, and validation evidence are retained under `outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/`; the separate `smoke/` directory is a one-update check. No upstream originals or installed packages were changed.
