# ioi-das-relative

A small IOI research project that separates the causal variable being studied from the token position where an intervention is applied. The current Phase 0/1 checkpoint preserves the original POSITION-task sampling rules, saves fixed base/source pairs, and audits factual name anchors and positions relative to each prompt's end with the real GPT-2 tokenizer.

The implementation brief is [CODEX_IOI_DAS_BOOTSTRAP.txt](CODEX_IOI_DAS_BOOTSTRAP.txt). Read [docs/STATUS.md](docs/STATUS.md) for execution evidence and the continuation command, [docs/PLAN.md](docs/PLAN.md) for contracts and future acceptance criteria, and [docs/UPSTREAM.md](docs/UPSTREAM.md) for attribution, hashes, and documented adaptations.

## Environment and runnable commands

The existing `ioi-das-v2` Conda environment was discovered at `/home/ilingl/.conda/envs/ioi-das-v2/bin/python`. Bootstrap uses that interpreter without installing packages or changing CUDA. The inspected versions are Python 3.10.21, torch 2.5.1+cu121, transformers 4.57.6, tokenizers 0.22.2, pyvene 0.1.8, numpy 2.2.6, pytest 9.1.1, and packaging 26.3. Phase 1 uses tokenizers and standard Python code; it does not load language-model weights or require a GPU. pyvene remains an external dependency for later phases.

Run from this project root:

```bash
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli audit --config configs/audit.json
```

Run the focused checks with the same interpreter:

```bash
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m pytest -q
```

The configuration pins tokenizer `gpt2` to revision `607a30d783dfa663caf39e06633721c8d4cfcd7e` and enables `local_files_only`. Fast tokenizer offsets identify character spans; token IDs are compared with the corresponding slow GPT-2 tokenizer. Only tokenizer assets are needed. Configuration paths are resolved relative to the config directory and its explicit `project_root`; they do not depend on the process's working directory once the config path is supplied.

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

`GOAL_NAME` selects the factual indirect object's occurrence within each input. The scalar anchor is the last token of that complete name span. `N` is the last non-padding input token, and `N-k` is resolved independently for every base and source. The eventual model readout remains at base `N` regardless of the intervention location. Unsupported multi-token answers are preserved and reported instead of silently taking their first token.

The completed audit covers all 300 pairs: 600 input and 1,800 answer-continuation comparisons agree between fast and slow GPT-2 tokenizers, and 2,400 batch/individual position comparisons agree. All original-rule answer checks support single-token evaluation. Training prompts have lengths 15 or 19; test prompts range from 14 to 20 tokens. Preserved source resampling gives equal lengths within these sampled pairs, so separately labeled synthetic 18/22-token pairs verify unequal-length behavior. Focused checks also diagnose invalid offsets and retain an unsupported two-token `Mary Jane` answer. See [audit evidence](outputs/audit/summary.md) and [current status](docs/STATUS.md) for the final validation record.

## Source and scope

Eight upstream files are preserved unchanged under `vendor/pyvene_upstream/` at Stanford pyvene commit `9e333904dcf9e597ca76170010d17f4d4580de8d`, with machine-readable [provenance](vendor/pyvene_upstream/provenance.json). Adapted generation code credits [activation-patching-illusion](https://github.com/amakelov/activation-patching-illusion), as upstream does. The upstream Apache 2.0 license is included in `vendor/pyvene_upstream/LICENSE`.

This checkpoint implements `data.py`, `tokenization.py`, `positions.py`, `checks.py`, `audit.py`, and the CLI. Phases 2–4 are documented plans only. No DAS training, model-weight download, condition sweep, or plotting is part of bootstrap.
