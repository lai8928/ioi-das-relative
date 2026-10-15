"""Exercise experiment lifecycle contracts with CPU models and stub forwards."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch", reason="Experiment checks require the DAS runtime")
pytest.importorskip("pyvene", reason="Experiment checks require the external pyvene dependency")

from ioi_das import evaluate, experiment, intervention, train, validation
from ioi_das.data import sha256_file


ROOT = Path(__file__).resolve().parents[1]


class _Alignment(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.rotate_layer = torch.nn.Linear(1, 1, bias=False)
        with torch.no_grad():
            self.rotate_layer.weight.fill_(1)


class _ScopedFixture:
    def __init__(self, model, state):
        self.interventions = {"fixture": _Alignment()}
        self.activations = {"fixture": object()}
        self.full_intervention_outputs = [object()]
        self.handle = model.register_forward_hook(lambda *args: None)
        self.state = state

    def _cleanup_states(self):
        if self.state["cleanup_defect"] != "hooks":
            self.handle.remove()
        if self.state["cleanup_defect"] != "caches":
            self.activations.clear()


@pytest.fixture
def checkpoint_runtime(tmp_path, monkeypatch):
    model = torch.nn.Linear(1, 1, bias=False).requires_grad_(False)
    model.config = SimpleNamespace(_attn_implementation="eager")
    sentinel = model.register_forward_hook(lambda *args: None)
    original_hooks = validation.hook_snapshot(model)
    model_hash = validation.fingerprint_model(model)
    state = {"loads": [], "wrappers": [], "evaluations": [], "fingerprints": [],
             "fail": False, "mutate": False, "cleanup_defect": None}
    tokenizer, reference = object(), object()

    def load_model(*args, **kwargs):
        state["loads"].append((args, kwargs))
        return model

    def build(model_argument, layer, rank):
        assert model_argument is model
        assert validation.hook_snapshot(model) == original_hooks
        wrapper = _ScopedFixture(model, state)
        state["wrappers"].append(wrapper)
        return wrapper

    def evaluate_condition(model_argument, wrapper, records, tokenizer_argument,
                           reference_argument, device, batch_size, location, split):
        assert model_argument is model
        assert tokenizer_argument is tokenizer and reference_argument is reference
        value = float(wrapper.interventions["fixture"].rotate_layer.weight.item())
        state["evaluations"].append((split, value))
        if state["mutate"]:
            with torch.no_grad():
                model.weight.add_(1)
        if state["fail"]:
            raise RuntimeError("fixture evaluation failed")
        return {"metrics": {"iia_correct": 1, "iia_total": 1, "iia": 1.0},
                "predictions": [{"sample_id": f"{split}-fixture", "alignment_value": value}]}

    original_fingerprint = validation.fingerprint_model

    def fingerprint(model_argument):
        value = original_fingerprint(model_argument)
        state["fingerprints"].append(value)
        return value

    monkeypatch.setattr(experiment, "load_tokenizers", lambda options: (tokenizer, reference))
    monkeypatch.setattr(intervention, "load_model", load_model)
    monkeypatch.setattr(intervention, "build_intervention", build)
    monkeypatch.setattr(evaluate, "evaluate_condition", evaluate_condition)
    monkeypatch.setattr(validation, "fingerprint_model", fingerprint)
    selection = tmp_path / "selection.json"
    selection.write_text('{"selected_layer": 8}', encoding="utf-8")
    checkpoints = []
    for value in (2.0, 3.0):
        checkpoint = tmp_path / f"alignment-{int(value)}.pt"
        torch.save({"condition": {"layer": 8},
                    "interventions": {"fixture": {"rotate_layer.weight": torch.tensor([[value]])}}},
                   checkpoint)
        checkpoints.append(checkpoint)
    config = json.loads((ROOT / "configs/base.json").read_text(encoding="utf-8"))
    runtime_options = {"model_options": config["model"], "tokenizer_options": config["tokenizer"],
                       "device_name": "cpu", "cpu_threads": 1}
    options = {**runtime_options, "pairs": {"test": ["fixture"]}, "layer": 8, "rank": 1,
               "location": "N", "seed": 42, "evaluation_batch_size": 1,
               "selection_path": selection, "selection_sha256": sha256_file(selection),
               "dataset_metadata": {"test": {"sha256": "fixture"}}}
    yield {"model": model, "model_hash": model_hash, "hooks": original_hooks, "state": state,
           "runtime_options": runtime_options, "options": options, "selection": selection,
           "checkpoints": checkpoints, "config": config}
    for wrapper in state["wrappers"]:
        wrapper.handle.remove()
    sentinel.remove()


def _evaluate_saved(directory, checkpoint, fixture, runtime):
    return experiment.evaluate_checkpoint(directory, checkpoint, **fixture["options"],
                                          checkpoint_sha256=sha256_file(checkpoint), runtime=runtime)


def test_shared_runtime_loads_once_and_cleans_each_checkpoint(checkpoint_runtime, tmp_path):
    fixture = checkpoint_runtime
    state = fixture["state"]
    with experiment.evaluation_runtime(**fixture["runtime_options"]) as runtime:
        assert runtime.model is fixture["model"]
        for index, checkpoint in enumerate(fixture["checkpoints"]):
            result = _evaluate_saved(tmp_path / f"evaluation-{index}", checkpoint, fixture, runtime)
            assert result["status"] == "complete"
            assert result["checkpoint_sha256"] == sha256_file(checkpoint)
            assert result["selection_sha256"] == fixture["options"]["selection_sha256"]
            assert result["model_sha256"] == fixture["model_hash"]
            assert result["validation"] == {"cleanup": "passed", "frozen_weights": "passed"}
            assert validation.hook_snapshot(runtime.model) == fixture["hooks"]
            assert not state["wrappers"][-1].activations
            assert not state["wrappers"][-1].full_intervention_outputs
    assert len(state["loads"]) == 1
    assert len(state["wrappers"]) == 2
    assert state["evaluations"] == [("test", 2.0), ("test", 3.0)]
    assert state["fingerprints"] == [fixture["model_hash"]] * 4


@pytest.mark.parametrize("changed", ["missing_lock", "lock", "checkpoint"])
def test_shared_runtime_rechecks_lock_and_hash_before_each_checkpoint(
        checkpoint_runtime, tmp_path, changed):
    fixture = checkpoint_runtime
    first, second = fixture["checkpoints"]
    expected_hash = sha256_file(second)
    with experiment.evaluation_runtime(**fixture["runtime_options"]) as runtime:
        _evaluate_saved(tmp_path / "first", first, fixture, runtime)
        if changed == "missing_lock":
            fixture["selection"].unlink()
        elif changed == "lock":
            fixture["selection"].write_text("changed lock", encoding="utf-8")
        else:
            second.write_bytes(b"changed checkpoint")
        expected_error = "Checkpoint hash mismatch" if changed == "checkpoint" else "Missing or changed selection lock"
        with pytest.raises(ValueError, match=expected_error):
            experiment.evaluate_checkpoint(tmp_path / "second", second, **fixture["options"],
                                           checkpoint_sha256=expected_hash, runtime=runtime)
    assert not (tmp_path / "second").exists()
    assert len(fixture["state"]["wrappers"]) == 1
    assert fixture["state"]["evaluations"] == [("test", 2.0)]


def test_failed_checkpoint_cleans_and_reuses_the_frozen_runtime(checkpoint_runtime, tmp_path):
    fixture = checkpoint_runtime
    state = fixture["state"]
    with experiment.evaluation_runtime(**fixture["runtime_options"]) as runtime:
        state["fail"] = True
        failed = tmp_path / "failed"
        with pytest.raises(RuntimeError, match="fixture evaluation failed"):
            _evaluate_saved(failed, fixture["checkpoints"][0], fixture, runtime)
        assert not (failed / "result.json").exists()
        assert "fixture evaluation failed" in json.loads((failed / "failure.json").read_text())["error"]
        assert validation.hook_snapshot(runtime.model) == fixture["hooks"]
        assert not state["wrappers"][-1].activations
        assert not state["wrappers"][-1].full_intervention_outputs
        assert state["fingerprints"] == [fixture["model_hash"]] * 2
        state["fail"] = False
        result = _evaluate_saved(tmp_path / "recovered", fixture["checkpoints"][1], fixture, runtime)
        assert result["model_sha256"] == fixture["model_hash"]
    assert len(state["loads"]) == 1
    assert state["fingerprints"] == [fixture["model_hash"]] * 4


@pytest.mark.parametrize("defect", ["weights", "hooks", "caches"])
def test_checkpoint_rejects_model_mutation_or_incomplete_cleanup(checkpoint_runtime, tmp_path, defect):
    fixture = checkpoint_runtime
    state = fixture["state"]
    state["mutate"] = defect == "weights"
    state["cleanup_defect"] = defect if defect in ("hooks", "caches") else None
    expected_error = "caches remained" if defect == "caches" else "changed model weights or left condition-owned hooks"
    output = tmp_path / "failed"
    with experiment.evaluation_runtime(**fixture["runtime_options"]) as runtime:
        with pytest.raises(RuntimeError, match=expected_error):
            _evaluate_saved(output, fixture["checkpoints"][0], fixture, runtime)
    assert not (output / "result.json").exists()
    assert expected_error in json.loads((output / "failure.json").read_text())["error"]


def test_initial_train_and_validation_finish_before_training(checkpoint_runtime, tmp_path, monkeypatch):
    fixture = checkpoint_runtime
    state = fixture["state"]
    config = fixture["config"]
    output = tmp_path / "condition"
    events = []
    pairs = {split: [SimpleNamespace(sample_id=f"{split}-fixture")]
             for split in ("train", "validation")}
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "set_device", lambda device: None)
    monkeypatch.setattr(torch.cuda, "reset_peak_memory_stats", lambda device: None)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda device: "fixture CPU model")
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda device: 0)
    monkeypatch.setattr(experiment, "runtime_environment", lambda *args: {})
    import transformers
    from transformers.utils import hub

    monkeypatch.setattr(transformers, "set_seed", lambda seed: None)
    asset = tmp_path / "cached_asset"
    asset.write_bytes(b"fixture cached asset")
    monkeypatch.setattr(hub, "cached_file", lambda *args, **kwargs: str(asset))
    monkeypatch.setattr(validation, "run_preflight_validation", lambda *args:
                        {"model_sha256": fixture["model_hash"], "status": "passed"})
    monkeypatch.setattr(validation, "validate_after_training", lambda *args: {"status": "passed"})
    monkeypatch.setattr(intervention, "prepare_batch", lambda records, *args: SimpleNamespace(pairs=records))
    monkeypatch.setattr(intervention, "intervention_forward", lambda *args: torch.ones(1, 2))
    original_load = torch.load
    monkeypatch.setattr(torch, "load", lambda path, **kwargs:
                        original_load(path, map_location="cpu", weights_only=True))
    original_evaluate = evaluate.evaluate_condition

    def evaluate_split(*args):
        split = args[-1]
        events.append(("evaluate", split))
        return original_evaluate(*args)

    def train_alignment(model, wrapper, *args, **kwargs):
        assert events == [("evaluate", "train"), ("evaluate", "validation")]
        for split in ("train", "validation"):
            saved = json.loads((output / f"initial_{split}_predictions.jsonl").read_text())
            assert saved["alignment_value"] == 1.0
        events.append(("train", "first_optimizer_step"))
        with torch.no_grad():
            wrapper.interventions["fixture"].rotate_layer.weight.fill_(4)
        return {"optimizer_steps": 1}

    monkeypatch.setattr(evaluate, "evaluate_condition", evaluate_split)
    monkeypatch.setattr(train, "train_alignment", train_alignment)
    result = experiment.run_condition(
        output, pairs, model_options=config["model"], tokenizer_options=config["tokenizer"],
        training_options=config["training"], layer=8, rank=1, component="block_output",
        target_variable="position", location="N", seed=42, device_name="cuda:0", cpu_threads=1,
        evaluation_batch_size=1, dataset_metadata={}, provenance={"commit": "fixture"},
        config_sha256="fixture", evaluation_splits=("train", "validation"))
    assert result["status"] == "complete"
    assert set(result["metrics"]) == {"initial_train", "initial_validation", "train", "validation"}
    assert events == [("evaluate", "train"), ("evaluate", "validation"),
                      ("train", "first_optimizer_step"),
                      ("evaluate", "train"), ("evaluate", "validation")]
    assert state["evaluations"] == [("train", 1.0), ("validation", 1.0),
                                    ("train", 4.0), ("validation", 4.0)]
    assert validation.hook_snapshot(fixture["model"]) == fixture["hooks"]
