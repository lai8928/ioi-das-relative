"""Verify saved-result reporting without a machine-learning runtime."""

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from ioi_das.report import generate_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def saved_experiment(tmp_path):
    condition_path = "conditions/intervention.layer=8/seed=42"
    run = {"status": "failed", "run_kind": "smoke", "config_sha256": "a" * 64,
           "resolved_config": {"task": "single-condition-das", "name": "saved-fixture",
                               "data": {"test": "legacy_v1/test"}},
           "conditions": [{"path": condition_path, "status": "complete",
                           "axes": {"intervention.layer": 8, "seed": 42}},
                          {"path": "conditions/intervention.layer=8/seed=43", "status": "failed",
                           "axes": {"intervention.layer": 8, "seed": 43}, "error": "fixture failure"},
                          {"path": "conditions/intervention.layer=8/seed=44", "status": "pending",
                           "axes": {"intervention.layer": 8, "seed": 44}}]}
    result = {"status": "complete", "run_kind": "smoke", "seed": 42,
              "condition": {"layer": 8, "component": "block_output", "rank": 1,
                            "intervention_location": "N"},
              "metrics": {split: {"iia_correct": correct, "iia_total": total,
                                   "iia": correct / total, "factual_accuracy": 0.95}
                          for split, correct, total in (("initial_train", 94, 200),
                                                         ("train", 173, 200), ("test", 79, 100))}}
    _write_json(tmp_path / "run.json", run)
    _write_json(tmp_path / condition_path / "result.json", result)
    return tmp_path


def test_report_preserves_exact_saved_metrics_and_incomplete_conditions(saved_experiment):
    source_paths = [saved_experiment / "run.json", *saved_experiment.glob("conditions/**/result.json")]
    originals = {path: path.read_bytes() for path in source_paths}
    report = generate_report(saved_experiment)
    assert report["statuses"] == {"complete": 1, "failed": 1, "pending": 1}
    with (saved_experiment / "conditions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["status"] for row in rows] == ["complete", "failed", "pending"]
    assert rows[0]["initial_train_iia_correct"] == "94"
    assert rows[0]["initial_train_iia_total"] == "200"
    assert rows[0]["train_iia"] == "0.865"
    assert rows[0]["test_iia_correct"] == "79"
    assert rows[1]["train_iia"] == ""
    assert rows[1]["seed"] == "43"
    assert rows[1]["error"] == "fixture failure"
    summary = (saved_experiment / "summary.md").read_text()
    assert "**smoke**" in summary
    assert "not a full experimental result" in summary
    assert "Test IIA (descriptive)" in summary
    assert "previously inspected" in summary
    assert "94/200 = 0.47" in summary
    assert "173/200 = 0.865" in summary
    assert "79/100 = 0.79" in summary
    ET.parse(saved_experiment / "figures/iia.svg")
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("experiment_fixture", ["saved_experiment", "locked_experiment"])
def test_report_regeneration_is_byte_identical(request, experiment_fixture):
    saved_experiment = request.getfixturevalue(experiment_fixture)
    first = generate_report(saved_experiment)
    artifacts = [saved_experiment / name for name in first["artifacts"]]
    before = {path: path.read_bytes() for path in artifacts}
    assert generate_report(saved_experiment) == first
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize("experiment_fixture", ["saved_experiment", "locked_experiment"])
def test_report_cli_does_not_import_torch_or_model_libraries(request, experiment_fixture):
    saved_experiment = request.getfixturevalue(experiment_fixture)
    program = """
import importlib.abc
import sys

class BlockModelImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'transformers', 'pyvene'}:
            raise AssertionError('Report attempted a model import: ' + fullname)

sys.meta_path.insert(0, BlockModelImports())
from ioi_das.cli import main
sys.argv = ['ioi-das', 'report', '--experiment-dir', sys.argv[1]]
raise SystemExit(main())
"""
    completed = subprocess.run([sys.executable, "-B", "-c", program, str(saved_experiment)],
                               cwd=PROJECT_ROOT, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (saved_experiment / "summary.md").is_file()


def test_report_keeps_unlisted_saved_results_and_flags_missing_complete_results(saved_experiment):
    run_path = saved_experiment / "run.json"
    run = json.loads(run_path.read_text())
    run["conditions"].append({"path": "conditions/seed=45", "status": "complete", "axes": {"seed": 45}})
    _write_json(run_path, run)
    _write_json(saved_experiment / "conditions/seed=46/result.json", {"status": "failed", "seed": 46})
    report = generate_report(saved_experiment)
    assert report["statuses"] == {"complete": 1, "failed": 2, "pending": 1, "missing_result": 1}


def test_report_rejects_condition_paths_outside_saved_conditions(saved_experiment):
    run_path = saved_experiment / "run.json"
    run = json.loads(run_path.read_text())
    run["conditions"][0]["path"] = "../other-experiment"
    _write_json(run_path, run)
    with pytest.raises(ValueError, match="Condition path must be inside"):
        generate_report(saved_experiment)


@pytest.fixture
def locked_experiment(tmp_path):
    run = {"status": "complete", "run_kind": "full", "resolved_config": {
        "task": "layer-sweep", "name": "saved-fixture", "data": {"test": "legacy_v1/test"},
        "selection": {"evaluate_after_lock": ["test"]}}, "conditions": [], "post_lock": []}
    _write_json(tmp_path / "selection.json", {"selected_layer": 8, "metric": "validation_iia"})
    for layer in (7, 8):
        for seed in (42, 43, 44):
            condition_path = f"conditions/intervention.layer={layer}/seed={seed}"
            status = "complete" if layer == 8 else {42: "complete", 43: "failed", 44: "pending"}[seed]
            run["conditions"].append({"path": condition_path, "status": status,
                                      "axes": {"intervention.layer": layer, "seed": seed}})
            if status != "complete":
                continue
            validation = {42: 0.8, 43: 0.82, 44: 0.84}[seed] if layer == 8 else 0.17
            result = {"status": status, "seed": seed, "condition": {"layer": layer},
                      "metrics": {"train": {"iia": 0.865}, "validation": {"iia": validation}}}
            _write_json(tmp_path / condition_path / "result.json", result)
            post_lock_path = f"post_lock/intervention.layer={layer}/seed={seed}"
            result_path = tmp_path / post_lock_path / "result.json"
            _write_json(result_path, {"status": "complete", "metrics": {"test": {"iia": 0.79}},
                                      "selection_sha256": hashlib.sha256((tmp_path / "selection.json").read_bytes()).hexdigest()})
            run["post_lock"].append({"path": post_lock_path, "condition_path": condition_path,
                                     "status": "complete", "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest()})
    _write_json(tmp_path / "run.json", run)
    return tmp_path


def test_report_joins_hashed_post_lock_metrics_and_marks_incomplete_layers(locked_experiment):
    originals = {path: path.read_bytes() for path in locked_experiment.glob("**/*.json")}
    report = generate_report(locked_experiment)
    with (locked_experiment / "conditions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    assert [row["status"] for row in rows[:3]] == ["complete", "failed", "pending"]
    assert rows[0]["post_lock_status"] == "complete"
    assert rows[0]["test_iia"] == "0.79"
    assert rows[1]["post_lock_status"] == "pending"
    assert rows[1]["test_iia"] == ""
    with (locked_experiment / "layer_summary.csv").open(newline="", encoding="utf-8") as handle:
        layers = {(row["layer"], row["split"]): row for row in csv.DictReader(handle)}
    validation = layers["8", "validation"]
    assert float(validation["mean_iia"]) == pytest.approx(0.82)
    assert float(validation["seed_sample_sd"]) == pytest.approx(0.02)
    assert validation["completed_seeds"] == validation["expected_seeds"] == "3"
    assert validation["flag"] == "complete"
    incomplete = layers["7", "validation"]
    assert incomplete["completed_seeds"] == "1"
    assert incomplete["expected_seeds"] == "3"
    assert incomplete["flag"] == "incomplete"
    assert incomplete["seed_sample_sd"] == ""
    assert float(layers["8", "test"]["mean_iia"]) == pytest.approx(0.79)
    for name in report["artifacts"]:
        if name.endswith(".svg"):
            ET.parse(locked_experiment / name)
    validation_plot = (locked_experiment / "figures/validation_by_layer.svg").read_text()
    assert all(f"Seed {seed}" in validation_plot for seed in (42, 43, 44))
    assert "seed SD" in validation_plot
    assert "Selected layer: **8**" in (locked_experiment / "summary.md").read_text()
    assert all(path.read_bytes() == content for path, content in originals.items())


def test_report_rejects_post_lock_hash_mismatch(locked_experiment):
    result_path = locked_experiment / "post_lock/intervention.layer=8/seed=42/result.json"
    result_path.write_text(result_path.read_text() + "\n")
    with pytest.raises(ValueError, match="Post-lock result SHA-256 mismatch"):
        generate_report(locked_experiment)


def test_report_rejects_post_lock_results_without_selection_lock(locked_experiment):
    (locked_experiment / "selection.json").unlink()
    with pytest.raises(ValueError, match="Post-lock records require selection.json"):
        generate_report(locked_experiment)


def test_report_rejects_post_lock_results_from_another_selection_lock(locked_experiment):
    selection_path = locked_experiment / "selection.json"
    selection_path.write_text(selection_path.read_text() + "\n")
    with pytest.raises(ValueError, match="Post-lock selection SHA-256 mismatch"):
        generate_report(locked_experiment)


@pytest.mark.parametrize("status", ["pending", "failed", "running", "complete"])
def test_report_handles_preallocated_post_lock_cells_before_selection(locked_experiment, status):
    (locked_experiment / "selection.json").unlink()
    run_path = locked_experiment / "run.json"
    run = json.loads(run_path.read_text())
    run["status"] = "failed"
    for record in run["post_lock"]:
        (locked_experiment / record["path"] / "result.json").unlink()
        record["status"] = "pending"
        record.pop("result_sha256")
    run["post_lock"][0].update(status=status, error="saved failure" if status == "failed" else "")
    _write_json(run_path, run)
    if status in {"running", "complete"}:
        with pytest.raises(ValueError, match="Post-lock records require selection.json"):
            generate_report(locked_experiment)
        return
    report = generate_report(locked_experiment)
    assert report["conditions"] == 6
    with (locked_experiment / "conditions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    assert rows[0]["post_lock_status"] == status
    assert all(row["test_iia"] == "" for row in rows)
    assert {row["status"] for row in rows} == {"complete", "failed", "pending"}
    assert not (locked_experiment / "selection.json").exists()


def test_report_tracks_missing_and_failed_post_lock_results(locked_experiment):
    run_path = locked_experiment / "run.json"
    run = json.loads(run_path.read_text())
    record = run["post_lock"][1]
    (locked_experiment / record["path"] / "result.json").unlink()
    record = run["post_lock"][2]
    (locked_experiment / record["path"] / "result.json").unlink()
    record.update(status="failed", error="saved evaluation failure")
    _write_json(run_path, run)
    generate_report(locked_experiment)
    with (locked_experiment / "conditions.csv").open(newline="", encoding="utf-8") as handle:
        rows = {row["condition"]: row for row in csv.DictReader(handle)}
    assert rows[run["post_lock"][1]["condition_path"]]["post_lock_status"] == "missing_result"
    assert rows[run["post_lock"][2]["condition_path"]]["post_lock_status"] == "failed"
    assert "saved evaluation failure" in (locked_experiment / "summary.md").read_text()


def test_report_rejects_post_lock_paths_outside_saved_records(locked_experiment):
    run_path = locked_experiment / "run.json"
    run = json.loads(run_path.read_text())
    run["post_lock"][0]["path"] = "conditions/intervention.layer=8/seed=42"
    _write_json(run_path, run)
    with pytest.raises(ValueError, match="Post-lock path must be inside"):
        generate_report(locked_experiment)
