"""Lock a validation-only setting choice with complete contributing evidence."""

from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
from typing import Any

from .data import sha256_file


def choose_layer(values: list[dict[str, Any]]) -> tuple[int, dict[str, float]]:
    """Return the highest mean validation IIA layer, breaking ties by lowest index."""
    grouped = defaultdict(list)
    seeds = defaultdict(set)
    for value in values:
        layer, seed = value["layer"], value["seed"]
        if seed in seeds[layer]:
            raise ValueError(f"Duplicate seed {seed} for layer {layer}; provide one condition per layer and seed.")
        seeds[layer].add(seed)
        grouped[layer].append(Fraction(value["iia_correct"], value["iia_total"]))
    if not grouped or len({frozenset(group) for group in seeds.values()}) != 1:
        raise ValueError("Selection requires complete layers with matching seed sets.")
    means = {layer: sum(ratios) / len(ratios) for layer, ratios in grouped.items()}
    selected = min(means, key=lambda layer: (-means[layer], layer))
    return selected, {str(layer): float(value) for layer, value in sorted(means.items())}


def _contributions(output: Path, metadata: dict) -> list[dict]:
    values = []
    for condition in metadata["conditions"]:
        path = output / condition["path"]
        result_path = path / "result.json"
        if condition["status"] != "complete" or sha256_file(result_path) != condition["result_sha256"]:
            raise ValueError(f"Selection requires a complete, verified condition: {path}.")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        for name, digest in result["artifacts"].items():
            if sha256_file(path / name) != digest:
                raise ValueError(f"Condition artifact hash mismatch at {path / name}; restore its bytes.")
        metric = result["metrics"]["validation"]
        values.append({"layer": result["condition"]["layer"], "seed": result["seed"],
                       "iia": metric["iia"], "iia_correct": metric["iia_correct"],
                       "iia_total": metric["iia_total"], "condition_path": condition["path"],
                       "result_sha256": condition["result_sha256"],
                       "checkpoint_sha256": sha256_file(path / "alignment.pt")})
    return values


def lock_selection(output: Path, metadata: dict) -> dict:
    """Write or verify selection.json before allowing any locked-split evaluation."""
    settings = metadata["resolved_config"]["selection"]
    values = _contributions(output, metadata)
    selected, means = choose_layer(values)
    evidence = {"schema_version": 1, "selected_layer": selected,
                "metric": settings["metric"], "aggregate": settings["aggregate"],
                "tie_break": settings["tie_break"], "evaluate_after_lock": settings["evaluate_after_lock"],
                "values": values, "mean_validation_iia": means,
                "config_sha256": metadata["config_sha256"],
                "dataset_hashes": metadata["dataset_hashes"],
                "source_hashes": metadata["implementation_sha256"]}
    path = output / "selection.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if {key: value for key, value in saved.items() if key != "locked_at_utc"} != evidence:
            raise ValueError(f"Selection evidence differs at {path}; restore the immutable lock.")
        return saved
    evidence["locked_at_utc"] = datetime.now(timezone.utc).isoformat()
    # Exclusive creation prevents replacing an existing scientific choice.
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence
