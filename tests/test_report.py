"""Verify saved-result reporting without a machine-learning runtime."""

import csv
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


def test_report_regeneration_is_byte_identical(saved_experiment):
    first = generate_report(saved_experiment)
    artifacts = [saved_experiment / name for name in first["artifacts"]]
    before = {path: path.read_bytes() for path in artifacts}
    assert generate_report(saved_experiment) == first
    assert all(path.read_bytes() == content for path, content in before.items())


def test_report_cli_does_not_import_torch_or_model_libraries(saved_experiment):
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
