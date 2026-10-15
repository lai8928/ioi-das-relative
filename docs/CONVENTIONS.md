# Engineering conventions

How code, configs, scripts, outputs, and git history are written in this
project. Scientific rules are in [PROTOCOL.md](PROTOCOL.md). Rules marked
**(tested)** are enforced by `tests/test_conventions.py` once that test
exists; the rest are checked in review.

## 1. Code structure

Three layers, each depending only on the layers below it:

| Layer | Modules | Rules |
| --- | --- | --- |
| Entry | `cli.py`, `scripts/*.py` | Parse arguments, load a config, call one pipeline function, print a short result. No experiment logic. |
| Pipeline | `config.py`, `pipeline.py`, `report.py` (names may be refined) | Load and validate configs, expand the grid, run conditions, write outputs, aggregate saved results. The only layer that reads a config object. |
| Building blocks | `data`, `tokenization`, `positions`, `intervention`, `train`, `evaluate`, `validation` | Pure functions with explicit parameters. Never receive a whole config dict. No file paths chosen here. |

- One code path per behavior. A single condition is a grid of size 1; a smoke
  run is an override of the same path. Never fork a function to make a
  variant (`run_condition_v2`, `run_m3_condition`).
- New behavior becomes a named option chosen by config (for example a
  location anchor, a model family, a schedule name), registered in one
  place, with a test.

## 2. Readability

- Module and function names describe what they do. No phase, milestone,
  meeting, or date in file names, identifiers, comments, docstrings, or error
  messages **(tested for file names and identifiers)**. Write
  "rank must be between 1 and n_embd", not "Phase 2 requires rank 1".
- Public functions have type hints and a docstring whose first line says
  what the function returns or does. Comments explain why, not what changed
  or when; history belongs in git.
- Keep functions short enough to read at once (guideline: about 50 lines).
  Split by responsibility, not by line count alone.
- Error messages state what is wrong, the offending value or sample ID, and
  how to fix it.
- Follow the surrounding style: standard library first, then third-party,
  then local imports; f-strings; `pathlib.Path` for paths; dataclasses for
  structured records.
- No dead code, commented-out code, or unused parameters kept "for later".

## 3. Configs

### Layout

```
configs/
  schema.json                  JSON Schema for every non-legacy config (tested)
  base.json                    shared defaults: model, tokenizer, data, intervention, training
  <task-id>/<name>.json        one experiment; only differences from what it extends
  datasets/<name>.json         how a registered dataset was built (generator, seeds, sizes, dedup sources)
  audit.json, phase2.json      legacy, frozen at these paths
```

### Format

```jsonc
{
  "schema_version": 1,
  "extends": "../base.json",            // optional; path relative to this file
  "task": "layer-sweep",                // must equal the parent directory name (tested)
  "name": "gpt2-small",                 // must equal the file stem (tested)
  "model": {"name": "gpt2", "revision": "<pinned>"},
  "data": {"train": "legacy_v1/train", "validation": "val_indist_v1/validation", "test": "legacy_v1/test"},
  "intervention": {"target_variable": "position", "component": "block_output",
                   "layer": 8, "location": "N", "rank": 1},
  "training": {"epochs": 10, "batch_size": 20, "learning_rate": 0.01,
               "schedule": "legacy_per_update_linearlr"},
  "grid": {"intervention.layer": "all", "seed": [42, 43, 44]},
  "selection": {"metric": "validation_iia", "aggregate": "mean_over_seeds",
                "tie_break": "lowest_layer", "evaluate_after_lock": ["test"]}
}
```

- Merge: objects merge recursively; lists and scalars replace. The resolved
  config is what runs and what is saved.
- `grid` keys are dotted paths into the config; values are lists or `"all"`
  (resolved from the model, for example its layer count). Conditions are the
  Cartesian product, run in the listed key order.
- Datasets are referenced by `<dataset>/<split>` names from
  `data/REGISTRY.md`, never by file path.
- Keys are `snake_case`. Every key is defined in `schema.json`; unknown keys
  are an error **(tested)**.
- Changing what an existing key means requires bumping `schema_version` and a
  PROTOCOL change-log entry.

## 4. Outputs

```
outputs/<task-id>/<YYYYMMDD>-<name>/          full run
outputs/<task-id>/smoke-<YYYYMMDD>-<name>/    smoke run
  run.json            git commit, clean-tree flag, command, resolved config and its SHA-256,
                      dataset hashes, environment, start/end time, status
  resolved_config.json
  conditions/<axis>=<value>/.../              per-condition artifacts and result.json
  summary.md, *.csv, figures/                 regenerated from saved files by `report`
```

- The experiment ID is derived from the config name and the start date. A
  second run of the same config on the same day gets the suffix `-2`, `-3`, ….
- Full runs refuse to start when the git working tree has uncommitted changes
  under `src/`, `configs/`, or `data/`. Smoke runs may run on a dirty tree
  and record that fact.
- Completed outputs are never edited. A resumed run only adds missing
  conditions after verifying hashes of existing ones.
- Every output directory has `run.json` **(tested)**.
- Legacy outputs (`outputs/audit/`, `outputs/phase2/`, …) keep their paths.

## 5. Scripts

- `scripts/<verb>_<object>.py` is an entry point: argparse, then one call into
  the package. Keep under 100 lines and import from `ioi_das` **(tested)**.
  Prefer adding a CLI subcommand over adding a script.
- `scripts/adhoc/YYYYMMDD-<topic>.py` holds one-off investigations. Nothing
  imports them; they may be deleted at any time. Logic needed a second time
  moves into the package.

### Legacy entry points

When a generic replacement exists, remove the old command, script, or loader
instead of keeping it working. Old results stay where they are and are
reproduced by checking out the commit recorded in their `run.json` or
`result.json`. Snapshots are kept; their entry points are not maintained.

## 6. Tests

- Every new option or bug fix gets a focused test.
- Regression tests pin key published numbers so refactors cannot silently
  change science. At minimum: the single-condition run (layer 8, N, rank 1,
  seed 42) gives initial train IIA 94/200, final train IIA 173/200, and test
  IIA 79/100, with the saved alignment SHA-256 in
  `outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full/result.json`.
  GPU regression tests are marked so they can be skipped on CPU.
- `tests/test_conventions.py` enforces the rules marked (tested).
- Run: `$PY -B -m pytest -q` (see README for `$PY`).

## 7. Git

| Thing | Mechanism | Example |
| --- | --- | --- |
| Meeting snapshot | Annotated tag on `main` when the brief is final | `meeting/2026-10-15` |
| Code change | Branch from `main` named in its brief; merge when acceptance passes; then delete | `feat/config-pipeline` |
| Exploration | `spike/<topic>`; never merged directly; rewrite cleanly if kept | `spike/boundless-das` |
| Experiment | No branch: config + outputs committed on `main` | `results(layer-sweep): …` |
| Superseded attempt | Kept as a reference branch, not merged | `m3-complete-20261015` |

Commit messages: `<type>(<scope>): <summary>`, imperative, ≤ 72 characters,
with an optional body explaining why.

| Type | Use |
| --- | --- |
| `feat` | New capability in `src/` |
| `fix` | Bug fix |
| `refactor` | Behavior-preserving restructure (regression tests must pass) |
| `test` | Tests only |
| `docs` | Documentation, meeting notes, briefs |
| `config` | New or changed experiment configs |
| `data` | New registered dataset |
| `results` | Outputs of a completed run plus the STATUS update; summary names the key number |

Scope is a task ID or module name, for example
`results(layer-sweep): 20261016-gpt2-small — layer 8, val IIA 0.83`.

`main` must always pass the test suite. Push only with the user's
authorization.
