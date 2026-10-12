# Phase 0/1 checkpoint

Completed on 2026-10-12 (America/Los_Angeles). Project root: `/home/ilingl/projects/ioi-das-relative`.

Phase 0 and Phase 1 are complete. No model weights were downloaded or loaded, no DAS training started, no packages were installed, and no CUDA/system environment was changed. Phases 2–4 remain documented plans requiring a new request.

Follow-up on 2026-10-12: inspected the newly created project-local Conda prefix, reran the implemented checkpoint, and verified an actual CUDA matrix multiplication on the server. The added `doctor` command is an environment diagnostic; Phase 2 remains unimplemented.

GitHub follow-up on 2026-10-12: the user explicitly authorized creating a new personal repository and uploading this checkpoint. The private repository is `lai8928/ioi-das-relative`: https://github.com/lai8928/ioi-das-relative. Git was initialized in this project, using branch `main` and the personal account's noreply commit identity. This later authorization supersedes the bootstrap restriction on repository creation and pushing; the restriction on later experiment phases remains in effect.

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

No factual accuracy, IIA, intervention-forward, frozen-weight, gradient, or training claims are made at this checkpoint. Those require Phase 2. The original utility's 18-token assertion cannot be retained for these original inputs. Its `kl_div` metric is not KL divergence; later implementation must inspect and rename/correct it. Preserve held-out test data and add a separate validation split before future tuning.

## Exact next command

The next safe action is to rerun the completed checkpoint using the saved files and inspect `outputs/audit/summary.md`. This works from any directory:

```bash
env PYTHONPATH=/home/ilingl/projects/ioi-das-relative/src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/ilingl/.conda/envs/ioi-das-v2/bin/python -B -m ioi_das.cli audit --config /home/ilingl/projects/ioi-das-relative/configs/audit.json
```

Expected result: 200 train / 100 test pairs, zero unsupported original answer checks, and `Dataset reused`. Do not regenerate or replace the saved samples. Review the complete Phase 1 evidence before requesting the planned Phase 2 single condition (GPT-2, block_output, layer 8, N, rank 1). No later-phase command exists yet.

## Follow-up environment and GPU verification

The user created `/home/ilingl/projects/ioi-das-relative/.conda` using `conda create --prefix ./.conda python=3.11`. Its current Python is 3.11.17. It has pip 26.2.1 and packaging 26.3, but torch, transformers, tokenizers, pyvene, numpy, and pytest are missing. Actual attempts fail with `No module named pytest` and `Audit failed: No module named 'transformers'`. This prefix cannot yet run the complete checkpoint or use PyTorch CUDA. No packages were installed to remedy it.

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

Expected results: 11 tests and 305 subtests passed; audit passes 200 train / 100 test pairs with saved data reused; doctor reports `status="passed"`, `gpu.status="passed"`, and a CUDA result device. The audit is tokenizer-only CPU work even when GPUs are available. Setting CUDA_VISIBLE_DEVICES chooses visible devices for the GPU diagnostic; it does not turn the Phase 1 audit into GPU work.

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

Future project changes should be reviewed and tested before committing and pushing to `origin/main`. Continue using the exact Phase 1 audit command above; Phase 2 still requires a new request.
