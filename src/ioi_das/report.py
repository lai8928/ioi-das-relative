"""Regenerate experiment tables and figures from saved JSON files only."""

from collections import Counter
import csv
from html import escape
import io
import json
from pathlib import Path
from typing import Any


SPLITS = ("initial_train", "train", "test")
METRICS = ("iia", "iia_correct", "iia_total", "factual_accuracy", "factual_correct",
           "factual_total", "mean_counterfactual_loss", "mean_factual_loss",
           "mean_target_logit")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Saved metadata must be a JSON object: {path}.")
    return value


def _condition_path(experiment_dir: Path, value: str) -> Path:
    path = (experiment_dir / value).resolve()
    if not path.is_relative_to(experiment_dir / "conditions"):
        raise ValueError(f"Condition path must be inside {experiment_dir / 'conditions'}: {value!r}.")
    return path


def _saved_conditions(experiment_dir: Path, run: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    known = set()
    for condition in run.get("conditions", []):
        path = _condition_path(experiment_dir, condition["path"])
        if path in known:
            raise ValueError(f"Duplicate condition path in run.json: {condition['path']!r}.")
        known.add(path)
        records.append({**condition, "directory": path})
    for result_path in sorted((experiment_dir / "conditions").glob("**/result.json")):
        if result_path.parent not in known:
            records.append({"directory": result_path.parent, "status": "unknown", "axes": {}})
    return records


def _condition_row(record: dict[str, Any], experiment_dir: Path, run_kind: str) -> dict[str, Any]:
    path = record["directory"]
    result_path = path / "result.json"
    result = _read_json(result_path) if result_path.is_file() else {}
    condition = result.get("condition", {})
    axes = record.get("axes", {})
    configured = record.get("resolved_config", {})
    intervention = configured.get("intervention", {})
    status = result.get("status", record.get("status", "pending"))
    if not result and status == "complete":
        status = "missing_result"
    row = {"condition": path.relative_to(experiment_dir).as_posix(), "status": status,
           "run_kind": result.get("run_kind", run_kind),
           "layer": condition.get("layer", axes.get("intervention.layer", intervention.get("layer", ""))),
           "component": condition.get("component", axes.get("intervention.component", intervention.get("component", ""))),
           "location": condition.get("intervention_location", axes.get("intervention.location", intervention.get("location", ""))),
           "rank": condition.get("rank", axes.get("intervention.rank", intervention.get("rank", ""))),
           "seed": result.get("seed", axes.get("seed", configured.get("seed", ""))),
           "error": result.get("error", record.get("error", ""))}
    failure_path = path / "failure.json"
    if failure_path.is_file():
        row["error"] = _read_json(failure_path).get("error", row["error"])
    metrics = result.get("metrics", {})
    for split in SPLITS:
        for metric in METRICS:
            row[f"{split}_{metric}"] = metrics.get(split, {}).get(metric, "")
    return row


def _csv_text(rows: list[dict[str, Any]]) -> str:
    fields = ("condition", "status", "run_kind", "layer", "component", "location", "rank", "seed",
              *(f"{split}_{metric}" for split in SPLITS for metric in METRICS), "error")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _markdown_value(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _iia_text(row: dict[str, Any], split: str) -> str:
    ratio = row[f"{split}_iia"]
    if ratio == "":
        return "—"
    correct, total = row[f"{split}_iia_correct"], row[f"{split}_iia_total"]
    return f"{correct}/{total} = {ratio}"


def _summary_text(run: dict[str, Any], rows: list[dict[str, Any]], descriptive_test: bool) -> str:
    kind = run.get("run_kind", "unknown")
    config = run.get("resolved_config", {})
    label = f"{config.get('task', 'experiment')} / {config.get('name', 'saved run')}"
    counts = Counter(row["status"] for row in rows)
    lines = [f"# {label}", "", f"Run kind: **{kind}**; run status: **{run.get('status', 'unknown')}**.",
             "", f"Config SHA-256: `{run.get('config_sha256', 'unrecorded')}`.", "",
             "Conditions: " + (", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
                               or "none") + ".", ""]
    if kind == "smoke":
        lines.extend(["This is a smoke run for execution checks; it is not a full experimental result.", ""])
    if descriptive_test:
        lines.extend(["The legacy test set is a descriptive benchmark, previously inspected in earlier runs.",
                      "It is not an untouched held-out test.", ""])
    test_label = "Test IIA (descriptive)" if descriptive_test else "Test IIA"
    lines.extend([f"| Condition | Status | Initial train IIA | Train IIA | {test_label} |",
                  "| --- | --- | --- | --- | --- |"])
    for row in rows:
        cells = [row["condition"], row["status"], *(_iia_text(row, split) for split in SPLITS)]
        lines.append("| " + " | ".join(_markdown_value(cell) for cell in cells) + " |")
    lines.extend(["", "Full-precision metrics and exact counts are saved in `conditions.csv`.",
                  "Missing metrics are shown as —; failed and pending conditions remain in the table.", "",
                  "![Saved IIA by condition](figures/iia.svg)", ""])
    errors = [row for row in rows if row["error"]]
    if errors:
        lines.extend(["Condition errors:", ""])
        lines.extend(f"- `{_markdown_value(row['condition'])}`: {_markdown_value(row['error'])}" for row in errors)
        lines.append("")
    return "\n".join(lines)


def _figure_text(rows: list[dict[str, Any]], run_kind: str, descriptive_test: bool) -> str:
    width, left, chart_width = 1100, 480, 500
    height = 120 + max(1, len(rows)) * 84
    colors = ("#94a3b8", "#2563eb", "#059669")
    labels = ("Initial train", "Train", "Test (descriptive)" if descriptive_test else "Test")
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">',
             f'<title id="title">Saved IIA by condition ({escape(run_kind)} run)</title>',
             '<desc id="description">IIA ratios range from zero to one. Missing results have no bars.</desc>',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g font-family="sans-serif" font-size="12" fill="#0f172a">',
             f'<text x="20" y="26" font-size="18">Saved IIA by condition — {escape(run_kind)} run</text>']
    for index, (color, label) in enumerate(zip(colors, labels)):
        x = 20 + index * 220
        parts.extend([f'<rect x="{x}" y="42" width="12" height="12" fill="{color}"/>',
                      f'<text x="{x + 18}" y="53">{escape(label)}</text>'])
    for tick in range(6):
        x = left + chart_width * tick / 5
        parts.extend([f'<line x1="{x:g}" y1="78" x2="{x:g}" y2="{height - 18}" stroke="#e2e8f0"/>',
                      f'<text x="{x:g}" y="74" text-anchor="middle">{tick / 5:g}</text>'])
    for index, row in enumerate(rows):
        y = 104 + index * 84
        parts.extend([f'<text x="20" y="{y + 8}">{escape(str(row["condition"]))}</text>',
                      f'<text x="20" y="{y + 26}" fill="#64748b">{escape(str(row["status"]))}</text>'])
        for offset, (split, color) in enumerate(zip(SPLITS, colors)):
            value = row[f"{split}_iia"]
            if value != "":
                bar_width = float(value) * chart_width
                bar_y = y - 10 + offset * 20
                parts.extend([f'<rect x="{left}" y="{bar_y}" width="{bar_width:.12g}" height="14" fill="{color}"/>',
                              f'<text x="{left + bar_width + 5:.12g}" y="{bar_y + 12}">{escape(str(value))}</text>'])
    parts.extend(["</g>", "</svg>", ""])
    return "\n".join(parts)


def generate_report(experiment_dir: Path) -> dict[str, Any]:
    """Write deterministic tables, a summary, and an SVG from saved run metadata."""
    experiment_dir = Path(experiment_dir).expanduser().resolve()
    run = _read_json(experiment_dir / "run.json")
    run_kind = run.get("run_kind", "unknown")
    rows = [_condition_row(record, experiment_dir, run_kind)
            for record in _saved_conditions(experiment_dir, run)]
    test = run.get("resolved_config", {}).get("data", {}).get("test", "")
    descriptive_test = test == "legacy_v1/test"
    figures = experiment_dir / "figures"
    figures.mkdir(exist_ok=True)
    (experiment_dir / "conditions.csv").write_text(_csv_text(rows), encoding="utf-8")
    (experiment_dir / "summary.md").write_text(_summary_text(run, rows, descriptive_test), encoding="utf-8")
    (figures / "iia.svg").write_text(_figure_text(rows, run_kind, descriptive_test), encoding="utf-8")
    return {"experiment_dir": str(experiment_dir), "run_kind": run_kind,
            "conditions": len(rows), "statuses": dict(Counter(row["status"] for row in rows)),
            "artifacts": ["conditions.csv", "summary.md", "figures/iia.svg"]}
