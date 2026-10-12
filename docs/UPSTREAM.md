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
| `get_last_token()` | Position/readout contract now; later `evaluate.py` reads base logits using each base attention mask. |
| `single_d_low_rank_das_position_config()` and intervention branches in `find_variable_at()` | Planned `intervention.py` in Phase 2. |
| Optimization, metrics, and nested condition loops in `find_variable_at()` | Planned `train.py`, `evaluate.py`, and `experiment.py` in Phases 2–3. |
| Notebook figures and saved CSV reads | Planned `plot.py`; plots will read this project's results rather than upstream outputs. |
| `LICENSE` and `pyproject.toml` | Attribution/license preservation and external dependency reference. |

## Inspected dependencies

The utility imports standard-library modules, transformers, numpy, torch, pandas, joblib, tqdm, and pyvene intervention classes. The notebook imports the utility, pyvene model/helpers, pandas, matplotlib, and plotnine. Its plotting cells load tutorial CSV results; these are later-phase reference behavior and are not Phase 1 inputs.

The Phase 1 adaptation extracts prompt sampling into standard Python and loads GPT-2 tokenizers through the installed transformers/tokenizers packages. No additional source file is required: the four original JSON assets fully define generation, while tokenizers are external versioned dependencies. The whole advanced tutorial directory and the pyvene package are not vendored. The inspected upstream package version is 0.1.8; the environment also has pyvene 0.1.8 installed, but this checkpoint does not import it to train or load model weights.

## Adapted behavior and compatibility fixes

- Replace `list(set(pattern))` with first-occurrence symbol order. Set iteration makes a seed insufficient to reproduce symbol assignments across processes. The adaptation preserves the distribution and upstream resampling/label semantics while making new samples deterministic; it does not claim to reconstruct historical samples.
- Capture spans while formatting the prompt, then map each occurrence using fast GPT-2 offsets. Retain full token spans and select the last token as the initial scalar anchor. Repeated subjects therefore have separate `S1` and `S2` sites.
- Compare fast GPT-2 IDs with slow GPT-2 IDs at the configured tokenizer revision. Keep right padding and attention masks explicit, and resolve separate base/source position arrays.
- Remove the tutorial's fixed-length assumption from the adaptation. All original prompts survive unchanged at their natural lengths; `N` is computed from each attention mask. There is no 18-token assertion or truncation/filtering to satisfy one.
- Keep `GOAL_NAME` factual within each input. It is neither the generated answer nor the POSITION counterfactual label. Readout remains at base `N` for future evaluation.
- Check the full leading-space continuation at the actual prompt boundary, retaining all answer IDs. The upstream `[0]` answer-token selection is not adopted; multi-token answers remain present and are marked unsupported for initial single-token evaluation.
- Resolve configuration paths against explicit config/project locations rather than the utility's relative tutorial directory. Save immutable examples with IDs and manifest hashes and reuse them instead of resampling for every condition.
- Report invalid locations with the sample ID and valid bounds. Keep synthetic unequal-length cases separate from the original research distribution in focused checks.

No training, scheduler, intervention, metric, or plotting implementation is adapted in this checkpoint. For future extraction, note that upstream `compute_metrics()` rounds accuracy and calls a mean target logit `kl_div`; it is not a true KL divergence. Preserve raw counts and full precision in future saved results and correct that label after review. The notebook's outputs and CSVs are not evidence of runs in this project.

## Compatibility evidence

Focused tests execute the preserved upstream prompt-generation methods in isolation with only the declared set-order substitution, then compare text, names, factual roles, objects, places, and POSITION counterfactual labels for all 300 pairs. Separate process checks confirm identical serialized dataset hashes under different `PYTHONHASHSEED` values. The full audit verifies 600 input and 1,800 answer-continuation fast/slow GPT-2 comparisons at the pinned tokenizer revision. These checks establish compatibility for newly saved samples while retaining the documented determinism change.
