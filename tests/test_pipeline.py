"""Check orchestration with temporary saved artifacts and a lightweight runner."""

from dataclasses import replace
from contextlib import contextmanager
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
    monkeypatch.setattr(pipeline, "_model_metadata", lambda *options: {
        "name": "gpt2", "revision": "a" * 40, "parameter_count": 124439808,
        "layer_count": 12, "hidden_size": 768})
    monkeypatch.setattr(pipeline, "_implementation_hashes", lambda: {"pipeline.py": "b" * 64})
    monkeypatch.setattr(pipeline, "_dataset_inputs", lambda root, options:
                        ({"train": [], "test": []}, {}, {},
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
    assert first["model"] == {
        "name": "gpt2", "revision": "a" * 40, "parameter_count": 124439808,
        "layer_count": 12, "hidden_size": 768}
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


@pytest.fixture
def selection_runtime(runtime, monkeypatch):
    config = replace(load_config(ROOT / "configs/layer-sweep/gpt2-small.json"),
                     project_root=runtime["config"].project_root)
    events = []
    shared_runtime = object()
    runtime_loads = []

    @contextmanager
    def load_runtime(**options):
        assert sum(event[0] == "train" for event in events) == 36
        runtime_loads.append(options)
        yield shared_runtime

    monkeypatch.setattr(pipeline, "evaluation_runtime", load_runtime)
    pairs = {"train": ["training sample"], "validation": ["selection sample"], "test": ["locked sample"]}
    hashes = {"legacy_v1/train": "c" * 64, "val_indist_v1/validation": "e" * 64,
              "legacy_v1/test": "d" * 64}
    datasets = {split: {"reference": reference, "sha256": hashes[reference]}
                for split, reference in config["data"].items()}
    monkeypatch.setattr(pipeline, "_dataset_inputs", lambda root, options: (pairs, datasets, {}, hashes))
    monkeypatch.setattr(report, "generate_report", lambda output: {})

    def train_condition(output, visible_pairs, **options):
        assert "test" not in visible_pairs
        assert options["evaluation_splits"] == ("train", "validation")
        events.append(("train", options["layer"], options["seed"]))
        output.mkdir(parents=True)
        checkpoint = output / "alignment.pt"
        checkpoint.write_bytes(f"alignment {options['layer']} {options['seed']}".encode())
        correct = 166 if options["layer"] == 8 else 0
        result = {"status": "complete", "run_kind": "smoke" if options["smoke"] else "full",
                  "seed": options["seed"], "condition": {"layer": options["layer"]},
                  "metrics": {"validation": {"iia": correct / 200, "iia_correct": correct, "iia_total": 200}},
                  "artifacts": {"alignment.pt": sha256_file(checkpoint)}}
        _save(output / "result.json", result)
        return result

    def evaluate_locked(output, checkpoint, **options):
        assert options["runtime"] is shared_runtime
        assert set(options["pairs"]) == {"test"}
        selection_path = options["selection_path"]
        assert selection_path.is_file()
        assert sha256_file(selection_path) == options["selection_sha256"]
        selected = json.loads(selection_path.read_text(encoding="utf-8"))
        assert selected["selected_layer"] == 8
        assert len(selected["values"]) == 36
        assert sum(event[0] == "train" for event in events) == 36
        assert sha256_file(checkpoint) == options["checkpoint_sha256"]
        events.append(("test", options["layer"], options["seed"]))
        output.mkdir(parents=True)
        predictions = output / "test_predictions.jsonl"
        predictions.write_text('{"sample_id":"locked sample"}\n', encoding="utf-8")
        result = {"status": "complete", "seed": options["seed"], "condition": {"layer": options["layer"]},
                  "metrics": {"test": {"iia": 0.79, "iia_correct": 79, "iia_total": 100}},
                  "selection_sha256": options["selection_sha256"],
                  "checkpoint_sha256": options["checkpoint_sha256"],
                  "artifacts": {predictions.name: sha256_file(predictions)}}
        _save(output / "result.json", result)
        return result

    monkeypatch.setattr(pipeline, "run_condition", train_condition)
    monkeypatch.setattr(pipeline, "evaluate_checkpoint", evaluate_locked)
    return {**runtime, "config": config, "events": events, "train": train_condition,
            "evaluate": evaluate_locked, "runtime_loads": runtime_loads}


def test_all_conditions_finish_before_lock_and_every_checkpoint_is_evaluated(selection_runtime, monkeypatch):
    primary_snapshots = {}
    original = selection_runtime["evaluate"]

    def evaluate(output, checkpoint, **options):
        primary = output.parents[2] / "conditions"
        if not primary_snapshots:
            primary_snapshots.update(_snapshot(primary))
        result = original(output, checkpoint, **options)
        assert _snapshot(primary) == primary_snapshots
        return result

    monkeypatch.setattr(pipeline, "evaluate_checkpoint", evaluate)
    result = pipeline.run_experiment(selection_runtime["config"])
    assert result["status"] == "complete"
    assert len(result["conditions"]) == len(result["post_lock"]) == 36
    assert all(row["status"] == "complete" for row in result["conditions"] + result["post_lock"])
    events = selection_runtime["events"]
    assert [row[0] for row in events] == ["train"] * 36 + ["test"] * 36
    expected = {(layer, seed) for layer in range(12) for seed in (42, 43, 44)}
    assert {(layer, seed) for kind, layer, seed in events if kind == "test"} == expected
    output = Path(result["experiment_dir"])
    assert sha256_file(output / "selection.json") == result["selection_sha256"]
    assert primary_snapshots
    assert len(selection_runtime["runtime_loads"]) == 1


def test_selection_smoke_never_evaluates_test_or_creates_a_lock(selection_runtime):
    result = pipeline.run_experiment(selection_runtime["config"], smoke=True)
    output = Path(result["experiment_dir"])
    assert result["status"] == "complete"
    assert len(result["conditions"]) == 36
    assert not result.get("post_lock")
    assert not (output / "selection.json").exists()
    assert not (output / "post_lock").exists()
    assert not result.get("selection_sha256")
    assert [event[0] for event in selection_runtime["events"]] == ["train"] * 36
    assert selection_runtime["runtime_loads"] == []


def test_failed_primary_condition_prevents_lock_and_locked_evaluations(selection_runtime, monkeypatch):
    original = selection_runtime["train"]

    def fail(output, pairs, **options):
        if options["layer"] == 2 and options["seed"] == 43:
            raise RuntimeError("primary condition failed")
        return original(output, pairs, **options)

    monkeypatch.setattr(pipeline, "run_condition", fail)
    with pytest.raises(RuntimeError, match="primary condition failed"):
        pipeline.run_experiment(selection_runtime["config"])
    parent = selection_runtime["config"].project_root / "outputs" / "layer-sweep"
    output, = parent.iterdir()
    metadata = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert any(condition["status"] == "failed" for condition in metadata["conditions"])
    assert all(condition["status"] == "pending" for condition in metadata["post_lock"])
    assert not (output / "selection.json").exists()
    assert not (output / "post_lock").exists()
    assert all(event[0] == "train" for event in selection_runtime["events"])


@pytest.mark.parametrize("target", ["selection", "post_lock_result", "post_lock_artifact"])
def test_selection_resume_rejects_changed_lock_or_locked_evidence(selection_runtime, target):
    result = pipeline.run_experiment(selection_runtime["config"])
    output = Path(result["experiment_dir"])
    if target == "selection":
        path = output / "selection.json"
    elif target == "post_lock_result":
        path = output / result["post_lock"][0]["path"] / "result.json"
    else:
        path = output / result["post_lock"][0]["path"] / "test_predictions.jsonl"
    path.write_text("changed saved scientific evidence", encoding="utf-8")
    before = _snapshot(output)
    events = list(selection_runtime["events"])
    with pytest.raises(ValueError, match="[Hh]ash mismatch"):
        pipeline.run_experiment(selection_runtime["config"], resume=output)
    assert _snapshot(output) == before
    assert selection_runtime["events"] == events


def test_completed_selection_resume_preserves_every_artifact(selection_runtime):
    result = pipeline.run_experiment(selection_runtime["config"])
    output = Path(result["experiment_dir"])
    before = _snapshot(output)
    events = list(selection_runtime["events"])
    assert pipeline.run_experiment(selection_runtime["config"], resume=output) == result
    assert _snapshot(output) == before
    assert selection_runtime["events"] == events
