"""Summarize saved run progress without opening results or loading a model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from statistics import fmean


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Run timestamps must include a UTC offset.")
    return parsed.astimezone(timezone.utc)


def _counts(records: list[dict]) -> dict[str, int]:
    counts = {"completed": 0, "failed": 0, "pending": 0, "running": 0, "total": len(records)}
    for record in records:
        state = record["status"]
        if state not in {"complete", "failed", "pending", "running"}:
            raise ValueError(f"Unknown saved record status: {state!r}.")
        counts[{"complete": "completed", "failed": "failed"}.get(state, "pending")] += 1
        if state == "running":
            counts["running"] += 1
    return counts


def _mean_duration(records: list[dict]) -> float | None:
    durations = []
    for record in records:
        if record["status"] != "complete" or "elapsed_seconds" not in record:
            continue
        value = record["elapsed_seconds"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Completed record elapsed_seconds must be a finite nonnegative number.")
        durations.append(value)
    return fmean(durations) if durations else None


def read_status(experiment_dir: str | Path, *, now: datetime | None = None) -> dict:
    """Read only run.json and estimate remaining records from saved mean durations.

    A running record counts as pending. Before any post-lock record completes,
    its duration is estimated from the condition mean and explicitly identified
    as such. Completed older runs need no duration estimate: their recorded end
    is the finish time. Failed runs do not have an estimated finish time.
    """
    directory = Path(experiment_dir).expanduser().resolve()
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("The status clock must include a UTC offset.")
    current = current.astimezone(timezone.utc)
    started = _timestamp(metadata["started_at_utc"])
    state = metadata["status"]
    if state not in {"complete", "failed", "pending", "running"}:
        raise ValueError(f"Unknown saved run status: {state!r}.")
    ended = _timestamp(metadata["ended_at_utc"]) if state in {"complete", "failed"} and metadata.get("ended_at_utc") else None
    conditions = metadata["conditions"]
    post_lock = metadata.get("post_lock", [])
    condition_counts, post_lock_counts = _counts(conditions), _counts(post_lock)
    mean_condition, mean_post_lock = _mean_duration(conditions), _mean_duration(post_lock)
    remaining, finish = None, None
    basis = "unavailable until a condition completes with elapsed_seconds"
    if state == "complete":
        remaining = 0.0
        finish = ended
        basis = "recorded completion"
    elif state == "failed" or condition_counts["failed"] or post_lock_counts["failed"]:
        basis = "unavailable for a failed run"
    else:
        pending_conditions, pending_post_lock = condition_counts["pending"], post_lock_counts["pending"]
        post_lock_duration = mean_post_lock if mean_post_lock is not None else mean_condition
        if ((not pending_conditions or mean_condition is not None)
                and (not pending_post_lock or post_lock_duration is not None)):
            remaining = pending_conditions * (mean_condition or 0.0) + pending_post_lock * (post_lock_duration or 0.0)
            finish = current + timedelta(seconds=remaining)
            basis = "mean completed condition duration"
            if pending_post_lock:
                basis += (" and mean completed post-lock duration" if mean_post_lock is not None
                          else "; pending post-lock records use the condition mean")
    return {"experiment_dir": str(directory), "status": state,
            "conditions": condition_counts, "post_lock": post_lock_counts,
            "elapsed_seconds": max(0.0, ((ended or current) - started).total_seconds()),
            "mean_condition_seconds": mean_condition, "mean_post_lock_seconds": mean_post_lock,
            "estimated_remaining_seconds": remaining,
            "estimated_finish_at_utc": finish.isoformat() if finish is not None else None,
            "estimate_basis": basis}


def _duration(seconds: float) -> str:
    hours, remainder = divmod(round(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_status(report: dict) -> str:
    """Format progress and its ETA basis for the status command."""
    lines = [f"Experiment {report['status']}: {report['experiment_dir']}"]
    for key, label in (("conditions", "Conditions"), ("post_lock", "Post-lock")):
        counts = report[key]
        lines.append(f"{label}: {counts['completed']} completed / {counts['failed']} failed / "
                     f"{counts['pending']} pending ({counts['running']} running; {counts['total']} total)")
    lines.append(f"Elapsed: {_duration(report['elapsed_seconds'])}")
    if report["mean_condition_seconds"] is not None:
        lines.append(f"Mean completed condition: {report['mean_condition_seconds']:.3f} s")
    if report["status"] == "complete" and report["estimated_finish_at_utc"] is not None:
        lines.append(f"Finished at (UTC): {report['estimated_finish_at_utc']}; remaining: 00:00:00")
    elif report["estimated_finish_at_utc"] is not None:
        lines.append(f"Estimated finish (UTC): {report['estimated_finish_at_utc']}; "
                     f"remaining: {_duration(report['estimated_remaining_seconds'])}")
    else:
        lines.append("Estimated finish (UTC): unavailable")
    lines.append(f"Estimate basis: {report['estimate_basis']}")
    return "\n".join(lines)
