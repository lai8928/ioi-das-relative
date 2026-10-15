"""Check lightweight progress counts, saved timing estimates, and old run support."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ioi_das.status import format_status, read_status


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def _save(tmp_path, **changes):
    metadata = {"status": "running", "started_at_utc": "2026-10-15T11:58:00+00:00",
                "conditions": [{"status": "complete", "elapsed_seconds": 20},
                               {"status": "complete", "elapsed_seconds": 40},
                               {"status": "running"}, {"status": "pending"}],
                "post_lock": [{"status": "pending"} for _ in range(4)]}
    metadata.update(changes)
    (tmp_path / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    return tmp_path


def test_progress_uses_completed_durations_and_counts_running_as_pending(tmp_path):
    report = read_status(_save(tmp_path), now=NOW)
    assert report["conditions"] == {"completed": 2, "failed": 0, "pending": 2, "running": 1, "total": 4}
    assert report["post_lock"] == {"completed": 0, "failed": 0, "pending": 4, "running": 0, "total": 4}
    assert report["elapsed_seconds"] == 120
    assert report["mean_condition_seconds"] == 30
    assert report["estimated_remaining_seconds"] == 180
    assert report["estimated_finish_at_utc"] == "2026-10-15T12:03:00+00:00"
    assert "post-lock records use the condition mean" in report["estimate_basis"]
    assert "2 completed / 0 failed / 2 pending" in format_status(report)
    assert "Elapsed: 00:02:00" in format_status(report)


def test_post_lock_estimate_uses_saved_post_lock_mean_when_available(tmp_path):
    post_lock = [{"status": "complete", "elapsed_seconds": 2}, {"status": "running"}]
    report = read_status(_save(tmp_path, conditions=[{"status": "complete", "elapsed_seconds": 30}],
                               post_lock=post_lock), now=NOW)
    assert report["estimated_remaining_seconds"] == 2
    assert report["estimated_finish_at_utc"] == "2026-10-15T12:00:02+00:00"
    assert "mean completed post-lock duration" in report["estimate_basis"]


def test_no_duration_or_failed_run_does_not_invent_an_estimate(tmp_path):
    report = read_status(_save(tmp_path, conditions=[{"status": "complete"}, {"status": "pending"}]), now=NOW)
    assert report["mean_condition_seconds"] is None
    assert report["estimated_finish_at_utc"] is None
    assert "unavailable" in format_status(report)
    report = read_status(_save(tmp_path, status="failed", ended_at_utc="2026-10-15T11:59:30+00:00",
                               conditions=[{"status": "complete", "elapsed_seconds": 30}, {"status": "failed"}]), now=NOW)
    assert report["conditions"]["failed"] == 1
    assert report["elapsed_seconds"] == 90
    assert report["estimated_finish_at_utc"] is None


def test_completed_legacy_run_uses_recorded_finish_without_condition_durations(tmp_path):
    report = read_status(_save(tmp_path, status="complete", ended_at_utc="2026-10-15T11:59:30+00:00",
                               conditions=[{"status": "complete"}], post_lock=[]), now=NOW)
    assert report["elapsed_seconds"] == 90
    assert report["estimated_remaining_seconds"] == 0
    assert report["estimated_finish_at_utc"] == "2026-10-15T11:59:30+00:00"
    assert "Finished at (UTC)" in format_status(report)
    assert "recorded completion" in format_status(report)


def test_existing_layer_sweep_has_correct_completed_counts_and_no_remaining_work():
    report = read_status(ROOT / "outputs/layer-sweep/20261015-gpt2-small", now=NOW)
    assert report["conditions"] == report["post_lock"] == {"completed": 36, "failed": 0, "pending": 0, "running": 0, "total": 36}
    assert report["elapsed_seconds"] == pytest.approx(1506.580679)
    assert report["estimated_remaining_seconds"] == 0
    assert report["estimated_finish_at_utc"] == "2026-10-15T17:10:08.921109+00:00"


def test_only_run_json_is_read_and_torch_is_never_imported(tmp_path):
    _save(tmp_path)
    code = f"""
import builtins
import sys
sys.path.insert(0, {str(ROOT / 'src')!r})
from pathlib import Path
original_read = Path.read_text
original_import = builtins.__import__
def guarded_read(path, *args, **kwargs):
    assert path.name == 'run.json', path
    return original_read(path, *args, **kwargs)
def guarded_import(name, *args, **kwargs):
    assert not name.startswith(('torch', 'transformers', 'pyvene')), name
    return original_import(name, *args, **kwargs)
Path.read_text = guarded_read
builtins.__import__ = guarded_import
from ioi_das.status import format_status, read_status
assert 'completed' in format_status(read_status({str(tmp_path)!r}))
assert 'torch' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("duration", [-1, float("inf"), True])
def test_invalid_saved_duration_is_rejected(tmp_path, duration):
    _save(tmp_path, conditions=[{"status": "complete", "elapsed_seconds": duration}])
    with pytest.raises(ValueError, match="finite nonnegative"):
        read_status(tmp_path, now=NOW)


def test_unknown_record_status_is_rejected(tmp_path):
    _save(tmp_path, conditions=[{"status": "unexpected"}])
    with pytest.raises(ValueError, match="Unknown saved record status"):
        read_status(tmp_path, now=NOW)
