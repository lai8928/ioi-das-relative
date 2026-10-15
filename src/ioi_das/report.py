"""Regenerate experiment tables and figures from saved JSON files only."""

from collections import Counter
import csv
import hashlib
from html import escape
import io
import json
from pathlib import Path
from statistics import mean, stdev
from typing import Any


SPLITS = ("initial_train", "train", "validation", "test")
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


def _add_post_lock_metrics(experiment_dir: Path, run: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    records = run.get("post_lock", [])
    selection_path = experiment_dir / "selection.json"
    evaluation_started = any(record.get("status") in {"running", "complete"}
                             or (experiment_dir / record["path"] / "result.json").is_file()
                             for record in records)
    if evaluation_started and not selection_path.is_file():
        raise ValueError("Post-lock records require selection.json; restore the saved selection lock.")
    selection_hash = hashlib.sha256(selection_path.read_bytes()).hexdigest() if selection_path.is_file() else None
    by_condition = {row["condition"]: row for row in rows}
    scheduled = bool(run.get("resolved_config", {}).get("selection")) and run.get("run_kind") != "smoke"
    for row in rows:
        row["post_lock_status"] = "pending" if scheduled else "not_scheduled"
        row["post_lock_error"] = ""
    seen = set()
    for record in records:
        name = record["condition_path"]
        if name not in by_condition or name in seen:
            raise ValueError(f"Post-lock record has an unknown or duplicate condition_path: {name!r}.")
        seen.add(name)
        row = by_condition[name]
        directory = (experiment_dir / record["path"]).resolve()
        if not directory.is_relative_to(experiment_dir / "post_lock"):
            raise ValueError(f"Post-lock path must be inside {experiment_dir / 'post_lock'}: {record['path']!r}.")
        result_path = directory / "result.json"
        row["post_lock_status"] = record.get("status", "pending")
        row["post_lock_error"] = record.get("error", "")
        if not result_path.is_file():
            if row["post_lock_status"] == "complete":
                row["post_lock_status"] = "missing_result"
            continue
        expected_hash = record.get("result_sha256")
        if expected_hash and hashlib.sha256(result_path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"Post-lock result SHA-256 mismatch: {result_path}.")
        result = _read_json(result_path)
        if result.get("selection_sha256", selection_hash) != selection_hash:
            raise ValueError(f"Post-lock selection SHA-256 mismatch: {result_path}.")
        row["post_lock_status"] = result.get("status", row["post_lock_status"])
        row["post_lock_error"] = result.get("error", row["post_lock_error"])
        for split, metrics in result.get("metrics", {}).items():
            if split not in run.get("resolved_config", {}).get("selection", {}).get("evaluate_after_lock", []):
                raise ValueError(f"Post-lock split {split!r} was not configured for locked evaluation.")
            for metric in METRICS:
                row[f"{split}_{metric}"] = metrics.get(metric, "")


def _csv_text(rows: list[dict[str, Any]]) -> str:
    fields = ("condition", "status", "run_kind", "layer", "component", "location", "rank", "seed",
              *(f"{split}_{metric}" for split in SPLITS for metric in METRICS),
              "post_lock_status", "error", "post_lock_error")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _layer_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    layers = sorted({row["layer"] for row in rows if row["layer"] != ""}, key=int)
    for split in SPLITS:
        for layer in layers:
            cells = [row for row in rows if row["layer"] == layer]
            values = [float(row[f"{split}_iia"]) for row in cells
                      if row[f"{split}_iia"] != "" and row["status"] == "complete"
                      and (split != "test" or row["post_lock_status"] in {"complete", "not_scheduled"})]
            summaries.append({"layer": layer, "split": split, "mean_iia": mean(values) if values else "",
                              "seed_sample_sd": stdev(values) if len(values) > 1 else "",
                              "completed_seeds": len(values), "expected_seeds": len(cells),
                              "flag": "complete" if len(values) == len(cells) else "incomplete"})
    return summaries


def _layer_csv_text(summaries: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=("layer", "split", "mean_iia", "seed_sample_sd",
                                              "completed_seeds", "expected_seeds", "flag"), lineterminator="\n")
    writer.writeheader()
    writer.writerows(summaries)
    return output.getvalue()


def _markdown_value(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _iia_text(row: dict[str, Any], split: str) -> str:
    ratio = row[f"{split}_iia"]
    if ratio == "":
        return "—"
    correct, total = row[f"{split}_iia_correct"], row[f"{split}_iia_total"]
    return f"{correct}/{total} = {ratio}"


def _summary_text(run: dict[str, Any], rows: list[dict[str, Any]], descriptive_test: bool,
                  selection: dict[str, Any] | None = None) -> str:
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
    if selection:
        lines.extend([f"Selected layer: **{selection['selected_layer']}**; metric: `{selection.get('metric', 'validation_iia')}`.",
                      "The choice was locked in `selection.json` before post-lock evaluation.", ""])
    test_label = "Test IIA (descriptive)" if descriptive_test else "Test IIA"
    lines.extend([f"| Condition | Status | Initial train IIA | Train IIA | Validation IIA | {test_label} | Post-lock status |",
                  "| --- | --- | --- | --- | --- | --- | --- |"])
    for row in rows:
        cells = [row["condition"], row["status"], *(_iia_text(row, split) for split in SPLITS), row["post_lock_status"]]
        lines.append("| " + " | ".join(_markdown_value(cell) for cell in cells) + " |")
    lines.extend(["", "Full-precision metrics and exact counts are saved in `conditions.csv`.",
                  "Missing metrics are shown as —; failed and pending conditions remain in the table.", "",
                  "Per-layer means and sample SD across seeds are saved in `layer_summary.csv`.",
                  "Seed SD describes variation across seeds; it is not a confidence interval.",
                  "A single available seed has no sample SD. Incomplete layers are flagged in the CSV.", "",
                  "![Validation IIA by layer](figures/validation_by_layer.svg)", "",
                  "![Train and validation IIA by layer](figures/train_validation_by_layer.svg)", "",
                  "![Post-lock test IIA by layer](figures/test_by_layer.svg)", "",
                  "![Saved IIA by condition](figures/iia.svg)", ""])
    errors = [row for row in rows if row["error"]]
    if errors:
        lines.extend(["Condition errors:", ""])
        lines.extend(f"- `{_markdown_value(row['condition'])}`: {_markdown_value(row['error'])}" for row in errors)
        lines.append("")
    post_lock_errors = [row for row in rows if row["post_lock_error"]]
    if post_lock_errors:
        lines.extend(["Post-lock errors:", ""])
        lines.extend(f"- `{_markdown_value(row['condition'])}`: {_markdown_value(row['post_lock_error'])}"
                     for row in post_lock_errors)
        lines.append("")
    return "\n".join(lines)


def _figure_text(rows: list[dict[str, Any]], run_kind: str, descriptive_test: bool) -> str:
    width, left, chart_width = 1100, 480, 500
    height = 120 + max(1, len(rows)) * 104
    colors = ("#94a3b8", "#2563eb", "#d97706", "#059669")
    labels = ("Initial train", "Train", "Validation", "Test (descriptive)" if descriptive_test else "Test")
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
        y = 104 + index * 104
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


def _curve_points(points: list[tuple[float, float | None]], color: str, thick: bool) -> str:
    parts = []
    segment = []
    for x, value in [*points, (0, None)]:
        if value is None:
            if len(segment) > 1:
                joined = " ".join(f"{px:.12g},{py:.12g}" for px, py in segment)
                parts.append(f'<polyline points="{joined}" fill="none" stroke="{color}" '
                             f'stroke-width="{3 if thick else 1.2}"/>')
            segment = []
            continue
        y = 440 - value * 320
        segment.append((x, y))
        parts.append(f'<circle cx="{x:.12g}" cy="{y:.12g}" r="{4 if thick else 2.5}" fill="{color}">'
                     f'<title>IIA {value:.12g}</title></circle>')
    return "\n".join(parts)


def _layer_curve(title: str, rows: list[dict[str, Any]], summaries: list[dict[str, Any]],
                 splits: tuple[str, ...], run_kind: str, show_seeds: bool) -> str:
    layers = sorted({int(row["layer"]) for row in rows if row["layer"] != ""})
    x_positions = {layer: 80 + index * 740 / max(1, len(layers) - 1) for index, layer in enumerate(layers)}
    colors = ("#2563eb", "#d97706", "#059669", "#9333ea")
    series = []
    if show_seeds:
        seeds = sorted({row["seed"] for row in rows if row["seed"] != ""}, key=int)
        for index, seed in enumerate(seeds):
            values = {int(row["layer"]): float(row[f"{splits[0]}_iia"]) for row in rows
                      if row["seed"] == seed and row["layer"] != "" and row[f"{splits[0]}_iia"] != ""
                      and row["status"] == "complete"
                      and (splits[0] != "test" or row["post_lock_status"] in {"complete", "not_scheduled"})}
            series.append((f"Seed {seed}", colors[index % len(colors)], values, {}, False))
    for index, split in enumerate(splits):
        values = {int(row["layer"]): row["mean_iia"] for row in summaries
                  if row["split"] == split and row["mean_iia"] != ""}
        deviations = {int(row["layer"]): row["seed_sample_sd"] for row in summaries
                      if row["split"] == split and row["seed_sample_sd"] != ""}
        series.append((f"{split.replace('_', ' ').title()} mean ± seed SD",
                       "#0f172a" if show_seeds else colors[index], values, deviations, True))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="510" '
             'viewBox="0 0 960 510" role="img" aria-labelledby="title description">',
             f'<title id="title">{escape(title)} ({escape(run_kind)} run)</title>',
             '<desc id="description">IIA by layer. Error bars show sample SD across seeds, not a confidence interval. '
             'Missing results have no points; means with missing seeds are incomplete.</desc>',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g font-family="sans-serif" font-size="12" fill="#0f172a">',
             f'<text x="30" y="28" font-size="18">{escape(title)} — {escape(run_kind)} run</text>']
    for index, (label, color, values, deviations, thick) in enumerate(series):
        parts.append(f'<text x="{30 + index % 2 * 380}" y="{53 + index // 2 * 20}" fill="{color}">{escape(label)}</text>')
        points = [(x_positions[layer], values.get(layer)) for layer in layers]
        parts.append(_curve_points(points, color, thick))
        for layer, deviation in deviations.items():
            x = x_positions[layer]
            if layer not in values:
                continue
            top = 440 - min(1, values[layer] + deviation) * 320
            bottom = 440 - max(0, values[layer] - deviation) * 320
            parts.append(f'<path d="M {x:.12g} {top:.12g} V {bottom:.12g} '
                         f'M {x - 4:.12g} {top:.12g} H {x + 4:.12g} '
                         f'M {x - 4:.12g} {bottom:.12g} H {x + 4:.12g}" stroke="{color}" fill="none"/>')
    for tick in range(6):
        y = 440 - tick / 5 * 320
        parts.extend([f'<line x1="70" y1="{y:g}" x2="830" y2="{y:g}" stroke="#e2e8f0"/>',
                      f'<text x="60" y="{y + 4:g}" text-anchor="end">{tick / 5:g}</text>'])
    for layer in layers:
        parts.append(f'<text x="{x_positions[layer]:.12g}" y="462" text-anchor="middle">{layer}</text>')
    parts.extend(['<text x="450" y="487" text-anchor="middle">Layer</text>',
                  '<text x="15" y="280" transform="rotate(-90 15 280)" text-anchor="middle">IIA</text>',
                  "</g>", "</svg>", ""])
    return "\n".join(parts)


def generate_report(experiment_dir: Path) -> dict[str, Any]:
    """Write deterministic tables, a summary, and layer curves from saved metadata."""
    experiment_dir = Path(experiment_dir).expanduser().resolve()
    run = _read_json(experiment_dir / "run.json")
    run_kind = run.get("run_kind", "unknown")
    rows = [_condition_row(record, experiment_dir, run_kind)
            for record in _saved_conditions(experiment_dir, run)]
    _add_post_lock_metrics(experiment_dir, run, rows)
    summaries = _layer_summaries(rows)
    selection_path = experiment_dir / "selection.json"
    selection = _read_json(selection_path) if selection_path.is_file() else None
    test = run.get("resolved_config", {}).get("data", {}).get("test", "")
    descriptive_test = test == "legacy_v1/test"
    figures = experiment_dir / "figures"
    figures.mkdir(exist_ok=True)
    (experiment_dir / "conditions.csv").write_text(_csv_text(rows), encoding="utf-8")
    (experiment_dir / "layer_summary.csv").write_text(_layer_csv_text(summaries), encoding="utf-8")
    (experiment_dir / "summary.md").write_text(_summary_text(run, rows, descriptive_test, selection), encoding="utf-8")
    (figures / "iia.svg").write_text(_figure_text(rows, run_kind, descriptive_test), encoding="utf-8")
    curves = {"validation_by_layer.svg": ("Validation IIA by layer", ("validation",), True),
              "train_validation_by_layer.svg": ("Train and validation IIA by layer", ("train", "validation"), False),
              "test_by_layer.svg": ("Post-lock test IIA by layer (descriptive)" if descriptive_test else "Test IIA by layer",
                                    ("test",), True)}
    for name, (title, splits, show_seeds) in curves.items():
        (figures / name).write_text(_layer_curve(title, rows, summaries, splits, run_kind, show_seeds), encoding="utf-8")
    return {"experiment_dir": str(experiment_dir), "run_kind": run_kind,
            "conditions": len(rows), "statuses": dict(Counter(row["status"] for row in rows)),
            "artifacts": ["conditions.csv", "layer_summary.csv", "summary.md", "figures/iia.svg",
                          *(f"figures/{name}" for name in curves)]}
