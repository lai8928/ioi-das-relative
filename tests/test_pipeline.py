"""Check orchestration with temporary saved artifacts and a lightweight runner."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from ioi_das.config import load_config
from ioi_das.data import sha256_file
from ioi_das import pipeline
from ioi_das import report


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "configs/single-condition-das/layer8-seed42.json"


def _snapshot(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_grid_preserves_axis_and_value_order_and_single_condition():
    config = load_config(REFERENCE, ['grid={"seed":[43,42],"intervention.layer":[8,7]}'])
    conditions = pipeline.expand_grid(config, layer_count=12)
    assert [list(row["axes"].items()) for row in conditions] == [
        [("seed", 43), ("intervention.layer", 8)],
        [("seed", 43), ("intervention.layer", 7)],
        [("seed", 42), ("intervention.layer", 8)],
        [("seed", 42), ("intervention.layer", 7)],
    ]
    assert conditions[0]["path"] == "conditions/seed=43/intervention.layer=8"
    assert [row["resolved_config"]["intervention"]["layer"] for row in conditions] == [8, 7, 8, 7]
    assert len(pipeline.expand_grid(load_config(REFERENCE), layer_count=12)) == 1
    assert config["intervention"]["layer"] == 8


def test_all_layers_requires_model_count_and_expands_in_order():
    config = load_config(REFERENCE, ['grid={"intervention.layer":"all"}'])
    with pytest.raises(ValueError, match="layer count"):
        pipeline.expand_grid(config)
    assert [row["axes"]["intervention.layer"] for row in pipeline.expand_grid(config, 12)] == list(range(12))
    with pytest.raises(ValueError, match="exceeds"):
        pipeline.expand_grid(load_config(REFERENCE, ["intervention.layer=12"]), 12)


def test_grid_cannot_change_dataset_identity():
    config = load_config(REFERENCE, ['grid={"data.train":["legacy_v1/train"]}'])
    with pytest.raises(ValueError, match="identity or data"):
        pipeline.expand_grid(config, 12)


def test_grid_validates_model_and_tokenizer_revision_together():
    config = load_config(REFERENCE, ['grid={"model.revision":["' + "a" * 40 + '"]}'])
    with pytest.raises(ValueError, match="same pinned revision"):
        pipeline.expand_grid(config, 12)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    schema = tmp_path / "configs/schema.json"
    schema.parent.mkdir()
    schema.write_bytes((ROOT / "configs/schema.json").read_bytes())
    config = replace(load_config(REFERENCE), project_root=tmp_path)
    state = {"commit": "a" * 40, "clean_tree": True, "protected_tree_clean": True}
    calls = []
    monkeypatch.setattr(pipeline, "_git_state", lambda root: dict(state))
    monkeypatch.setattr(pipeline, "_layer_count", lambda options: 12)
    monkeypatch.setattr(pipeline, "_implementation_hashes", lambda: {"pipeline.py": "b" * 64})
    monkeypatch.setattr(pipeline, "_dataset_inputs", lambda root, options:
                        ({"train": [], "test": []}, {}, {}, tmp_path / "saved-data",
                         {"legacy_v1/train": "c" * 64, "legacy_v1/test": "d" * 64}))

    def runner(output, pairs, **options):
        calls.append(options["seed"])
        output.mkdir(parents=True)
        artifact = output / "fixture.txt"
        artifact.write_text(f"saved fixture for seed {options['seed']}", encoding="utf-8")
        result = {"status": "complete", "run_kind": "smoke" if options["smoke"] else "full",
                  "seed": options["seed"], "condition": {"layer": options["layer"]},
                  "artifacts": {artifact.name: sha256_file(artifact)}, "metrics": {}}
        _save(output / "result.json", result)
        return result

    monkeypatch.setattr(pipeline, "run_condition", runner)
    return {"config": config, "state": state, "calls": calls, "runner": runner}


def test_dirty_full_run_is_refused_before_allocating_outputs(runtime):
    runtime["state"].update(clean_tree=False, protected_tree_clean=False)
    with pytest.raises(ValueError, match="require committed"):
        pipeline.run_experiment(runtime["config"])
    assert not (runtime["config"].project_root / "outputs").exists()
    assert runtime["calls"] == []


def test_dirty_smoke_records_provenance_and_allocates_unique_paths(runtime):
    runtime["state"].update(clean_tree=False, protected_tree_clean=False)
    first = pipeline.run_experiment(runtime["config"], smoke=True, command=["ioi-das", "run", "--smoke"])
    second = pipeline.run_experiment(runtime["config"], smoke=True)
    output = Path(first["experiment_dir"])
    assert output.name.startswith("smoke-")
    assert second["experiment_dir"] == str(output) + "-2"
    assert first["status"] == "complete"
    assert first["run_kind"] == "smoke"
    assert first["git"]["clean_tree"] is False
    assert first["command"] == ["ioi-das", "run", "--smoke"]
    assert first["config_sha256"] == runtime["config"].sha256
    assert first["dataset_hashes"]["legacy_v1/train"] == "c" * 64
    assert first["environment"]["executable"]
    assert first["started_at_utc"] and first["ended_at_utc"]
    assert json.loads((output / "resolved_config.json").read_text()) == runtime["config"].to_dict()
    assert (output / "summary.md").is_file()


def test_completed_resume_verifies_without_running_or_mutating(runtime):
    result = pipeline.run_experiment(runtime["config"])
    output = Path(result["experiment_dir"])
    before = _snapshot(output)
    resumed = pipeline.run_experiment(runtime["config"], resume=output)
    assert resumed == result
    assert runtime["calls"] == [42]
    assert _snapshot(output) == before


@pytest.mark.parametrize("target", ["artifact", "result", "saved_config", "embedded_config", "dataset", "implementation"])
def test_resume_rejects_changed_hashes_without_mutating(runtime, monkeypatch, target):
    result = pipeline.run_experiment(runtime["config"])
    output = Path(result["experiment_dir"])
    condition = output / result["conditions"][0]["path"]
    if target == "artifact":
        (condition / "fixture.txt").write_text("changed artifact")
    elif target == "result":
        (condition / "result.json").write_text("{}")
    elif target == "saved_config":
        path = output / "resolved_config.json"
        values = json.loads(path.read_text())
        values["seed"] = 43
        _save(path, values)
    elif target in {"embedded_config", "dataset"}:
        path = output / "run.json"
        values = json.loads(path.read_text())
        if target == "embedded_config":
            values["resolved_config"]["seed"] = 43
        else:
            values["dataset_hashes"]["legacy_v1/train"] = "0" * 64
        _save(path, values)
    else:
        monkeypatch.setattr(pipeline, "_implementation_hashes", lambda: {"pipeline.py": "0" * 64})
    before = _snapshot(output)
    with pytest.raises(ValueError, match="[Hh]ash"):
        pipeline.run_experiment(runtime["config"], resume=output)
    assert runtime["calls"] == [42]
    assert _snapshot(output) == before


def test_resume_runs_only_missing_conditions_and_keeps_complete_bytes(runtime, monkeypatch):
    config = replace(load_config(REFERENCE, ['grid={"seed":[42,43]}']),
                     project_root=runtime["config"].project_root)

    def interrupted(output, pairs, **options):
        if options["seed"] == 43:
            raise RuntimeError("fixture interruption before output allocation")
        return runtime["runner"](output, pairs, **options)

    monkeypatch.setattr(pipeline, "run_condition", interrupted)
    with pytest.raises(RuntimeError, match="fixture interruption"):
        pipeline.run_experiment(config)
    output = next((config.project_root / "outputs" / config["task"]).iterdir())
    failed = json.loads((output / "run.json").read_text())
    assert failed["status"] == "failed"
    assert [row["status"] for row in failed["conditions"]] == ["complete", "failed"]
    completed = output / failed["conditions"][0]["path"]
    before = _snapshot(completed)
    monkeypatch.setattr(pipeline, "run_condition", runtime["runner"])
    resumed = pipeline.run_experiment(config, resume=True)
    assert resumed["status"] == "complete"
    assert runtime["calls"] == [42, 43]
    assert _snapshot(completed) == before


def test_failed_partial_condition_is_retained_and_never_overwritten(runtime, monkeypatch):
    config = replace(load_config(REFERENCE, ['grid={"seed":[42,43,44]}']),
                     project_root=runtime["config"].project_root)

    def interrupted(output, pairs, **options):
        if options["seed"] != 43:
            return runtime["runner"](output, pairs, **options)
        output.mkdir(parents=True)
        (output / "partial.txt").write_text("preserve this partial evidence")
        raise RuntimeError("fixture interruption after saving partial output")

    monkeypatch.setattr(pipeline, "run_condition", interrupted)
    with pytest.raises(RuntimeError, match="fixture interruption"):
        pipeline.run_experiment(config)
    output = next((config.project_root / "outputs" / config["task"]).iterdir())
    saved = json.loads((output / "run.json").read_text())
    assert saved["status"] == "failed"
    assert [row["status"] for row in saved["conditions"]] == ["complete", "failed", "pending"]
    completed = output / saved["conditions"][0]["path"]
    partial = output / saved["conditions"][1]["path"]
    before = {completed: _snapshot(completed), partial: _snapshot(partial)}
    monkeypatch.setattr(pipeline, "run_condition", runtime["runner"])
    resumed = pipeline.run_experiment(config, resume=output)
    assert resumed["status"] == "failed"
    assert [row["status"] for row in resumed["conditions"]] == ["complete", "failed", "complete"]
    assert runtime["calls"] == [42, 44]
    assert all(_snapshot(directory) == content for directory, content in before.items())


def test_report_failure_does_not_mask_original_training_failure(runtime, monkeypatch, capsys):
    def fail_training(*args, **kwargs):
        raise RuntimeError("original fixture training failure")

    def fail_reporting(*args, **kwargs):
        raise ValueError("fixture reporting failure")

    monkeypatch.setattr(pipeline, "run_condition", fail_training)
    monkeypatch.setattr(report, "generate_report", fail_reporting)
    with pytest.raises(RuntimeError, match="original fixture training failure"):
        pipeline.run_experiment(runtime["config"])
    output = next((runtime["config"].project_root / "outputs" / runtime["config"]["task"]).iterdir())
    saved = json.loads((output / "run.json").read_text())
    assert "original fixture training failure" in saved["error"]
    assert "fixture reporting failure" in capsys.readouterr().err
