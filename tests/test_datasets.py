"""Verify registry integrity and immutable, bounded, deduplicated dataset builds."""

import json
from pathlib import Path
import shutil

import jsonschema
import pytest

from ioi_das import data
from ioi_das.data import sha256_file
from ioi_das.datasets import (
    build_dataset,
    load_dataset,
    load_dataset_spec,
    load_registry,
    split_inventory,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_SHA256 = "f62945c14803c2d9b8832b736bf5dd0d79226ea2e5fa7727b5aaa32aa54ba8e5"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    generated = tmp_path / "data" / "generated"
    generated.mkdir(parents=True)
    for name in ("train.jsonl", "test.jsonl", "manifest.json"):
        shutil.copyfile(PROJECT_ROOT / "data" / "generated" / name, generated / name)
    registry = load_registry(PROJECT_ROOT)
    registry["datasets"] = {"legacy_v1": registry["datasets"]["legacy_v1"]}
    write_json(tmp_path / "data" / "registry.json", registry)
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "pyvene_upstream").symlink_to(PROJECT_ROOT / "vendor" / "pyvene_upstream")
    return tmp_path


def recipe(project, name="example_v1", **changes):
    spec = {
        "schema_version": 1,
        "name": name,
        "purpose": "Test immutable, deduplicated validation generation.",
        "generator": {"name": "original_position", "source_split": "train", "seed": 314159, "max_batches": 10},
        "splits": {"validation": {"ABB->BAB": 3, "BAB->ABB": 3}},
        "deduplicate_against": ["legacy_v1"],
        **changes,
    }
    path = project / "configs" / "datasets" / f"{name}.json"
    write_json(path, spec)
    return path


def test_registry_resolves_splits_from_different_directories():
    train = load_dataset("legacy_v1/train", PROJECT_ROOT)
    validation = load_dataset("val_indist_v1/validation", PROJECT_ROOT)
    assert len(train.pairs) == len(validation.pairs) == 200
    assert train.directory != validation.directory
    assert validation.sha256 == VALIDATION_SHA256
    assert {pair.split for pair in validation.pairs} == {"validation"}


@pytest.mark.parametrize("reference", ["missing/train", "legacy_v1/validation", "../train", "legacy_v1"])
def test_unregistered_or_invalid_references_fail(reference):
    with pytest.raises(ValueError, match="reference|Unregistered"):
        load_dataset(reference, PROJECT_ROOT)


@pytest.mark.parametrize("filename, message", [("train.jsonl", "Split SHA-256"), ("manifest.json", "Manifest SHA-256")])
def test_hash_mismatch_is_rejected(project, filename, message):
    path = project / "data" / "generated" / filename
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match=message):
        load_dataset("legacy_v1/train", project)


def test_registry_manifest_count_disagreement_is_rejected(project):
    registry_path = project / "data" / "registry.json"
    registry = load_registry(project)
    registry["datasets"]["legacy_v1"]["splits"]["train"]["count"] += 1
    write_json(registry_path, registry)
    with pytest.raises(ValueError, match="metadata disagrees"):
        load_dataset("legacy_v1/train", project)


def test_reuse_after_generator_source_edit_uses_recorded_hash_as_provenance(project, monkeypatch):
    changed_generator = project / "src" / "ioi_das" / "data.py"
    changed_generator.parent.mkdir(parents=True)
    changed_generator.write_bytes(Path(data.__file__).read_bytes() + b"\n# A later diagnostic edit.\n")
    monkeypatch.setattr(data, "__file__", str(changed_generator))
    loaded = load_dataset("legacy_v1/train", project)
    assert sha256_file(changed_generator) != loaded.manifest["generation"]["generator_sha256"]
    assert len(loaded.pairs) == 200


def test_build_deduplicates_existing_datasets_and_all_accepted_pairs(project):
    path = recipe(project, splits={"train": {"ABB->BAB": 3}, "validation": {"ABB->BAB": 3, "BAB->ABB": 3}})
    built = build_dataset(path)
    assert built["dataset"] == "example_v1"
    old_pairs = load_dataset("legacy_v1/train", project).pairs + load_dataset("legacy_v1/test", project).pairs
    blocked_texts, blocked_groups = split_inventory(old_pairs)
    accepted_texts, accepted_groups = set(), set()
    for split in ("train", "validation"):
        dataset = load_dataset(f"example_v1/{split}", project)
        for pair in dataset.pairs:
            texts, groups = split_inventory([pair])
            assert not texts & (blocked_texts | accepted_texts)
            assert not groups & (blocked_groups | accepted_groups)
            accepted_texts.update(texts)
            accepted_groups.update(groups)
    manifest = json.loads((project / built["directory"] / "manifest.json").read_text())
    assert manifest["deduplication"]["sources"]["legacy_v1/train"]["sha256"] == load_dataset("legacy_v1/train", project).sha256


def test_build_refuses_to_overwrite_and_preserves_all_bytes(project):
    path = recipe(project)
    built = build_dataset(path, project)
    directory = project / built["directory"]
    saved = {file.name: file.read_bytes() for file in directory.iterdir()}
    registry_bytes = (project / "data" / "registry.json").read_bytes()
    with pytest.raises(ValueError, match="never overwrite"):
        build_dataset(path, project)
    assert saved == {file.name: file.read_bytes() for file in directory.iterdir()}
    assert registry_bytes == (project / "data" / "registry.json").read_bytes()


def test_generation_bound_failure_never_writes_a_partial_dataset(project):
    path = recipe(project, generator={"name": "original_position", "source_split": "train", "seed": 42, "max_batches": 1})
    registry_bytes = (project / "data" / "registry.json").read_bytes()
    with pytest.raises(ValueError, match="exhausted max_batches=1"):
        build_dataset(path, project)
    assert not (project / "data" / "generated" / "example_v1").exists()
    assert registry_bytes == (project / "data" / "registry.json").read_bytes()


def test_validation_build_reproduces_the_reference_exact_bytes(project):
    path = project / "configs" / "datasets" / "val_indist_v1.json"
    path.parent.mkdir(parents=True)
    shutil.copyfile(PROJECT_ROOT / "configs" / "datasets" / path.name, path)
    result = build_dataset(path, project)
    assert result["splits"]["validation"]["sha256"] == VALIDATION_SHA256
    assert result["deduplication"]["candidate_seeds"] == [314159, 314160, 314161]
    assert result["deduplication"]["rejections"] == {"prompt_overlap": 1}


def test_dataset_recipes_have_their_own_schema():
    directory = PROJECT_ROOT / "configs" / "datasets"
    schema = json.loads((directory / "schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    for path in directory.glob("*.json"):
        if path.name != "schema.json":
            assert load_dataset_spec(path)["name"] == path.stem


def test_dataset_recipe_rejects_unknown_options(project):
    with pytest.raises(ValueError, match="unrecognized_option"):
        load_dataset_spec(recipe(project, unrecognized_option=True))
