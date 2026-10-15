"""Resolve experiment grids, preserve run provenance, and execute missing conditions."""

from __future__ import annotations

from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime, timezone
from itertools import product
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .config import ResolvedConfig, config_sha256, set_path, validate_config
from .data import sha256_file
from .experiment import evaluate_checkpoint, evaluation_runtime, run_condition


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    # Grid insertion order determines condition order and must survive saving.
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def expand_grid(config: ResolvedConfig, layer_count: int | None = None) -> list[dict[str, Any]]:
    """Return Cartesian conditions in the configured axis order, including a size-one grid."""
    values = config.to_dict()
    axes = values.get("grid", {})
    choices = []
    for key, options in axes.items():
        if key in {"task", "name", "schema_version", "grid"} or key.startswith(("data.", "grid.")):
            raise ValueError(f"Grid axis {key!r} changes experiment identity or data; use a separate config.")
        if options == "all":
            if key != "intervention.layer" or layer_count is None:
                raise ValueError(f"Grid axis {key!r} cannot resolve \"all\"; provide the cached model layer count.")
            options = list(range(layer_count))
        choices.append(options)
    conditions = []
    seen = set()
    for combination in product(*choices):
        resolved = deepcopy(values)
        resolved.pop("grid", None)
        selected = dict(zip(axes, combination))
        for key, value in selected.items():
            set_path(resolved, key, value)
        validate_config(resolved, config.project_root)
        intervention = resolved["intervention"]
        if layer_count is not None and intervention["layer"] >= layer_count:
            raise ValueError(f"Layer {intervention['layer']} exceeds cached model's {layer_count} layers; fix intervention.layer.")
        parts = [f"{key}={quote(str(value), safe='')}" for key, value in selected.items()]
        if not parts:
            parts = [f"intervention.layer={intervention['layer']}", f"seed={resolved['seed']}"]
        path = str(Path("conditions", *parts))
        if path in seen:
            raise ValueError(f"Duplicate grid condition {path}; remove repeated axis values.")
        seen.add(path)
        conditions.append({"path": path, "axes": selected, "resolved_config": resolved, "status": "pending"})
    return conditions


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _git_state(root: Path) -> dict:
    return {"commit": _git(root, "rev-parse", "HEAD"),
            "clean_tree": not bool(_git(root, "status", "--porcelain")),
            "protected_tree_clean": not bool(_git(root, "status", "--porcelain", "--untracked-files=all",
                                                "--", "src", "configs", "data"))}


def _dataset_inputs(root: Path, data_options: dict) -> tuple[dict, dict, dict, dict]:
    from .audit import verify_upstream
    from .datasets import load_dataset

    pairs, datasets, hashes = {}, {}, {}
    for split, reference in data_options.items():
        saved = load_dataset(reference, root)
        pairs[split] = saved.pairs
        datasets[split] = {"reference": reference, "path": str(saved.path),
                           "sha256": saved.sha256, "manifest_path": str(saved.manifest_path),
                           "manifest_sha256": saved.manifest_sha256,
                           "generation": saved.manifest.get("generation", {})}
        hashes[reference] = saved.sha256
        hashes[f"{saved.name}/manifest"] = saved.manifest_sha256
    provenance = verify_upstream(root / "vendor/pyvene_upstream")
    return pairs, datasets, provenance, hashes


def _layer_count(model_options: dict) -> int:
    from transformers.utils.hub import cached_file

    path = cached_file(model_options["name"], "config.json", revision=model_options["revision"], local_files_only=True)
    return int(_read_json(Path(path))["n_layer"])


def _allocate_output(root: Path, task: str, name: str, smoke: bool) -> Path:
    date = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y%m%d")
    identifier = f"{'smoke-' if smoke else ''}{date}-{name}"
    parent = root / "outputs" / task
    parent.mkdir(parents=True, exist_ok=True)
    suffix = 1
    while True:
        output = parent / (identifier if suffix == 1 else f"{identifier}-{suffix}")
        try:
            output.mkdir()
            return output
        except FileExistsError:
            suffix += 1


def _verify_complete(output: Path, condition: dict) -> None:
    directory = output / condition["path"]
    result_path = directory / "result.json"
    expected_result = condition.get("result_sha256")
    if not expected_result or not result_path.is_file() or sha256_file(result_path) != expected_result:
        raise ValueError(f"Condition result hash mismatch: {result_path}; restore saved evidence.")
    result = _read_json(result_path)
    if result["status"] != "complete" or not result.get("artifacts"):
        raise ValueError(f"Incomplete condition result: {result_path}; preserve this run and start another.")
    for name, digest in result["artifacts"].items():
        artifact = directory / name
        if not artifact.is_file() or sha256_file(artifact) != digest:
            raise ValueError(f"Condition artifact hash mismatch: {artifact}; restore saved evidence.")


def _resume_output(config: ResolvedConfig, smoke: bool, resume: bool | Path) -> Path:
    if not isinstance(resume, bool):
        return Path(resume).expanduser().resolve()
    candidates = []
    for path in (config.project_root / "outputs" / config["task"]).glob("*/run.json"):
        metadata = _read_json(path)
        if metadata.get("config_sha256") == config.sha256 and metadata.get("run_kind") == ("smoke" if smoke else "full"):
            candidates.append(path.parent)
    if not candidates:
        raise ValueError("No matching saved run to resume; omit --resume to create a run.")
    return max(candidates, key=lambda path: _read_json(path / "run.json")["started_at_utc"])


def _resume_metadata(output: Path, config: ResolvedConfig, smoke: bool, hashes: dict,
                     conditions: list[dict]) -> dict:
    metadata = _read_json(output / "run.json")
    saved_config = _read_json(output / "resolved_config.json")
    if (config_sha256(saved_config) != config.sha256 or metadata["config_sha256"] != config.sha256
            or config_sha256(metadata["resolved_config"]) != config.sha256):
        raise ValueError(f"Config hash mismatch at {output}; restore the saved config or start a new run.")
    if metadata["run_kind"] != ("smoke" if smoke else "full") or metadata["dataset_hashes"] != hashes:
        raise ValueError(f"Dataset hashes or run kind differ at {output}; restore the original inputs.")
    if metadata.get("implementation_sha256") != _implementation_hashes():
        raise ValueError(f"Implementation hashes differ at {output}; restore the original source before resuming.")
    planned = [(condition["path"], condition["resolved_config"]) for condition in conditions]
    saved = [(condition["path"], condition["resolved_config"]) for condition in metadata["conditions"]]
    if planned != saved:
        raise ValueError(f"Condition grid differs at {output}; use the original config.")
    for condition in metadata["conditions"]:
        if condition["status"] == "complete":
            _verify_complete(output, condition)
        elif (output / condition["path"]).exists() and any((output / condition["path"]).iterdir()):
            condition["status"] = "failed"
            condition.setdefault("error", "Partial condition retained; start a new experiment to retry it.")
    if metadata.get("selection_sha256"):
        path = output / "selection.json"
        if not path.is_file() or sha256_file(path) != metadata["selection_sha256"]:
            raise ValueError(f"Selection hash mismatch at {path}; restore the immutable lock.")
    for record in metadata.get("post_lock", []):
        if record["status"] == "complete":
            _verify_complete(output, record)
        elif (output / record["path"]).exists() and any((output / record["path"]).iterdir()):
            record["status"] = "failed"
            record.setdefault("error", "Partial locked evaluation retained; start a new run to retry it.")
    return metadata


def _implementation_hashes() -> dict:
    return {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))}


def _execute(output: Path, metadata: dict, pairs: dict, datasets: dict, provenance: dict,
             smoke: bool) -> dict:
    from .report import generate_report

    metadata["status"] = "running"
    metadata.pop("error", None)
    _write_json(output / "run.json", metadata)
    locked_splits = tuple(metadata["resolved_config"].get("selection", {}).get("evaluate_after_lock", []))
    evaluation_splits = tuple(split for split in pairs if split not in locked_splits)
    if smoke:
        evaluation_splits = tuple(split for split in evaluation_splits if split != "test")
    visible_pairs = {split: pairs[split] for split in evaluation_splits}
    try:
        for condition in metadata["conditions"]:
            if condition["status"] == "complete":
                continue
            directory = output / condition["path"]
            if directory.exists() and any(directory.iterdir()):
                continue
            values = condition["resolved_config"]
            intervention = values["intervention"]
            condition["status"] = "running"
            _write_json(output / "run.json", metadata)
            try:
                run_condition(
                    output / condition["path"], visible_pairs, model_options=values["model"],
                    tokenizer_options=values["tokenizer"], training_options=values["training"],
                    layer=intervention["layer"], rank=intervention["rank"], component=intervention["component"],
                    target_variable=intervention["target_variable"], location=intervention["location"],
                    seed=values["seed"], device_name=values["device"], cpu_threads=values["cpu_threads"],
                    evaluation_batch_size=values["evaluation_batch_size"], dataset_metadata=datasets,
                    provenance=provenance, config_sha256=config_sha256(values),
                    evaluation_splits=evaluation_splits, smoke=smoke)
                condition["status"] = "complete"
                condition["result_sha256"] = sha256_file(output / condition["path"] / "result.json")
            except BaseException as error:
                condition["status"] = "failed"
                condition["error"] = f"{type(error).__name__}: {error}"
                raise
            finally:
                _write_json(output / "run.json", metadata)
        if all(condition["status"] == "complete" for condition in metadata["conditions"]) and locked_splits and not smoke:
            _evaluate_locked(output, metadata, pairs, datasets)
        if _implementation_hashes() != metadata["implementation_sha256"]:
            raise RuntimeError("Source files changed during this run; preserve its evidence and rerun committed source.")
        records = metadata["conditions"] + metadata.get("post_lock", [])
        metadata["status"] = "complete" if all(record["status"] == "complete" for record in records) else "failed"
    except BaseException as error:
        metadata["status"] = "failed"
        metadata["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        metadata["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_json(output / "run.json", metadata)
        if sys.exc_info()[0] is None:
            generate_report(output)
        else:
            try:
                generate_report(output)
            except (OSError, ValueError, KeyError) as report_error:
                print(f"Report generation also failed: {report_error}", file=sys.stderr)
    return metadata


def _evaluate_locked(output: Path, metadata: dict, pairs: dict, datasets: dict) -> None:
    with ExitStack() as resources:
        _evaluate_locked_records(output, metadata, pairs, datasets, resources)


def _evaluate_locked_records(output: Path, metadata: dict, pairs: dict,
                             datasets: dict, resources: ExitStack) -> None:
    from .selection import lock_selection

    if _implementation_hashes() != metadata["implementation_sha256"]:
        raise RuntimeError("Source files changed before selection; preserve this run and restore its source.")
    lock_selection(output, metadata)
    selection_path = output / "selection.json"
    metadata["selection_sha256"] = sha256_file(selection_path)
    _write_json(output / "run.json", metadata)
    conditions = {condition["path"]: condition for condition in metadata["conditions"]}
    locked_splits = metadata["resolved_config"]["selection"]["evaluate_after_lock"]
    runtime, runtime_options = None, None
    for record in metadata["post_lock"]:
        if record["status"] == "complete":
            continue
        directory = output / record["path"]
        if directory.exists() and any(directory.iterdir()):
            continue
        condition = conditions[record["condition_path"]]
        _verify_complete(output, condition)
        values = condition["resolved_config"]
        intervention = values["intervention"]
        checkpoint = output / condition["path"] / "alignment.pt"
        record["status"] = "running"
        _write_json(output / "run.json", metadata)
        try:
            options = {"model_options": values["model"], "tokenizer_options": values["tokenizer"],
                       "device_name": values["device"], "cpu_threads": values["cpu_threads"]}
            if runtime is None:
                runtime = resources.enter_context(evaluation_runtime(**options))
                runtime_options = options
            elif options != runtime_options:
                raise ValueError("Locked checkpoints require identical model, tokenizer, device, and CPU settings.")
            evaluate_checkpoint(
                directory, checkpoint, pairs={split: pairs[split] for split in locked_splits},
                model_options=values["model"], tokenizer_options=values["tokenizer"],
                layer=intervention["layer"], rank=intervention["rank"], location=intervention["location"],
                seed=values["seed"], device_name=values["device"], cpu_threads=values["cpu_threads"],
                evaluation_batch_size=values["evaluation_batch_size"], selection_path=selection_path,
                selection_sha256=metadata["selection_sha256"], checkpoint_sha256=sha256_file(checkpoint),
                dataset_metadata={split: datasets[split] for split in locked_splits}, runtime=runtime)
            record["status"] = "complete"
            record["result_sha256"] = sha256_file(directory / "result.json")
        except BaseException as error:
            record["status"] = "failed"
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            _write_json(output / "run.json", metadata)


def run_experiment(config: ResolvedConfig, smoke: bool = False,
                   resume: bool | Path = False, command: list[str] | None = None) -> dict:
    """Run a config on a clean source tree or verify and continue missing saved conditions."""
    state = _git_state(config.project_root)
    if not smoke and not state["protected_tree_clean"]:
        raise ValueError("Full runs require committed src/, configs/, and data/ changes; commit them before running.")
    pairs, datasets, provenance, hashes = _dataset_inputs(config.project_root, config["data"])
    conditions = expand_grid(config, _layer_count(config["model"]))
    if resume:
        output = _resume_output(config, smoke, resume)
        metadata = _resume_metadata(output, config, smoke, hashes, conditions)
        if metadata["status"] == "complete":
            return metadata
    else:
        output = _allocate_output(config.project_root, config["task"], config["name"], smoke)
        metadata = {
            "schema_version": 1, "experiment_dir": str(output), "run_kind": "smoke" if smoke else "full",
            "status": "pending", "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "git": state, "command": command if command is not None else sys.argv,
            "config_source_sha256": sha256_file(config.source_path),
            "resolved_config": config.to_dict(), "config_sha256": config.sha256,
            "dataset_hashes": hashes, "implementation_sha256": _implementation_hashes(),
            "environment": {"executable": sys.executable, "python": platform.python_version(),
                            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES")},
            "conditions": conditions,
        }
        if config.get("selection") and not smoke:
            metadata["post_lock"] = [
                {"path": str(Path("post_lock") / Path(condition["path"]).relative_to("conditions")),
                 "condition_path": condition["path"], "status": "pending"}
                for condition in conditions]
        _write_json(output / "run.json", metadata)
        _write_json(output / "resolved_config.json", config.to_dict())
    return _execute(output, metadata, pairs, datasets, provenance, smoke)
