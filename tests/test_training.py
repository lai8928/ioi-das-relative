"""Check explicit training options without loading pretrained model weights."""

import json
from types import SimpleNamespace

import pytest


torch = pytest.importorskip("torch", reason="Training checks require torch")
pytest.importorskip("pyvene", reason="Intervention checks require pyvene")

from ioi_das import train
from ioi_das.intervention import load_model


class TrainableAlignment(torch.nn.Module):
    """Supply one trainable two-class alignment for optimizer checks."""

    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.tensor([1.0, -1.0]))

    def get_trainable_parameters(self):
        return [self.weight]


@pytest.mark.parametrize("factors, expected_rates", [
    ({}, [0.003333333333333333, 0.0031, 0.0028666666666666662, 0.002633333333333333]),
    ({"schedule_start_factor": 0.5, "schedule_end_factor": 0.2,
      "schedule_total_iters": 2}, [0.005, 0.0035, 0.002, 0.002]),
])
def test_named_schedule_steps_every_update(monkeypatch, tmp_path, factors, expected_rates):
    """Keep the legacy update schedule independent from the epoch count."""
    model = torch.nn.Linear(1, 1)
    model.requires_grad_(False)
    wrapper = TrainableAlignment()
    pairs = [SimpleNamespace(sample_id=f"sample-{index}") for index in range(4)]
    monkeypatch.setattr(train, "prepare_batch", lambda *args: SimpleNamespace(
        counterfactual_labels=torch.tensor([0, 1])))
    monkeypatch.setattr(train, "intervention_forward", lambda wrapper, batch:
                        wrapper.weight.expand(len(batch.counterfactual_labels), -1))
    path = tmp_path / "training_steps.jsonl"
    result = train.train_alignment(
        model, wrapper, pairs, None, None, "cpu", seed=42, location="N", output_path=path,
        epochs=2, batch_size=2, learning_rate=0.01, **factors)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert result["optimizer_steps"] == 4
    assert result["presentations"] == 8
    assert result["model_training_mode"] is False
    assert result["scheduler"]["step_interval"] == "batch"
    assert result["scheduler"]["total_iters"] == factors.get("schedule_total_iters", 10)
    assert [row["learning_rate_used"] for row in rows] == pytest.approx(expected_rates)
    assert rows[0]["sample_ids"] == ["sample-1", "sample-3"]
    assert all(row["gradient_norm"] > 0 for row in rows)
    assert all(parameter.grad is None for parameter in model.parameters())


def test_unknown_schedule_fails_before_training(tmp_path):
    with pytest.raises(ValueError, match="Unsupported schedule 'epoch'"):
        train.train_alignment(
            None, None, [], None, None, "cpu", seed=42, location="N",
            output_path=tmp_path / "steps.jsonl", epochs=1, batch_size=1,
            learning_rate=0.01, schedule="epoch")


@pytest.mark.parametrize("name, revision, options, diagnostic", [
    ("gpt2-medium", "pinned", {}, "requires name 'gpt2'"),
    ("gpt2", "", {}, "pinned revision"),
    ("gpt2", "pinned", {"local_files_only": False}, "existing cache"),
    ("gpt2", "pinned", {"dtype": "float16"}, "Unsupported model dtype"),
    ("gpt2", "pinned", {"attn_implementation": "sdpa"}, "Unsupported model dtype"),
])
def test_model_loader_rejects_unsupported_settings(name, revision, options, diagnostic):
    with pytest.raises(ValueError, match=diagnostic):
        load_model(name, revision, "cpu", **options)
