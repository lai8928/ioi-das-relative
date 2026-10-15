"""Verify registry integrity and immutable, bounded, deduplicated dataset builds."""

import json
from collections import Counter
from pathlib import Path
import shutil

import jsonschema
import pytest

from ioi_das import data
from ioi_das import datasets
from ioi_das.data import sha256_file
from ioi_das.datasets import (
    build_dataset,
    generation_capacity,
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


def test_generator_defaults_regenerate_the_registered_legacy_bytes(tmp_path):
    registry = load_registry(PROJECT_ROOT)["datasets"]["legacy_v1"]
    pairs = data.generate_pairs(PROJECT_ROOT / "vendor" / "pyvene_upstream", seed=42)
    explicit = data.generate_pairs(PROJECT_ROOT / "vendor" / "pyvene_upstream", seed=42,
                                    pairs_per_combination=50)
    assert pairs == explicit
    for split, records in pairs.items():
        path = tmp_path / f"{split}.jsonl"
        data.write_pairs(path, records)
        assert sha256_file(path) == registry["splits"][split]["sha256"]


def test_generator_size_parameter_controls_each_pattern_combination():
    pairs = data.generate_pairs(PROJECT_ROOT / "vendor" / "pyvene_upstream", seed=42,
                                pairs_per_combination=7)
    assert len(pairs["train"]) == 28
    assert len(pairs["test"]) == 14
    assert Counter(f"{pair.base.pattern}->{pair.source.pattern}" for pair in pairs["train"]) == {
        "ABB->ABB": 7, "ABB->BAB": 7, "BAB->ABB": 7, "BAB->BAB": 7}


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
def test_generator_size_requires_a_positive_integer(size):
    with pytest.raises(ValueError, match="pairs_per_combination"):
        data.generate_pairs(PROJECT_ROOT / "vendor" / "pyvene_upstream", pairs_per_combination=size)


def test_training_capacity_accounts_for_fixed_validation_and_legacy_test():
    excluded = (load_dataset("legacy_v1/test", PROJECT_ROOT).pairs +
                load_dataset("val_indist_v1/validation", PROJECT_ROOT).pairs)
    capacity = generation_capacity(PROJECT_ROOT / "vendor" / "pyvene_upstream", "train", excluded)
    assert capacity == {"source_split": "train",
                        "resource_counts": {"names": 49, "objects": 4, "places": 4, "templates": 2},
                        "semantic_group_capacity": 37632, "excluded_semantic_groups": 200,
                        "available_semantic_groups": 37432}


def test_impossible_dataset_capacity_fails_before_sampling_or_allocating(project, monkeypatch):
    path = recipe(project, splits={"train": {"ABB->ABB": 37633}})
    registry_bytes = (project / "data" / "registry.json").read_bytes()
    monkeypatch.setattr(datasets, "generate_pairs", lambda *args, **kwargs:
                        pytest.fail("Capacity preflight must happen before sampling"))
    with pytest.raises(ValueError, match="semantic-group capacity"):
        build_dataset(path, project)
    assert not (project / "data" / "generated" / "example_v1").exists()
    assert (project / "data" / "registry.json").read_bytes() == registry_bytes


def _training_recipe(project, name, per_direction, *, source=None, nested=()):
    generator = ({"name": "registered_subset", "source": source, "nested_against": list(nested)}
                 if source is not None else
                 {"name": "original_position", "source_split": "train", "seed": 271828,
                  "max_batches": 10, "pairs_per_combination": per_direction})
    return recipe(project, name=name, generator=generator,
                  splits={"train": {key: per_direction for key in
                                    ("ABB->ABB", "ABB->BAB", "BAB->ABB", "BAB->BAB")}},
                  deduplicate_against=["legacy_v1/test"])


@pytest.fixture
def training_pool(project):
    build_dataset(_training_recipe(project, "pool_v1", 4), project)
    return project


def test_balanced_subsets_preserve_source_rows_and_verify_nesting_and_overlap(training_pool):
    project = training_pool
    source = load_dataset("pool_v1/train", project)
    prior, previous_records = [], set()
    for name, quota in (("small_v1", 1), ("medium_v1", 2), ("large_v1", 4)):
        build_dataset(_training_recipe(project, name, quota, source=source.reference, nested=prior), project)
        saved = load_dataset(f"{name}/train", project)
        records = set(saved.pairs)
        assert previous_records < records
        assert records <= set(source.pairs)
        assert [pair.sample_id for pair in saved.pairs] == [
            pair.sample_id for pair in source.pairs if pair in records]
        for direction in ("ABB->ABB", "ABB->BAB", "BAB->ABB", "BAB->BAB"):
            matching = lambda rows: [pair for pair in rows
                                     if f"{pair.base.pattern}->{pair.source.pattern}" == direction]
            assert matching(saved.pairs) == matching(source.pairs)[:quota]
        selection = saved.manifest["deduplication"]["selection"]
        assert selection["source"] == {"reference": source.reference, "sha256": source.sha256,
                                       "manifest_sha256": source.manifest_sha256, "count": 16}
        assert selection["all_records_in_source"] is True
        assert set(selection["nested_against"]) == set(prior)
        for reference, evidence in selection["nested_against"].items():
            smaller = load_dataset(reference, project)
            assert evidence == {"sha256": smaller.sha256, "manifest_sha256": smaller.manifest_sha256,
                                "count": len(smaller.pairs), "missing_pairs": 0}
        verification = saved.manifest["deduplication"]["verification"]
        assert verification["status"] == "passed"
        assert verification["splits"]["train"]["unique_semantic_groups"] == quota * 4
        assert verification["splits"]["train"]["cross_pair_prompt_duplicates"] == 0
        assert verification["splits"]["train"]["cross_pair_semantic_group_duplicates"] == 0
        assert verification["external_overlap"]["legacy_v1/test"]["prompt_text_overlap"] == 0
        assert verification["external_overlap"]["legacy_v1/test"]["semantic_group_overlap"] == 0
        prior.append(saved.reference)
        previous_records = records
    assert saved.pairs == source.pairs


@pytest.mark.parametrize("quota, nested, diagnostic", [
    (5, (), "cannot satisfy subset quotas"),
    (1, ("pool_v1/train",), "records are missing"),
])
def test_invalid_subset_retains_registry_and_does_not_allocate(training_pool, quota, nested, diagnostic):
    project = training_pool
    path = _training_recipe(project, "invalid_v1", quota, source="pool_v1/train", nested=nested)
    registry_bytes = (project / "data" / "registry.json").read_bytes()
    with pytest.raises(ValueError, match=diagnostic):
        build_dataset(path, project)
    assert not (project / "data" / "generated" / "invalid_v1").exists()
    assert (project / "data" / "registry.json").read_bytes() == registry_bytes


def test_nested_recipes_take_all_sizes_and_balancing_from_their_specs():
    directory = PROJECT_ROOT / "configs" / "datasets"
    for name, count, nested in (("train_pool_v1", 5000, None), ("train_n200_v1", 200, []),
                                ("train_n1000_v1", 1000, ["train_n200_v1/train"]),
                                ("train_n5000_v1", 5000, ["train_n200_v1/train", "train_n1000_v1/train"])):
        spec = load_dataset_spec(directory / f"{name}.json")
        assert set(spec["splits"]["train"].values()) == {count // 4}
        assert len(spec["splits"]["train"]) == 4
        assert spec["deduplicate_against"] == ["legacy_v1/test", "val_indist_v1/validation"]
        if nested is not None:
            assert spec["generator"]["source"] == "train_pool_v1/train"
            assert spec["generator"]["nested_against"] == nested
