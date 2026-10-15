"""Protect fixed samples against silent regeneration or corruption on reuse."""

import json
from pathlib import Path
import shutil

import pytest

from ioi_das import data
from ioi_das.audit import LEGACY_MANIFEST_SHA256, ensure_saved_pairs, verify_upstream


ROOT = Path(__file__).resolve().parents[1]


def config(directory):
    return {"generated_dir": directory, "upstream_dir": ROOT / "vendor/pyvene_upstream",
            "seed": 42, "tokenizer": {"name": "gpt2", "revision": "original-tokenizer"}}


def test_reuse_preserves_all_files_and_allows_another_tokenizer(tmp_path):
    options = config(tmp_path)
    provenance = verify_upstream(options["upstream_dir"])
    initial, manifest, reused = ensure_saved_pairs(options, provenance)
    assert not reused
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()}
    options["tokenizer"] = {"name": "gpt2", "revision": "different-tokenizer"}
    loaded, reused_manifest, reused = ensure_saved_pairs(options, provenance)
    assert reused and loaded == initial and reused_manifest == manifest
    assert {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()} == before
    assert manifest["tokenizer_at_generation"]["revision"] == "original-tokenizer"


def test_dataset_hash_failure_does_not_regenerate(tmp_path):
    options = config(tmp_path)
    provenance = verify_upstream(options["upstream_dir"])
    ensure_saved_pairs(options, provenance)
    train = tmp_path / "train.jsonl"
    corrupted = train.read_bytes() + b"\n"
    train.write_bytes(corrupted)
    with pytest.raises(ValueError, match="Saved dataset hash mismatch"):
        ensure_saved_pairs(options, provenance)
    assert train.read_bytes() == corrupted


def test_seed_change_does_not_replace_saved_samples(tmp_path):
    options = config(tmp_path)
    provenance = verify_upstream(options["upstream_dir"])
    ensure_saved_pairs(options, provenance)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    options["seed"] = 43
    with pytest.raises(ValueError, match="Saved dataset generation metadata differs"):
        ensure_saved_pairs(options, provenance)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_pinned_legacy_dataset_reuses_historical_generator_after_source_edit(tmp_path, monkeypatch):
    directory = tmp_path / "saved"
    directory.mkdir()
    for name in ("manifest.json", "train.jsonl", "test.jsonl"):
        shutil.copy2(ROOT / "data/generated" / name, directory / name)
    manifest_path = directory / "manifest.json"
    assert data.sha256_file(manifest_path) == LEGACY_MANIFEST_SHA256
    manifest = json.loads(manifest_path.read_text())
    edited_generator = tmp_path / "generator.py"
    edited_generator.write_bytes(Path(data.__file__).read_bytes() + b"\n# Updated diagnostic wording.\n")
    assert data.sha256_file(edited_generator) != manifest["generation"]["generator_sha256"]
    monkeypatch.setattr(data, "__file__", str(edited_generator))
    monkeypatch.setattr(data, "generate_pairs", lambda *args: pytest.fail("Saved pairs must never regenerate"))
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in directory.iterdir()}
    options = config(directory)
    pairs, reused_manifest, reused = ensure_saved_pairs(options, verify_upstream(options["upstream_dir"]))
    assert reused and reused_manifest == manifest
    assert {split: len(records) for split, records in pairs.items()} == {"train": 200, "test": 100}
    assert {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in directory.iterdir()} == before


def test_corrupted_legacy_manifest_cannot_claim_historical_generator(tmp_path, monkeypatch):
    for name in ("manifest.json", "train.jsonl", "test.jsonl"):
        shutil.copy2(ROOT / "data/generated" / name, tmp_path / name)
    path = tmp_path / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["generation"]["generator_sha256"] = "0" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert data.sha256_file(path) != LEGACY_MANIFEST_SHA256
    monkeypatch.setattr(data, "generate_pairs", lambda *args: pytest.fail("Corrupted pairs must never regenerate"))
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()}
    options = config(tmp_path)
    with pytest.raises(ValueError, match="Saved dataset generation metadata differs"):
        ensure_saved_pairs(options, verify_upstream(options["upstream_dir"]))
    assert {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in tmp_path.iterdir()} == before
