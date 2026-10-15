"""Lock choices from complete validation evidence with deterministic exact ties."""

import json
from pathlib import Path

import pytest

from ioi_das.data import sha256_file
from ioi_das.experiment import evaluate_checkpoint
from ioi_das.selection import choose_layer, lock_selection


def _value(layer, seed, correct, total):
    return {"layer": layer, "seed": seed, "iia_correct": correct, "iia_total": total}


def test_selection_uses_exact_rational_means_and_lowest_layer_tie_break():
    # A floating mean makes (0.1 + 0.2) / 2 exceed 0.15; the true means tie.
    values = [_value(8, 42, 1, 10), _value(8, 43, 2, 10),
              _value(2, 42, 3, 20), _value(2, 43, 3, 20)]
    selected, means = choose_layer(values)
    assert selected == 2
    assert means == {"2": 0.15, "8": 0.15}
    assert choose_layer(list(reversed(values))) == (selected, means)


def test_selection_aggregates_seeds_before_selecting_layer():
    values = [_value(7, 42, 100, 100), _value(7, 43, 0, 100),
              _value(8, 42, 60, 100), _value(8, 43, 60, 100)]
    assert choose_layer(values) == (8, {"7": 0.5, "8": 0.6})


@pytest.mark.parametrize("values", [[], [_value(7, 42, 1, 2), _value(8, 43, 1, 2)],
                                    [_value(7, 42, 1, 2), _value(7, 43, 1, 2), _value(8, 42, 1, 2)]])
def test_selection_requires_complete_matching_seed_sets(values):
    with pytest.raises(ValueError, match="matching seed sets"):
        choose_layer(values)


def test_selection_rejects_duplicate_layer_seed_contributions():
    with pytest.raises(ValueError, match="Duplicate seed 42 for layer 8"):
        choose_layer([_value(8, 42, 1, 2), _value(8, 42, 1, 2)])


def _selection_evidence(tmp_path):
    condition = tmp_path / "conditions" / "layer8"
    condition.mkdir(parents=True)
    checkpoint = condition / "alignment.pt"
    checkpoint.write_bytes(b"saved alignment")
    result = {"status": "complete", "seed": 42, "condition": {"layer": 8},
              "metrics": {"validation": {"iia": 0.83, "iia_correct": 166, "iia_total": 200}},
              "artifacts": {"alignment.pt": sha256_file(checkpoint)}}
    result_path = condition / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    metadata = {"resolved_config": {"selection": {"metric": "validation_iia",
                "aggregate": "mean_over_seeds", "tie_break": "lowest_layer", "evaluate_after_lock": ["test"]}},
                "conditions": [{"path": "conditions/layer8", "status": "complete",
                                "result_sha256": sha256_file(result_path)}],
                "config_sha256": "c" * 64, "dataset_hashes": {"val/validation": "d" * 64},
                "implementation_sha256": {"selection.py": "e" * 64}}
    return metadata


def test_selection_records_contributions_and_preserves_existing_lock(tmp_path):
    metadata = _selection_evidence(tmp_path)
    selected = lock_selection(tmp_path, metadata)
    path = tmp_path / "selection.json"
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert selected["selected_layer"] == 8
    assert selected["config_sha256"] == metadata["config_sha256"]
    assert selected["dataset_hashes"] == metadata["dataset_hashes"]
    assert selected["source_hashes"] == metadata["implementation_sha256"]
    assert selected["values"][0]["result_sha256"] == metadata["conditions"][0]["result_sha256"]
    assert selected["values"][0]["iia_correct"] == 166
    assert selected["values"][0]["iia_total"] == 200
    assert lock_selection(tmp_path, metadata) == selected
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    metadata["config_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="immutable lock"):
        lock_selection(tmp_path, metadata)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_pending_or_failed_condition_cannot_create_selection(tmp_path):
    metadata = _selection_evidence(tmp_path)
    for status in ("pending", "failed"):
        metadata["conditions"][0]["status"] = status
        with pytest.raises(ValueError, match="complete, verified condition"):
            lock_selection(tmp_path, metadata)
        assert not (tmp_path / "selection.json").exists()


@pytest.mark.parametrize("changed", [False, True])
def test_checkpoint_evaluation_requires_valid_lock_before_loading_runtime(tmp_path, changed):
    selection = tmp_path / "selection.json"
    if changed:
        selection.write_text("changed scientific choice", encoding="utf-8")
    # Required arguments are inert: lock verification must precede checkpoint/runtime access.
    with pytest.raises(ValueError, match="Missing or changed selection lock"):
        evaluate_checkpoint(tmp_path / "post_lock", tmp_path / "missing.pt", pairs={}, model_options={},
                            tokenizer_options={}, layer=8, rank=1, location="N", seed=42,
                            device_name="cuda:0", cpu_threads=1, evaluation_batch_size=20,
                            selection_path=selection, selection_sha256="0" * 64,
                            checkpoint_sha256="1" * 64, dataset_metadata={})
    assert not (tmp_path / "post_lock").exists()
