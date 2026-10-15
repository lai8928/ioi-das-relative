"""Resolve immutable registered splits and build bounded, deduplicated datasets."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import json
from math import comb
from pathlib import Path
import re
from typing import Iterable

import jsonschema

from . import data
from .data import PairRecord, PromptRecord, generate_pairs, load_pairs, sha256_file, write_pairs


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATTERN = re.compile(r"([a-z][a-z0-9_-]*)/(train|validation|test)")


@dataclass(frozen=True)
class DatasetSplit:
    """A verified registered split with its saved manifest and exact hashes."""

    reference: str
    name: str
    split: str
    directory: Path
    path: Path
    manifest_path: Path
    pairs: list[PairRecord]
    manifest: dict
    sha256: str
    manifest_sha256: str


def load_registry(project_root: Path = PROJECT_ROOT) -> dict:
    """Return the machine-readable dataset registry from the project root."""
    path = Path(project_root) / "data" / "registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1 or not isinstance(registry.get("datasets"), dict):
        raise ValueError(f"{path}: expected schema_version 1 and a datasets object.")
    return registry


def _contained_path(directory: Path, relative: str) -> Path:
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError(f"Dataset path {relative!r} escapes {directory}; use a relative path inside it.")
    return path


def load_dataset(reference: str, project_root: Path = PROJECT_ROOT) -> DatasetSplit:
    """Load one registered split after verifying file/manifest hashes and counts."""
    match = REFERENCE_PATTERN.fullmatch(reference)
    if match is None:
        raise ValueError(f"Invalid dataset reference {reference!r}; use <dataset>/<train|validation|test>.")
    name, split = match.groups()
    registry = load_registry(project_root)
    try:
        entry = registry["datasets"][name]
        saved = entry["splits"][split]
    except KeyError as error:
        raise ValueError(f"Unregistered dataset split {reference!r}; add it to data/registry.json.") from error
    directory = _contained_path(Path(project_root), entry["directory"])
    path = _contained_path(directory, saved["file"])
    manifest_path = directory / "manifest.json"
    manifest_hash, split_hash = sha256_file(manifest_path), sha256_file(path)
    if manifest_hash != entry["manifest_sha256"]:
        raise ValueError(f"Manifest SHA-256 mismatch for {reference}: {manifest_path}; restore its registered bytes.")
    if split_hash != saved["sha256"]:
        raise ValueError(f"Split SHA-256 mismatch for {reference}: {path}; restore its registered bytes.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_split = manifest.get("files", {}).get(split, {})
    if (manifest_split.get("sha256"), manifest_split.get("count")) != (split_hash, saved["count"]):
        raise ValueError(f"Manifest split metadata disagrees with registry for {reference}; restore the registered metadata.")
    pairs = load_pairs(path)
    if len(pairs) != saved["count"] or any(pair.split != split for pair in pairs):
        raise ValueError(f"Split count/labels mismatch for {reference}: expected {saved['count']} {split} pairs, got {len(pairs)}.")
    return DatasetSplit(reference, name, split, directory, path, manifest_path, pairs,
                        manifest, split_hash, manifest_hash)


def semantic_group(prompt: PromptRecord) -> tuple:
    """Return a generation context shared by all direction and pattern variants."""
    return prompt.template, tuple(sorted(set(prompt.names))), prompt.obj, prompt.place


def split_inventory(pairs: Iterable[PairRecord]) -> tuple[set, set]:
    """Return prompt texts and semantic groups represented by a sequence of pairs."""
    prompts = [prompt for pair in pairs for prompt in (pair.base, pair.source)]
    return {prompt.text for prompt in prompts}, {semantic_group(prompt) for prompt in prompts}


def load_dataset_spec(config_path: Path) -> dict:
    """Load a dataset recipe after validating its separate JSON Schema."""
    path = Path(config_path)
    spec = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((PROJECT_ROOT / "configs" / "datasets" / "schema.json").read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(spec)
    except jsonschema.ValidationError as error:
        raise ValueError(f"{path}: invalid dataset recipe: {error.message}") from error
    if spec["name"] != path.stem:
        raise ValueError(f"Dataset name {spec['name']!r} must match recipe file stem {path.stem!r}.")
    return spec


def _dedup_sources(references: list[str], project_root: Path) -> tuple[list, dict]:
    registry = load_registry(project_root)
    pairs, hashes = [], {}
    for reference in references:
        if "/" in reference:
            split_references = [reference]
        else:
            if reference not in registry["datasets"]:
                raise ValueError(f"Unknown deduplication dataset {reference!r}; register it before building.")
            split_references = [f"{reference}/{split}" for split in registry["datasets"][reference]["splits"]]
        for split_reference in split_references:
            dataset = load_dataset(split_reference, project_root)
            pairs.extend(dataset.pairs)
            hashes[split_reference] = {"sha256": dataset.sha256, "manifest_sha256": dataset.manifest_sha256}
    return pairs, hashes


def _sample_splits(spec: dict, upstream_dir: Path, excluded: list[PairRecord]) -> tuple[dict, dict]:
    blocked_texts, blocked_groups = split_inventory(excluded)
    selected = {split: [] for split in spec["splits"]}
    counts = {split: Counter() for split in selected}
    rejected = Counter()
    candidate_seeds = []
    generator = spec["generator"]
    capacity = generation_capacity(upstream_dir, generator["source_split"], excluded)
    capacity["requested_pairs"] = sum(sum(quotas.values()) for quotas in spec["splits"].values())
    if capacity["requested_pairs"] > capacity["available_semantic_groups"]:
        raise ValueError(f"Requested {capacity['requested_pairs']} pairs exceeds the available "
                         f"semantic-group capacity {capacity['available_semantic_groups']}; "
                         "preserve deduplication and reduce the dataset size.")
    for offset in range(generator["max_batches"]):
        candidate_seed = generator["seed"] + offset
        candidate_seeds.append(candidate_seed)
        candidates = generate_pairs(
            upstream_dir, candidate_seed,
            pairs_per_combination=generator.get("pairs_per_combination", 50))[generator["source_split"]]
        for pair in candidates:
            direction = f"{pair.base.pattern}->{pair.source.pattern}"
            split = next((key for key, quotas in spec["splits"].items()
                          if counts[key][direction] < quotas.get(direction, 0)), None)
            if split is None:
                continue
            texts, groups = split_inventory([pair])
            if texts & blocked_texts:
                rejected["prompt_overlap"] += 1
                continue
            if groups & blocked_groups:
                rejected["semantic_group_overlap"] += 1
                continue
            selected[split].append(replace(pair, sample_id=f"{split}-{len(selected[split]):04d}", split=split))
            counts[split][direction] += 1
            blocked_texts.update(texts)
            blocked_groups.update(groups)
        if all(dict(counts[split]) == quotas for split, quotas in spec["splits"].items()):
            return selected, {"candidate_seeds": candidate_seeds, "batches_used": offset + 1,
                              "rejections": dict(rejected), "pairing_counts": {s: dict(c) for s, c in counts.items()},
                              "capacity": capacity}
    accepted = {split: len(pairs) for split, pairs in selected.items()}
    raise ValueError(f"Dataset generation exhausted max_batches={generator['max_batches']}; "
                     f"accepted={accepted}, pairing_counts={counts}, rejections={dict(rejected)}. "
                     "Preserve deduplication rules; choose an explicit new recipe bound.")


def generation_capacity(upstream_dir: Path, source_split: str,
                        excluded: Iterable[PairRecord] = ()) -> dict:
    """Count distinct semantic contexts in the original resource half before sampling."""
    if source_split not in {"train", "test"}:
        raise ValueError("Capacity requires source_split 'train' or 'test'.")
    resource_dir = Path(upstream_dir) / "tutorials/advanced_tutorials/tutorial_data"
    resources = {key: json.loads((resource_dir / f"{key}.json").read_text(encoding="utf-8"))
                 for key in ("names", "objects", "places", "templates")}
    pools = {}
    for key in ("names", "objects", "places"):
        midpoint = len(resources[key]) // 2
        pools[key] = set(resources[key][:midpoint] if source_split == "train" else resources[key][midpoint:])
    templates = set(resources["templates"][:2] if source_split == "train" else resources["templates"][2:])
    _, blocked_groups = split_inventory(excluded)
    excluded_count = sum(template in templates and len(names) == 2 and set(names) <= pools["names"]
                         and obj in pools["objects"] and place in pools["places"]
                         for template, names, obj, place in blocked_groups)
    capacity = len(templates) * comb(len(pools["names"]), 2) * len(pools["objects"]) * len(pools["places"])
    return {"source_split": source_split,
            "resource_counts": {**{key: len(values) for key, values in pools.items()}, "templates": len(templates)},
            "semantic_group_capacity": capacity, "excluded_semantic_groups": excluded_count,
            "available_semantic_groups": capacity - excluded_count}


def _subset_splits(spec: dict, project_root: Path) -> tuple[dict, dict]:
    generator = spec["generator"]
    source = load_dataset(generator["source"], project_root)
    if set(spec["splits"]) != {source.split}:
        raise ValueError("Subset recipes must preserve the registered source split.")
    quotas = spec["splits"][source.split]
    counts, records = Counter(), []
    for pair in source.pairs:
        direction = f"{pair.base.pattern}->{pair.source.pattern}"
        if counts[direction] < quotas.get(direction, 0):
            records.append(pair)
            counts[direction] += 1
    if dict(counts) != quotas:
        raise ValueError(f"Registered source {source.reference} cannot satisfy subset quotas {quotas}; "
                         f"accepted pairing_counts={dict(counts)}.")
    selected = set(records)
    nested = {}
    for reference in generator["nested_against"]:
        smaller = load_dataset(reference, project_root)
        missing = set(smaller.pairs) - selected
        if missing:
            raise ValueError(f"Subset {spec['name']} does not contain all {len(smaller.pairs)} pairs "
                             f"from {reference}; {len(missing)} records are missing.")
        nested[reference] = {"sha256": smaller.sha256, "manifest_sha256": smaller.manifest_sha256,
                             "count": len(smaller.pairs), "missing_pairs": 0}
    return {source.split: records}, {
        "pairing_counts": {source.split: dict(counts)},
        "selection": {"strategy": "first pairs per pairing in saved source order; preserve sample IDs",
                      "source": {"reference": source.reference, "sha256": source.sha256,
                                 "manifest_sha256": source.manifest_sha256, "count": len(source.pairs)},
                      "nested_against": nested, "all_records_in_source": True}}


def _verify_splits(pairs: dict[str, list[PairRecord]], spec: dict,
                   project_root: Path) -> dict:
    """Verify accepted rows independently before publishing their dataset or registry entry."""
    seen_texts, seen_groups, identifiers = set(), set(), set()
    verified = {}
    for split, records in pairs.items():
        counts = Counter(f"{pair.base.pattern}->{pair.source.pattern}" for pair in records)
        if dict(counts) != spec["splits"][split]:
            raise ValueError(f"Built pairing counts disagree with recipe for {split}.")
        for pair in records:
            texts, groups = split_inventory([pair])
            if pair.sample_id in identifiers or texts & seen_texts or groups & seen_groups:
                raise ValueError("Built dataset repeats sample IDs, prompt text, or semantic groups across pairs.")
            identifiers.add(pair.sample_id)
            seen_texts.update(texts)
            seen_groups.update(groups)
        texts, groups = split_inventory(records)
        verified[split] = {"pair_count": len(records), "unique_sample_ids": len({p.sample_id for p in records}),
                           "unique_prompt_texts": len(texts), "unique_semantic_groups": len(groups),
                           "cross_pair_prompt_duplicates": 0, "cross_pair_semantic_group_duplicates": 0}
    _, sources = _dedup_sources(spec["deduplicate_against"], project_root)
    overlaps = {}
    for reference, hashes in sources.items():
        dataset = load_dataset(reference, project_root)
        texts, groups = split_inventory(dataset.pairs)
        text_overlap, group_overlap = len(texts & seen_texts), len(groups & seen_groups)
        if text_overlap or group_overlap:
            raise ValueError(f"Built dataset overlaps {reference}: {text_overlap} prompt texts, "
                             f"{group_overlap} semantic groups.")
        overlaps[reference] = {**hashes, "prompt_text_overlap": text_overlap,
                               "semantic_group_overlap": group_overlap}
    return {"status": "passed", "splits": verified, "external_overlap": overlaps}


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def build_dataset(config_path: Path, project_root: Path | None = None) -> dict:
    """Build a new named dataset once and append its hashes to the registry."""
    project_root = Path(project_root) if project_root is not None else Path(config_path).resolve().parents[2]
    spec = load_dataset_spec(config_path)
    registry = load_registry(project_root)
    directory = project_root / "data" / "generated" / spec["name"]
    if spec["name"] in registry["datasets"] or directory.exists():
        raise ValueError(f"Dataset {spec['name']!r} already exists or is registered; never overwrite it, choose a new versioned name.")
    excluded, source_hashes = _dedup_sources(spec["deduplicate_against"], project_root)
    upstream_dir = project_root / "vendor" / "pyvene_upstream"
    from .audit import verify_upstream

    provenance = verify_upstream(upstream_dir)
    if spec["generator"]["name"] == "registered_subset":
        pairs, evidence = _subset_splits(spec, project_root)
    else:
        pairs, evidence = _sample_splits(spec, upstream_dir, excluded)
    evidence["verification"] = _verify_splits(pairs, spec, project_root)
    directory.mkdir(parents=True, exist_ok=False)
    files = {}
    for split, records in pairs.items():
        path = directory / f"{split}.jsonl"
        write_pairs(path, records)
        files[split] = {"path": path.name, "count": len(records), "sha256": sha256_file(path)}
    manifest = {"schema_version": 1, "dataset": spec["name"], "files": files,
                "generation": {**spec["generator"], "generator_revision": data.GENERATOR_REVISION,
                               "generator_sha256": sha256_file(Path(data.__file__)),
                               "builder_sha256": sha256_file(Path(__file__)),
                               "specification_sha256": sha256_file(Path(config_path)),
                               "upstream_commit": provenance["commit"],
                               "upstream_sha256": {row["path"]: row["sha256"] for row in provenance["files"]}},
                "deduplication": {"sources": source_hashes, "policy": "prompt text and template + unordered names + object + place",
                                  **evidence}, "purpose": spec["purpose"]}
    manifest_path = directory / "manifest.json"
    _write_json(manifest_path, manifest)
    entry = {"directory": directory.relative_to(project_root).as_posix(),
             "splits": {split: {"file": row["path"], "count": row["count"], "sha256": row["sha256"]}
                        for split, row in files.items()},
             "manifest_sha256": sha256_file(manifest_path), "purpose": spec["purpose"]}
    registry["datasets"][spec["name"]] = entry
    registry_path = project_root / "data" / "registry.json"
    temporary = registry_path.with_suffix(".json.tmp")
    _write_json(temporary, registry)
    temporary.replace(registry_path)
    return {"dataset": spec["name"], **entry, "deduplication": evidence}
