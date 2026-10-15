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

# Dataset and position audits (CPU, tokenizer only; saved files are verified).
$PY -B -m ioi_das.cli data audit --dataset legacy_v1
$PY -B -m ioi_das.cli data audit --dataset val_indist_v1

# Create the validation dataset once in a project where it is not yet registered.
$PY -B -m ioi_das.cli data build --config configs/datasets/val_indist_v1.json

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

# All-layer sweep: validation selects the layer before any test evaluation.
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/layer-sweep/gpt2-small.json --smoke --override 'grid={"intervention.layer":[8],"seed":[42]}'
# Run long GPU jobs in tmux; commit source/config/data before the full run.
tmux new-session -s ioi-layer-sweep
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/layer-sweep/gpt2-small.json

# Rebuild CSVs, summary.md, and SVG figures from saved JSON only.
# Reporting imports no torch, transformers, or pyvene and needs no GPU.
$PY -B -m ioi_das.cli report --experiment-dir outputs/single-condition-das/YYYYMMDD-layer8-seed42
```

Experiment directories are derived from the config task/name and start date:
`outputs/<task>/<YYYYMMDD>-<name>/`, with `smoke-` before the date for smoke
runs. Repeated starts on the same date add `-2`, `-3`, and so on. Resume uses
the original resolved config; repeat any overrides or `--smoke` used for that
run. It preserves completed conditions and adds missing ones after checking
their artifact hashes. Failed partial conditions remain preserved; a new
experiment is needed to retry them.

For configs with `selection`, every primary condition evaluates train and
validation only. After all conditions complete, `selection.json` locks the
highest mean validation IIA over seeds (ties choose the lowest layer).
Every checkpoint is then evaluated on the configured locked splits in
separate hashed `post_lock/` records. Smoke runs never evaluate test or lock
a selection. Reports include `conditions.csv`, `layer_summary.csv`, and
validation, train/validation, and descriptive test curves. Seed SD is seed
variation, not a confidence interval.

Dataset references resolve through `data/registry.json`. Loading verifies both
split and manifest hashes; generator source hashes record provenance. Builders
refuse existing dataset versions and enforce prompt and semantic-group
deduplication. Each `data audit` writes a new directory under
`outputs/data-audit/<date>-<dataset>/`, preserving previous audit evidence.

Re-render the walkthrough notebook from saved outputs (no model load):

```bash
$PY -B scripts/render_phase2_notebook.py --project-root "$PWD"
```

## Run on another machine

Clone the repository, check out the commit containing the intended config,
and create a separate environment from the recorded interpreter and package
versions. The lock lists the project's runtime, test, and notebook imports;
pip also installs their dependencies. A CUDA-compatible NVIDIA driver and
`tmux` must already be available.

```bash
git clone https://github.com/lai8928/ioi-das-relative.git
cd ioi-das-relative
conda create -n ioi-das-v2 python=3.10.21 pip
conda activate ioi-das-v2
python -m pip install -r environment/requirements-lock.txt
PY=$(command -v python)
export PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 MPLCONFIGDIR=/tmp/ioi-das-relative-matplotlib
$PY -B -m ioi_das.cli doctor
```

Download the pinned model and tokenizer assets explicitly before any run.
Both commands use the cache names recorded in the configs. A run loads only
cached files and reports the required download command if assets are missing.

```bash
HF_HUB_OFFLINE=0 hf download gpt2 config.json model.safetensors tokenizer.json tokenizer_config.json vocab.json merges.txt --revision 607a30d783dfa663caf39e06633721c8d4cfcd7e
HF_HUB_OFFLINE=0 hf download gpt2-medium config.json model.safetensors tokenizer.json tokenizer_config.json vocab.json merges.txt --revision 6dcaa7a952f72f9298047fd5137cd6e4f05f41da
nvidia-smi
# Choose an available physical GPU, then verify CUDA and run a one-condition smoke.
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli doctor --require-gpu
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/model-scale/gpt2-medium.json --smoke --override 'grid={"intervention.layer":[12],"seed":[42]}'
```

Commit source, configs, and dataset changes before starting a full run. Launch
it inside `tmux` so disconnecting the terminal leaves the process running;
reactivate the environment and exports above inside the session if needed.

```bash
git status --short
tmux new-session -s ioi-medium
CUDA_VISIBLE_DEVICES=0 $PY -B -m ioi_das.cli run --config configs/model-scale/gpt2-medium.json
# Detach with Ctrl-b, then d; reconnect with: tmux attach -t ioi-medium
```

From another terminal, activate the environment, set `PY` and `PYTHONPATH` as
above, and pass the experiment directory printed by `run` to `status`. It
reads the saved run record and reports completion counts and a duration-based
ETA, so it can also inspect a completed run without loading model weights.

```bash
$PY -B -m ioi_das.cli status --experiment-dir outputs/model-scale/YYYYMMDD-gpt2-medium
```

Bring results back by committing `outputs/<task>/<experiment-id>/` on the
other machine and transferring that commit, or copy the complete directory
back into the same path here and commit it here. Preserve the saved config,
run records, hashes, checkpoints, and report together. Keep partial or failed
run directories as evidence; completed outputs remain unchanged.

## Credits

Eight upstream files are preserved unchanged under `vendor/pyvene_upstream/`
from Stanford pyvene commit `9e333904dcf9e597ca76170010d17f4d4580de8d`
(Apache 2.0). Dataset-generation code is adapted from
[activation-patching-illusion](https://github.com/amakelov/activation-patching-illusion),
as upstream credits. See [docs/UPSTREAM.md](docs/UPSTREAM.md).

## Training-size datasets and budgets

Build each version once, in this order, then audit all four with `data audit`:
`train_pool_v1`, `train_n200_v1`, `train_n1000_v1`, `train_n5000_v1`.
Each recipe is in `configs/datasets/<name>.json`; use
`ioi-das data build --config configs/datasets/<name>.json`.
The subsets preserve their pool records and are nested and balanced across
the four pairings. Manifests record capacity, external overlap checks,
source hashes, and subset nesting. Validation and descriptive test remain
`val_indist_v1/validation` and `legacy_v1/test`.

The two configs in `configs/data-scale/` fix layer 8 before the experiment,
using the prior layer-sweep choice. They do not select a new layer per size.
Their names contain `placeholder-equal-epochs` (10 epochs) or
`placeholder-equal-updates` (100 optimizer updates); these are provisional
budgets for later advisor review, not full-run results.
Both configs compare the three train references and seeds 42/43/44. To check
the complete configured grid with one bounded training pass per condition:

```bash
$PY -B -m ioi_das.cli run --config configs/data-scale/gpt2-small-layer8-placeholder-equal-epochs.json --smoke
$PY -B -m ioi_das.cli run --config configs/data-scale/gpt2-small-layer8-placeholder-equal-updates.json --smoke
```

Resolved training configs require exactly one of `epochs` and `max_updates`.
In an inherited JSON file, `null` explicitly removes an existing parent
setting; the update-budget config uses `"epochs": null` before setting
`"max_updates": 100`. CLI overrides also accept explicit removal, for example
`--override training.max_updates=null --override training.epochs=10`.
Removing an unknown setting is an error. Resolved configs never contain
these removal markers. The legacy per-update LinearLR is unchanged for both
budgets. `max_updates` stops at the exact requested optimizer step, including
partway through a shuffled pass. Smoke limits either budget to its first pass.

Only `data.train` may vary in a data grid. Every condition records the train
reference and SHA-256, while validation/test references stay fixed. Reports
keep each train dataset's seed means and SD separate.
