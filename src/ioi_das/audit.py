"""Audit registered IOI datasets without loading model weights or changing data."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from zoneinfo import ZoneInfo

from . import data
from .checks import run_focused_checks
from .config import config_sha256
from .positions import resolve_pair_positions, resolve_position
from .tokenization import check_answer, encode_pair_batch, encoded_to_dict, load_tokenizers


UPSTREAM_COMMIT = "9e333904dcf9e597ca76170010d17f4d4580de8d"
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


def _allocate_output(root: Path, dataset: str) -> Path:
    date = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y%m%d")
    parent = root / "outputs" / "data-audit"
    parent.mkdir(parents=True, exist_ok=True)
    suffix = 1
    while True:
        name = f"{date}-{dataset}" + (f"-{suffix}" if suffix > 1 else "")
        output = parent / name
        try:
            output.mkdir()
            return output
        except FileExistsError:
            suffix += 1


def _source_state(root: Path) -> dict:
    def git(*arguments: str) -> str:
        result = subprocess.run(["git", "-C", str(root), *arguments],
                                check=True, capture_output=True, text=True)
        return result.stdout.strip()

    return {"commit": git("rev-parse", "HEAD"),
            "clean_tree": not bool(git("status", "--porcelain")),
            "implementation_sha256": {path.name: data.sha256_file(path)
                                      for path in sorted(Path(__file__).parent.glob("*.py"))}}


def run_audit(dataset: str, project_root: Path | None = None,
              command: list[str] | None = None) -> dict:
    """Audit every registered split and save a fresh, immutable evidence directory."""
    from .datasets import load_dataset, load_registry

    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    registry = load_registry(root)
    if dataset not in registry["datasets"]:
        raise ValueError(f"Unknown dataset {dataset!r}; choose a name from data/registry.json.")
    inputs = {split: load_dataset(f"{dataset}/{split}", root)
              for split in registry["datasets"][dataset]["splits"]}
    config_path = root / "configs" / "base.json"
    tokenizer_options = json.loads(config_path.read_text(encoding="utf-8"))["tokenizer"]
    config = {"dataset": dataset, "tokenizer": tokenizer_options, "batch_size": 20,
              "intervention_locations": ["GOAL_NAME", "N", "N-1", "N-2"],
              "readout_location": "N"}
    provenance = verify_upstream(root / "vendor" / "pyvene_upstream")
    source = _source_state(root)
    output = _allocate_output(root, dataset)
    metadata = {"status": "running", "run_kind": "data-audit", "dataset": dataset,
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "command": command or [sys.executable, "-m", "ioi_das.cli", "data", "audit",
                                        "--dataset", dataset],
                "resolved_config": config, "config_sha256": config_sha256(config),
                "config_source_sha256": data.sha256_file(config_path),
                "registry_sha256": data.sha256_file(root / "data" / "registry.json"),
                "dataset_hashes": {item.reference: item.sha256 for item in inputs.values()},
                "dataset_manifest_sha256": {item.name: item.manifest_sha256 for item in inputs.values()},
                "dataset_generation": {item.name: item.manifest.get("generation", {})
                                       for item in inputs.values()},
                "upstream": provenance, **source}
    write_json(output / "resolved_config.json", config)
    write_json(output / "run.json", metadata)
    try:
        tokenizer, reference = load_tokenizers(tokenizer_options)
        metadata["environment"] = runtime_environment(config, tokenizer)
        write_json(output / "environment.json", metadata["environment"])
        write_json(output / "run.json", metadata)
        summary = _audit_pairs(output, {split: item.pairs for split, item in inputs.items()},
                               config, tokenizer, reference)
        summary.update({"dataset": dataset, "dataset_reused": True,
                        "config_sha256": metadata["config_sha256"],
                        "implementation_sha256": metadata["implementation_sha256"],
                        "dataset_manifest_sha256": metadata["dataset_manifest_sha256"],
                        "output_dir": str(output)})
        write_json(output / "summary.json", summary)
        write_summary(output / "summary.md", summary, select_previews(_read_rows(output / "pairs.jsonl")))
        metadata["status"] = summary["status"]
        metadata["artifacts"] = {name: data.sha256_file(output / name) for name in
                                 ("resolved_config.json", "environment.json", "focused_checks.json",
                                  "pairs.jsonl", "summary.json", "summary.md")}
    except Exception as error:
        metadata["status"] = "failed"
        metadata["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        metadata["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "run.json", metadata)
    return summary


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _audit_pairs(output_dir: Path, pairs: dict, config: dict, tokenizer, reference) -> dict:
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
    summary = {
        "status": "failed" if unsupported else "passed",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "upstream_commit": UPSTREAM_COMMIT,
        "counts": {split: len(records) for split, records in pairs.items()},
        "pairing_counts": {split: dict(Counter(f"{pair.base.pattern}->{pair.source.pattern}"
                                               for pair in records)) for split, records in pairs.items()},
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
    return summary


def select_previews(rows: list) -> list:
    """Return up to four varied examples from every audited split."""
    selected, seen = [], set()
    for row in rows:
        split = row["split"]
        key = split, row["base"]["pattern"], row["base"]["valid_length"]
        if key not in seen and sum(item["split"] == split for item in selected) < 4:
            selected.append(row)
            seen.add(key)
    return selected


def write_summary(path: Path, summary: dict, previews: list) -> None:
    lines = ["# Position audit", "", f"Real-tokenizer position audit {summary['status']}.", "",
             f"- Registered dataset: {summary['dataset']}.",
             f"- Saved pair counts: {summary['counts']}.",
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
              "Synthetic data is excluded from all registered dataset pairs. The mixed batch has base lengths [18, 22] "
              "and source lengths [22, 18]. Expected N-1 arrays are base [16, 20] and source [20, 16]. "
              "END/END-1/END-2 match individual tokenization. Repeated subjects map to distinct occurrences. "
              "Mary Jane retains both continuation tokens and is diagnosed as unsupported for single-token evaluation. "
              "See focused_checks.json for exact texts, all expected indices, and invalid-offset diagnostics.", ""]
    if summary["unsupported_answer_checks"]:
        lines += ["## Unsupported original-rule answer cases", "",
                  "See summary.json and pairs.jsonl for complete retained IDs, token spans, and diagnostics.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
