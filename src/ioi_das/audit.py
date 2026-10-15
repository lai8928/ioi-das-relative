"""Save fixed original-rule samples and audit them without model weights."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import sys

from . import data
from .checks import run_focused_checks
from .positions import resolve_pair_positions, resolve_position
from .tokenization import check_answer, encode_pair_batch, encoded_to_dict, load_tokenizers


UPSTREAM_COMMIT = "9e333904dcf9e597ca76170010d17f4d4580de8d"
# This immutable manifest binds the generator used to create the registered data.
# Current diagnostic wording may change without changing its historical provenance.
LEGACY_MANIFEST_SHA256 = "9f47c403b39c12b93f3d27d4e26416e081172914f276f9bc7fdcd1f6eb44653c"
UPSTREAM_PATHS = {
    "LICENSE", "pyproject.toml", "tutorials/advanced_tutorials/IOI_with_DAS.ipynb",
    "tutorials/advanced_tutorials/tutorial_ioi_utils.py",
    *(f"tutorials/advanced_tutorials/tutorial_data/{name}.json"
      for name in ("names", "objects", "places", "templates")),
}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def verify_upstream(upstream_dir: Path) -> dict:
    provenance = json.loads((upstream_dir / "provenance.json").read_text(encoding="utf-8"))
    if provenance["commit"] != UPSTREAM_COMMIT or {f["path"] for f in provenance["files"]} != UPSTREAM_PATHS:
        raise ValueError("Upstream provenance does not contain the eight required files at the pinned commit.")
    for entry in provenance["files"]:
        path = upstream_dir / entry["path"]
        if data.sha256_file(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Upstream original changed: {path}; restore exact pinned bytes before auditing.")
    return provenance


def validate_counts(pairs: dict) -> dict:
    expected = {
        "train": {"ABB->ABB": 50, "ABB->BAB": 50, "BAB->ABB": 50, "BAB->BAB": 50},
        "test": {"ABB->BAB": 50, "BAB->ABB": 50},
    }
    actual = {}
    for split, records in pairs.items():
        actual[split] = dict(Counter(f"{p.base.pattern}->{p.source.pattern}" for p in records))
        if actual[split] != expected[split] or any(p.split != split for p in records):
            raise ValueError(f"Saved {split} samples violate original POSITION counts or split labels.")
        if [p.sample_id for p in records] != [f"{split}-{i:04d}" for i in range(len(records))]:
            raise ValueError(f"Saved {split} sample IDs/order differ from the stable original-rule sequence.")
    return actual


def ensure_saved_pairs(config: dict, provenance: dict) -> tuple[dict, dict, bool]:
    directory = config["generated_dir"]
    paths = {split: directory / f"{split}.jsonl" for split in ("train", "test")}
    manifest_path = directory / "manifest.json"
    spec = {
        "seed": config["seed"],
        "generator_revision": data.GENERATOR_REVISION,
        "generator_sha256": data.sha256_file(Path(data.__file__)),
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_sha256": {entry["path"]: entry["sha256"] for entry in provenance["files"]},
        "target_variable": "position",
    }
    if any(path.exists() for path in (*paths.values(), manifest_path)):
        if not all(path.is_file() for path in (*paths.values(), manifest_path)):
            raise ValueError(f"Incomplete saved dataset at {directory}; preserve it and select "
                             "a separate generated_dir, or restore its missing files.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if data.sha256_file(manifest_path) == LEGACY_MANIFEST_SHA256:
            spec["generator_sha256"] = manifest["generation"]["generator_sha256"]
        if manifest["generation"] != spec:
            raise ValueError(f"Saved dataset generation metadata differs at {manifest_path}; "
                             "restore the original config/generator or select a separate generated_dir.")
        for split, path in paths.items():
            if data.sha256_file(path) != manifest["files"][split]["sha256"]:
                raise ValueError(f"Saved dataset hash mismatch: {path}; restore the saved file before reuse.")
        pairs = {split: data.load_pairs(path) for split, path in paths.items()}
        validate_counts(pairs)
        return pairs, manifest, True
    pairs = data.generate_pairs(config["upstream_dir"], config["seed"])
    counts = validate_counts(pairs)
    for split, path in paths.items():
        data.write_pairs(path, pairs[split])
    manifest = {
        "schema_version": 1,
        "generation": spec,
        "tokenizer_at_generation": config["tokenizer"],
        "pairing_counts": counts,
        "files": {split: {"path": f"{split}.jsonl", "count": len(pairs[split]),
                          "sha256": data.sha256_file(path)} for split, path in paths.items()},
        "policies": {
            "symbol_order": "first occurrence, replacing upstream unordered set iteration",
            "resource_split": "original first/second halves; templates first two/rest",
            "source_sampling": "resample each base using the same A/B names, template, object, place",
            "historical_samples": False,
            "name_span": "construction-time half-open character spans for formatted occurrences",
            "reuse": "verify manifest and hashes; never regenerate on an audit rerun",
        },
    }
    write_json(manifest_path, manifest)
    return pairs, manifest, False


def runtime_environment(config: dict, tokenizer) -> dict:
    from transformers.utils.hub import cached_file

    packages = {}
    for name in ("torch", "transformers", "tokenizers", "pyvene", "numpy", "pytest", "packaging"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    assets = {}
    for filename in ("tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt"):
        path = cached_file(config["tokenizer"]["name"], filename,
                           revision=config["tokenizer"]["revision"], local_files_only=True)
        if path:
            assets[filename] = {"path": str(Path(path).absolute()),
                                "sha256": data.sha256_file(Path(path))}
    return {
        "executable": sys.executable,
        "python": platform.python_version(),
        "packages": packages,
        "tokenizer": config["tokenizer"],
        "tokenizer_class": type(tokenizer).__name__,
        "reference_tokenizer_class": "GPT2Tokenizer",
        "tokenizer_assets": assets,
        "backend_sha256": hashlib.sha256(tokenizer.backend_tokenizer.to_str().encode()).hexdigest(),
        "model_weights_loaded": False,
        "gpu_required": False,
    }


def run_audit(config: dict) -> dict:
    output_dir = config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance = verify_upstream(config["upstream_dir"])
    tokenizer, reference = load_tokenizers(config["tokenizer"])
    environment = runtime_environment(config, tokenizer)
    write_json(output_dir / "environment.json", environment)
    pairs, manifest, reused = ensure_saved_pairs(config, provenance)
    focused = run_focused_checks(tokenizer, reference)
    write_json(output_dir / "focused_checks.json", focused)
    length_counts = {split: {side: Counter() for side in ("base", "source")} for split in pairs}
    unsupported, preview_candidates = [], []
    answer_statuses = Counter()
    batch_comparisons = 0
    batched_sides = 0
    temporary = output_dir / "pairs.jsonl.tmp"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for split, records in pairs.items():
            for start in range(0, len(records), config["batch_size"]):
                batch = encode_pair_batch(records[start:start + config["batch_size"]], tokenizer, reference)
                batched_sides += 2
                locations = {location: resolve_pair_positions(batch, location)
                             for location in config["intervention_locations"]}
                readouts = resolve_pair_positions(batch, config["readout_location"])
                for i, pair in enumerate(batch.pairs):
                    row = {"sample_id": pair.sample_id, "split": split,
                           "target_variable": pair.target_variable,
                           "counterfactual_answer": pair.counterfactual_answer,
                           "counterfactual_alternative": pair.counterfactual_alternative,
                           "intervention_locations": config["intervention_locations"],
                           "readout_location": "N", "batch_start": start}
                    checks = {}
                    for side in ("base", "source"):
                        side_batch = getattr(batch, side)
                        encoded = side_batch.examples[i]
                        indices = {location: resolve_position(encoded, location)
                                   for location in config["intervention_locations"]}
                        for location, index in indices.items():
                            if index != locations[location][side][i]:
                                raise AssertionError(f"{pair.sample_id}/{side}/{location}: batch/individual mismatch.")
                            batch_comparisons += 1
                        content = asdict(encoded.prompt)
                        content.update(encoded_to_dict(encoded))
                        content.update({"positions": indices,
                                        "padded_input_ids": side_batch.input_ids[i],
                                        "batch_attention_mask": side_batch.attention_mask[i],
                                        "batch_width": len(side_batch.input_ids[i])})
                        row[side] = content
                        length_counts[split][side][encoded.valid_length] += 1
                        for role, answer in (("factual", encoded.prompt.io_name),
                                             ("subject_alternative", encoded.prompt.subject_name)):
                            checks[f"{side}_{role}"] = asdict(check_answer(tokenizer, reference, encoded, answer))
                    for role, answer in (("counterfactual", pair.counterfactual_answer),
                                         ("counterfactual_alternative", pair.counterfactual_alternative)):
                        checks[role] = asdict(check_answer(tokenizer, reference, batch.base.examples[i], answer))
                    for label, check in checks.items():
                        answer_statuses[check["status"]] += 1
                        if check["status"] != "supported_single_token":
                            unsupported.append({"sample_id": pair.sample_id, "answer_check": label, **check})
                    row["answer_checks"] = checks
                    row["base_readout_index"] = readouts["base"][i]
                    if row["base_readout_index"] != row["base"]["valid_length"] - 1:
                        raise AssertionError(f"{pair.sample_id}: base readout is not its final valid token.")
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    preview_candidates.append(row)
    temporary.replace(output_dir / "pairs.jsonl")
    previews = select_previews(preview_candidates)
    summary = {
        "status": "passed",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "upstream_commit": UPSTREAM_COMMIT,
        "config_sha256": data.sha256_file(config["config_path"]),
        "implementation_sha256": {path.name: data.sha256_file(path)
                                  for path in sorted(Path(__file__).parent.glob("*.py"))},
        "dataset_manifest_sha256": data.sha256_file(config["generated_dir"] / "manifest.json"),
        "dataset_reused": reused,
        "counts": {split: len(records) for split, records in pairs.items()},
        "pairing_counts": manifest["pairing_counts"],
        "valid_length_counts": {split: {side: dict(sorted(counts.items())) for side, counts in sides.items()}
                                for split, sides in length_counts.items()},
        "unequal_length_original_pairs": sum(p["base"]["valid_length"] != p["source"]["valid_length"]
                                             for p in preview_candidates),
        "tokenizer": config["tokenizer"],
        "fast_reference_comparisons": {"inputs": 2 * len(preview_candidates),
                                       "continuations": sum(answer_statuses.values()),
                                       "batched_sides": batched_sides},
        "batch_individual_position_comparisons": batch_comparisons,
        "answer_status_counts": dict(answer_statuses),
        "unsupported_answer_checks": unsupported,
        "focused_checks": focused["status"],
        "policies": {"name_scalar": "last token of full factual occurrence span",
                     "readout": "base N = sum(base attention_mask) - 1",
                     "padding": "independent right padding, no truncation or appended answers"},
        "artifacts": {filename: data.sha256_file(output_dir / filename)
                      for filename in ("pairs.jsonl", "environment.json", "focused_checks.json")},
        "model_weights_loaded": False,
        "das_training_started": False,
    }
    write_json(output_dir / "summary.json", summary)
    write_summary(output_dir / "summary.md", summary, previews)
    return summary


def select_previews(rows: list) -> list:
    """Show both base patterns per split before filling with varied lengths."""
    selected, seen = [], set()
    for split in ("train", "test"):
        for pattern in ("ABB", "BAB"):
            row = next(row for row in rows if row["split"] == split and row["base"]["pattern"] == pattern)
            selected.append(row)
            seen.add((split, pattern, row["base"]["valid_length"]))
        for row in rows:
            key = row["split"], row["base"]["pattern"], row["base"]["valid_length"]
            if row["split"] == split and key not in seen and sum(r["split"] == split for r in selected) < 4:
                selected.append(row)
                seen.add(key)
    return sorted(selected, key=lambda row: (row["split"] == "test", row["sample_id"]))


def write_summary(path: Path, summary: dict, previews: list) -> None:
    lines = ["# Position audit", "", "Full real-tokenizer position audit passed.", "",
             f"- Original-rule samples: {summary['counts']['train']} training / {summary['counts']['test']} test pairs.",
             f"- Saved dataset reused: {summary['dataset_reused']}.",
             f"- Fast/reference GPT-2 comparisons: {summary['fast_reference_comparisons']}.",
             f"- Batch/individual position comparisons: {summary['batch_individual_position_comparisons']}.",
             f"- Unsupported answer checks: {len(summary['unsupported_answer_checks'])} (examples retained).",
             f"- Unequal-length original pairs: {summary['unequal_length_original_pairs']}.",
             "- Focused real-tokenizer checks passed, including synthetic unequal-length 18/22-token inputs.",
             "- No model weights loaded and no DAS training started.", "",
             "## Original-rule prompt lengths", ""]
    for split, sides in summary["valid_length_counts"].items():
        lines.append(f"- {split}: {sides}")
    lines += ["", "## Original-rule example subset", "",
              "Indices are zero-based. GOAL_NAME is each input's factual IO; name anchors use the last span token.", "",
              "| ID | Base/source patterns | Lengths | GOAL_NAME base/source | N base/source | N-1 base/source | N-2 base/source | Base IO / CF |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in previews:
        b, s = row["base"], row["source"]
        values = [f"{b['positions'][key]}/{s['positions'][key]}"
                  for key in ("GOAL_NAME", "N", "N-1", "N-2")]
        lines.append(f"| {row['sample_id']} | {b['pattern']}/{s['pattern']} | {b['valid_length']}/{s['valid_length']} | "
                     + " | ".join(values) + f" | {b['io_name']} / {row['counterfactual_answer']} |")
    for row in previews:
        lines += ["", f"### {row['sample_id']}", "", f"Base: {row['base']['text']}", "",
                  f"Source: {row['source']['text']}"]
    lines += ["", "## Synthetic focused evidence", "",
              "Synthetic data is excluded from the 200/100 sampled pairs. The mixed batch has base lengths [18, 22] "
              "and source lengths [22, 18]. Expected N-1 arrays are base [16, 20] and source [20, 16]. "
              "END/END-1/END-2 match individual tokenization. Repeated subjects map to distinct occurrences. "
              "Mary Jane retains both continuation tokens and is diagnosed as unsupported for single-token evaluation. "
              "See focused_checks.json for exact texts, all expected indices, and invalid-offset diagnostics.", ""]
    if summary["unsupported_answer_checks"]:
        lines += ["## Unsupported original-rule answer cases", "",
                  "See summary.json and pairs.jsonl for complete retained IDs, token spans, and diagnostics.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
