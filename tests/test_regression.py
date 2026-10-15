"""Compare the generic experiment with immutable saved scientific evidence."""

import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "outputs/phase2/gpt2-layer8-block-output-N-rank1-seed42/full"
ALIGNMENT_SHA256 = {
    "alignment.pt": "99e0b38582a600437b54480cd4fe654b06a9bb7adaa220f79d956e03a918c148",
    "initial_alignment.pt": "250b53cce7164a4a346287d620ebf36ffad40944cb39d6fe41c84aff1915e5c0",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def assert_reference_parity(reference: Path, actual: Path) -> None:
    """Assert exact counts, raw tensors, predictions, and optimizer history."""
    torch = pytest.importorskip("torch", reason="Alignment parity requires torch")
    expected_result = _read_json(reference / "result.json")
    actual_result = _read_json(actual / "result.json")
    for split, correct, total in (("initial_train", 94, 200), ("train", 173, 200),
                                  ("test", 79, 100)):
        for result in (expected_result, actual_result):
            metric = result["metrics"][split]
            assert (metric["iia_correct"], metric["iia_total"]) == (correct, total), split
        assert actual_result["metrics"][split] == expected_result["metrics"][split], split

    for filename, pinned_hash in ALIGNMENT_SHA256.items():
        expected_path = reference / filename
        assert expected_result["artifacts"][filename] == pinned_hash, filename
        assert hashlib.sha256(expected_path.read_bytes()).hexdigest() == pinned_hash, filename
        # torch.save container bytes can differ across otherwise identical saves.
        # Compare every raw parametrization tensor instead of requiring byte parity.
        expected = torch.load(expected_path, map_location="cpu", weights_only=True)["interventions"]
        observed = torch.load(actual / filename, map_location="cpu", weights_only=True)["interventions"]
        assert expected.keys() == observed.keys(), filename
        for intervention_key, state in expected.items():
            assert state.keys() == observed[intervention_key].keys(), filename
            for name, tensor in state.items():
                assert tensor.dtype == observed[intervention_key][name].dtype, (filename, name)
                assert torch.equal(tensor, observed[intervention_key][name]), (filename, name)

    for filename, count in (("initial_train_predictions.jsonl", 200),
                            ("train_predictions.jsonl", 200),
                            ("test_predictions.jsonl", 100)):
        expected = _read_rows(reference / filename)
        observed = _read_rows(actual / filename)
        assert len(expected) == len(observed) == count, filename
        for index, (expected_row, observed_row) in enumerate(zip(expected, observed)):
            assert observed_row == expected_row, (filename, index)

    expected_steps = _read_rows(reference / "training_steps.jsonl")
    observed_steps = _read_rows(actual / "training_steps.jsonl")
    assert len(expected_steps) == len(observed_steps) == 100
    for index, (expected_row, observed_row) in enumerate(zip(expected_steps, observed_steps)):
        expected_values = {key: value for key, value in expected_row.items() if key != "elapsed_seconds"}
        observed_values = {key: value for key, value in observed_row.items() if key != "elapsed_seconds"}
        assert observed_values == expected_values, ("training_steps.jsonl", index)
    assert _read_json(actual / "training.json") == _read_json(reference / "training.json")


def _condition_directory(path: Path) -> Path:
    if (path / "result.json").is_file():
        return path
    results = list((path / "conditions").rglob("result.json"))
    assert len(results) == 1, f"Expected one condition result under {path}; found {len(results)}"
    return results[0].parent


@pytest.mark.gpu
@pytest.mark.skipif(os.environ.get("IOI_DAS_RUN_GPU_REGRESSION") != "1",
                    reason="Set IOI_DAS_RUN_GPU_REGRESSION=1 to run the cached-model regression")
def test_cached_model_experiment_reproduces_saved_reference():
    """Run the real config on GPU, or verify a supplied completed experiment."""
    existing = os.environ.get("IOI_DAS_REGRESSION_DIR")
    if existing:
        actual = _condition_directory(Path(existing))
    else:
        torch = pytest.importorskip("torch", reason="GPU regression requires torch")
        if not torch.cuda.is_available():
            pytest.skip("GPU regression requires an available CUDA device")
        from ioi_das.config import load_config
        from ioi_das.pipeline import run_experiment

        result = run_experiment(load_config(ROOT / "configs/single-condition-das/layer8-seed42.json"))
        actual = _condition_directory(Path(result["experiment_dir"]))
    assert_reference_parity(REFERENCE, actual)


def test_reference_parity_accepts_saved_evidence():
    """Check that the verifier accepts the pinned saved artifacts on CPU."""
    assert_reference_parity(REFERENCE, REFERENCE)


@pytest.mark.parametrize("artifact", ["alignment.pt", "initial_alignment.pt",
                                     "test_predictions.jsonl", "training_steps.jsonl",
                                     "training.json"])
def test_reference_parity_detects_scientific_drift(tmp_path, artifact):
    """Detect tensor, prediction, per-update, and training-summary changes."""
    torch = pytest.importorskip("torch", reason="Alignment parity requires torch")
    actual = tmp_path / "condition"
    shutil.copytree(REFERENCE, actual)
    path = actual / artifact
    if artifact.endswith(".pt"):
        state = torch.load(path, map_location="cpu", weights_only=True)
        tensor = next(iter(next(iter(state["interventions"].values())).values()))
        tensor.view(-1)[0].add_(1)
        torch.save(state, path)
    elif artifact.endswith(".jsonl"):
        rows = _read_rows(path)
        key = "factual_loss" if artifact.startswith("test_") else "loss"
        rows[0][key] += 0.125
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    else:
        value = _read_json(path)
        value["first_step_loss"] += 0.125
        path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(AssertionError):
        assert_reference_parity(REFERENCE, actual)
