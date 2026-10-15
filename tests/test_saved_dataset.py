"""Protect registered samples against regeneration and source-provenance drift."""

import json
from pathlib import Path
import shutil

import pytest

from ioi_das import data
from ioi_das.datasets import load_dataset


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def saved_root(tmp_path):
    directory = tmp_path / "data" / "generated"
    directory.mkdir(parents=True)
    for name in ("manifest.json", "train.jsonl", "test.jsonl"):
        shutil.copy2(ROOT / "data" / "generated" / name, directory / name)
    registry = json.loads((ROOT / "data" / "registry.json").read_text(encoding="utf-8"))
    (tmp_path / "data" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return tmp_path


def _snapshot(directory):
    return {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in directory.iterdir()}


def test_registered_reuse_preserves_all_files(saved_root, monkeypatch):
    directory = saved_root / "data" / "generated"
    monkeypatch.setattr(data, "generate_pairs", lambda *args: pytest.fail("Saved pairs must never regenerate"))
    before = _snapshot(directory)
    initial = load_dataset("legacy_v1/train", saved_root)
    loaded = load_dataset("legacy_v1/train", saved_root)
    assert loaded.pairs == initial.pairs and loaded.manifest == initial.manifest
    assert len(loaded.pairs) == 200
    assert _snapshot(directory) == before


def test_split_hash_failure_does_not_regenerate(saved_root, monkeypatch):
    path = saved_root / "data" / "generated" / "train.jsonl"
    corrupted = path.read_bytes() + b"\n"
    path.write_bytes(corrupted)
    monkeypatch.setattr(data, "generate_pairs", lambda *args: pytest.fail("Saved pairs must never regenerate"))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_dataset("legacy_v1/train", saved_root)
    assert path.read_bytes() == corrupted


def test_generator_source_edit_is_provenance_only(saved_root, tmp_path, monkeypatch):
    directory = saved_root / "data" / "generated"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    edited_generator = tmp_path / "generator.py"
    edited_generator.write_bytes(Path(data.__file__).read_bytes() + b"\n# Diagnostic wording changed.\n")
    assert data.sha256_file(edited_generator) != manifest["generation"]["generator_sha256"]
    monkeypatch.setattr(data, "__file__", str(edited_generator))
    monkeypatch.setattr(data, "generate_pairs", lambda *args: pytest.fail("Saved pairs must never regenerate"))
    before = _snapshot(directory)
    loaded = load_dataset("legacy_v1/train", saved_root)
    assert loaded.manifest == manifest
    assert loaded.manifest["generation"]["seed"] == 42
    assert _snapshot(directory) == before


def test_manifest_provenance_edit_requires_new_registry_digest(saved_root, monkeypatch):
    path = saved_root / "data" / "generated" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["generation"]["generator_sha256"] = "0" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(data, "generate_pairs", lambda *args: pytest.fail("Saved pairs must never regenerate"))
    before = _snapshot(path.parent)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_dataset("legacy_v1/train", saved_root)
    assert _snapshot(path.parent) == before
