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
| Which datasets exist? | [data/registry.json](data/registry.json) |
| Where did the upstream code come from? | [docs/UPSTREAM.md](docs/UPSTREAM.md) |
| Rules for agents working here | [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) |
| Superseded plans, status, and specs | [docs/archive/](docs/archive/) |

## Layout

```
configs/            experiment configs (legacy: audit.json, phase2.json)
data/generated/     saved datasets, registered in data/registry.json
docs/               plan, status, protocol, conventions, meetings, briefs, archive
notebooks/          saved-result walkthroughs (no training by default)
outputs/            immutable experiment outputs
scripts/            thin wrappers and notebook rendering
src/ioi_das/        package: data, tokenization, positions, intervention,
                    train, evaluate, validation, config, pipeline, report, cli
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

# Check availability before choosing a physical GPU.
nvidia-smi

# One-update smoke check of the same pipeline used by a full experiment.
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/single-condition-das/layer8-seed42.json --smoke

# Full run: source, configs, and data must have no uncommitted changes.
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/single-condition-das/layer8-seed42.json

# Override one value; the resolved config and its SHA-256 are saved.
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/single-condition-das/layer8-seed42.json --smoke --override seed=43

# Continue missing conditions, verifying saved hashes first.
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/single-condition-das/layer8-seed42.json --resume outputs/single-condition-das/YYYYMMDD-layer8-seed42

# Rebuild conditions.csv, summary.md, and figures/iia.svg from saved JSON only.
# Reporting imports no torch, transformers, or pyvene and needs no GPU.
$PY -B -m ioi_das.cli report --experiment-dir outputs/single-condition-das/YYYYMMDD-layer8-seed42
```

Experiment directories are derived from the config task/name and start date:
`outputs/<task>/<YYYYMMDD>-<name>/`, with `smoke-` before the date for smoke
runs. Repeated starts on the same date add `-2`, `-3`, and so on. Resume uses
the original resolved config; repeat any overrides or `--smoke` used for that
run. It preserves completed conditions and adds missing ones after checking
their artifact hashes.

The audit reuses the registered saved dataset. When its configured output
already contains the completed audit, the command writes its verification
to a new `/tmp/ioi-das-audit-*` directory and reports that path. It preserves
the completed evidence under `outputs/audit/`.

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
