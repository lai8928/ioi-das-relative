"""Protect fixed samples against silent regeneration or corruption on reuse."""

from pathlib import Path

import pytest

from ioi_das.audit import ensure_saved_pairs, verify_upstream


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
