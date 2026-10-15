"""Protect completed audit evidence when resolving command-line options."""

import json
from pathlib import Path
import tempfile

import pytest

from ioi_das.cli import load_config


ROOT = Path(__file__).resolve().parents[1]


def _audit_config(tmp_path: Path) -> tuple[Path, Path]:
    config = json.loads((ROOT / "configs/audit.json").read_text())
    config["project_root"] = str(tmp_path)
    config["output_dir"] = "audit"
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    output = tmp_path / "audit"
    output.mkdir()
    (output / "summary.json").write_text('{"status": "passed"}\n', encoding="utf-8")
    (output / "summary.md").write_text("Saved completed audit.\n", encoding="utf-8")
    return path, output


def test_default_completed_audit_uses_fresh_temporary_directory(tmp_path):
    path, output = _audit_config(tmp_path)
    before = {item.name: (item.read_bytes(), item.stat().st_mtime_ns) for item in output.iterdir()}
    config = load_config(path)
    destination = config["output_dir"]
    try:
        assert destination != output
        assert destination.parent == Path(tempfile.gettempdir())
        assert destination.name.startswith("ioi-das-audit-")
        assert destination.is_dir() and not list(destination.iterdir())
        assert {item.name: (item.read_bytes(), item.stat().st_mtime_ns)
                for item in output.iterdir()} == before
    finally:
        destination.rmdir()


def test_explicit_completed_audit_directory_is_refused(tmp_path):
    path, output = _audit_config(tmp_path)
    before = {item.name: (item.read_bytes(), item.stat().st_mtime_ns) for item in output.iterdir()}
    with pytest.raises(ValueError, match="Completed audit exists"):
        load_config(path, str(output))
    assert {item.name: (item.read_bytes(), item.stat().st_mtime_ns)
            for item in output.iterdir()} == before
