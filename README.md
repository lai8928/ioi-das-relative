# ioi-das-relative

A small research project on the indirect object identification (IOI) task in
GPT-2. It uses distributed alignment search (DAS) to locate the POSITION
variable, and it separates the causal variable being studied from the token
position where the intervention is applied. Positions are resolved per
example (`N`, `N-1`, `GOAL_NAME`, …), so prompts keep their original variable
lengths.

## Where to look

| Question | File |
| --- | --- |
| What are we doing until the next meeting? | [docs/PLAN.md](docs/PLAN.md) |
| What is done, and where is the evidence? | [docs/STATUS.md](docs/STATUS.md) |
| Which rules does every experiment follow? | [docs/PROTOCOL.md](docs/PROTOCOL.md) |
| How are code, configs, scripts, and commits written? | [docs/CONVENTIONS.md](docs/CONVENTIONS.md) |
| Which code changes are queued for implementation? | [docs/briefs/](docs/briefs/) |
| What was discussed with the professor? | [docs/meetings/](docs/meetings/) |
| Which datasets exist? | [data/REGISTRY.md](data/REGISTRY.md) |
| Where did the upstream code come from? | [docs/UPSTREAM.md](docs/UPSTREAM.md) |
| Rules for agents working here | [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) |
| Superseded plans, status, and specs | [docs/archive/](docs/archive/) |

## Layout

```
configs/            experiment configs (legacy: audit.json, phase2.json)
data/generated/     saved datasets, registered in data/REGISTRY.md
docs/               plan, status, protocol, conventions, meetings, briefs, archive
notebooks/          saved-result walkthroughs (no training by default)
outputs/            immutable experiment outputs
scripts/            thin wrappers and notebook rendering
src/ioi_das/        package: data, tokenization, positions, intervention,
                    train, evaluate, validation, experiment, cli
tests/              pytest suite
vendor/pyvene_upstream/  eight pinned upstream originals, unchanged
```

## Environment

Use the existing Conda environment `ioi-das-v2`
(`/home/ilingl/.conda/envs/ioi-das-v2/bin/python`: Python 3.10, torch
2.5.1+cu121, transformers 4.57.6, tokenizers 0.22.2, pyvene 0.1.8). Do not
install packages into it without asking. The project-local `.conda/` prefix
lacks the dependencies and is not used.

The server has seven RTX 2080 Ti GPUs (11 GB each). `CUDA_VISIBLE_DEVICES=k`
exposes physical GPU `k` as logical `cuda:0`; check availability with
`nvidia-smi` first. Model and tokenizer load from the local cache only
(`local_files_only=true`, pinned revisions).

## Commands

Run from the project root. `PY` abbreviates the interpreter path.

```bash
PY=/home/ilingl/.conda/envs/ioi-das-v2/bin/python
export PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib

# Tests
$PY -B -m pytest -q

# Dataset and position audit (CPU, tokenizer only)
$PY -B -m ioi_das.cli audit --config configs/audit.json

# Environment and GPU diagnostics
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli doctor --require-gpu

# Single DAS condition (GPT-2 Small, layer 8, N, rank 1); --smoke for a one-update check.
# Existing output directories are refused; pass --output-dir <new path> to repeat.
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/phase2.json --smoke
```

Re-render the walkthrough notebook from saved outputs (no model load):

```bash
$PY -B scripts/render_phase2_notebook.py --project-root "$PWD"
```

## Credits

Eight upstream files are preserved unchanged under `vendor/pyvene_upstream/`
from Stanford pyvene commit `9e333904dcf9e597ca76170010d17f4d4580de8d`
(Apache 2.0). Dataset-generation code is adapted from
[activation-patching-illusion](https://github.com/amakelov/activation-patching-illusion),
as upstream credits. See [docs/UPSTREAM.md](docs/UPSTREAM.md).
