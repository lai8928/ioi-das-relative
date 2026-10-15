"""Audit arbitrary registered splits while preserving earlier output evidence."""

import json
from pathlib import Path
import shutil

import pytest

from ioi_das import audit
from ioi_das.config import config_sha256
from ioi_das.data import sha256_file


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def audit_root(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    shutil.copy2(ROOT / "configs" / "base.json", tmp_path / "configs" / "base.json")
    shutil.copytree(ROOT / "data" / "generated", tmp_path / "data" / "generated")
    shutil.copy2(ROOT / "data" / "registry.json", tmp_path / "data" / "registry.json")
    monkeypatch.setattr(audit, "verify_upstream", lambda path: {"commit": audit.UPSTREAM_COMMIT})
    monkeypatch.setattr(audit, "_source_state", lambda root:
                        {"commit": "a" * 40, "clean_tree": True, "implementation_sha256": {"audit.py": "b" * 64}})
    return tmp_path


def test_legacy_audit_retains_exact_reference_counts_and_run_provenance(audit_root):
    command = ["python", "-m", "ioi_das.cli", "data", "audit", "--dataset", "legacy_v1"]
    summary = audit.run_audit("legacy_v1", audit_root, command)
    assert summary["status"] == "passed"
    assert summary["counts"] == {"train": 200, "test": 100}
    assert summary["fast_reference_comparisons"] == {"inputs": 600, "continuations": 1800, "batched_sides": 30}
    assert summary["batch_individual_position_comparisons"] == 2400
    assert summary["answer_status_counts"] == {"supported_single_token": 1800}
    assert summary["unsupported_answer_checks"] == []
    assert summary["focused_checks"] == "passed"
    output = Path(summary["output_dir"])
    assert output.parent == audit_root / "outputs" / "data-audit"
    metadata = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "passed" and metadata["command"] == command
    assert metadata["config_sha256"] == config_sha256(metadata["resolved_config"])
    assert metadata["dataset_hashes"] == {f"legacy_v1/{split}": sha256_file(audit_root / "data" / "generated" / f"{split}.jsonl")
                                          for split in ("train", "test")}
    assert metadata["dataset_generation"]["legacy_v1"]["seed"] == 42
    assert metadata["environment"]["model_weights_loaded"] is False
    for name, digest in metadata["artifacts"].items():
        assert sha256_file(output / name) == digest


def test_validation_only_audit_works_and_repeat_uses_fresh_directory(audit_root):
    initial = audit.run_audit("val_indist_v1", audit_root)
    output = Path(initial["output_dir"])
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in output.iterdir()}
    repeated = audit.run_audit("val_indist_v1", audit_root)
    assert repeated["output_dir"] != initial["output_dir"]
    assert {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in output.iterdir()} == before
    assert initial["status"] == repeated["status"] == "passed"
    assert initial["counts"] == {"validation": 200}
    assert initial["fast_reference_comparisons"]["inputs"] == 400
    assert initial["answer_status_counts"] == {"supported_single_token": 1200}
    assert initial["unsupported_answer_checks"] == []
    assert "validation" in (output / "summary.md").read_text(encoding="utf-8")


def test_partial_audit_is_retained_with_failed_metadata(audit_root, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Tokenizer unavailable in cache")

    monkeypatch.setattr(audit, "load_tokenizers", fail)
    with pytest.raises(RuntimeError, match="Tokenizer unavailable"):
        audit.run_audit("legacy_v1", audit_root)
    output, = (audit_root / "outputs" / "data-audit").iterdir()
    metadata = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["error"] == "RuntimeError: Tokenizer unavailable in cache"
    assert metadata["completed_at_utc"]
    assert (output / "resolved_config.json").is_file()


def test_unknown_dataset_is_rejected_without_allocating_output(audit_root):
    with pytest.raises(ValueError, match="Unknown dataset"):
        audit.run_audit("missing", audit_root)
    assert not (audit_root / "outputs").exists()
