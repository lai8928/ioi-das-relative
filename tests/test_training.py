"""Check explicit training options without loading pretrained model weights."""

import json
from types import SimpleNamespace

import pytest


torch = pytest.importorskip("torch", reason="Training checks require torch")
pytest.importorskip("pyvene", reason="Intervention checks require pyvene")

from ioi_das import train
from ioi_das import intervention
from ioi_das.intervention import load_model


PINNED_REVISION = "a" * 40


class TrainableAlignment(torch.nn.Module):
    """Supply one trainable two-class alignment for optimizer checks."""

    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.tensor([1.0, -1.0]))

    def get_trainable_parameters(self):
        return [self.weight]


@pytest.fixture
def train_cpu(monkeypatch, tmp_path):
    """Run optimizer checks with five sample labels and no pretrained weights."""
    monkeypatch.setattr(train, "prepare_batch", lambda chosen, *args: SimpleNamespace(
        counterfactual_labels=torch.tensor([int(pair.sample_id.split("-")[-1]) % 2 for pair in chosen])))
    monkeypatch.setattr(train, "intervention_forward", lambda wrapper, batch:
                        wrapper.weight.expand(len(batch.counterfactual_labels), -1))
    calls = []

    def run(*, pair_count=5, batch_size=2, **budget):
        model = torch.nn.Linear(1, 1)
        model.requires_grad_(False)
        wrapper = TrainableAlignment()
        pairs = [SimpleNamespace(sample_id=f"sample-{index}") for index in range(pair_count)]
        path = tmp_path / f"steps-{len(calls)}.jsonl"
        calls.append(path)
        result = train.train_alignment(
            model, wrapper, pairs, None, None, "cpu", seed=42, location="N",
            output_path=path, batch_size=batch_size, learning_rate=0.01, **budget)
        return result, [json.loads(line) for line in path.read_text().splitlines()]

    return run


def test_epoch_budget_preserves_recorded_legacy_summary_and_shuffle(train_cpu):
    result, rows = train_cpu(epochs=3)
    assert result == {
        "run_kind": "full", "epochs": 3, "optimizer_steps": 9, "training_pair_count": 5,
        "presentations": 15, "optimizer": "Adam",
        "scheduler": {"name": "LinearLR", "start_factor": 1 / 3, "end_factor": 0.1,
                      "total_iters": 10, "step_interval": "batch"},
        "initial_effective_learning_rate": 0.003333333333333333,
        "final_learning_rate": 0.0012333333333333335,
        "first_step_loss": 1.1269280910491943, "last_step_loss": 0.13020934164524078,
        "epoch_results": [
            {"epoch": 1, "mean_loss": 0.9256195485591888, "correct": 3, "total": 5, "accuracy": 0.6},
            {"epoch": 2, "mean_loss": 0.9235813677310943, "correct": 3, "total": 5, "accuracy": 0.6},
            {"epoch": 3, "mean_loss": 0.9202864915132523, "correct": 3, "total": 5, "accuracy": 0.6}],
        "shuffle": "NumPy RandomState(seed), MT19937; same permutation algorithm as upstream",
        "model_training_mode": False,
    }
    assert [row["sample_ids"] for row in rows] == [
        ["sample-1", "sample-4"], ["sample-2", "sample-0"], ["sample-3"],
        ["sample-3", "sample-1"], ["sample-2", "sample-0"], ["sample-4"],
        ["sample-1", "sample-0"], ["sample-3", "sample-4"], ["sample-2"]]


@pytest.mark.parametrize("updates, presentations, passes, last_pass_count", [
    (1, 2, 1, 2), (3, 5, 1, 5), (4, 7, 2, 2), (7, 12, 3, 2), (9, 15, 3, 5),
])
def test_update_budget_matches_epoch_trace_through_its_exact_last_update(
        train_cpu, updates, presentations, passes, last_pass_count):
    reference, reference_rows = train_cpu(epochs=3)
    result, rows = train_cpu(max_updates=updates)
    strip_timing = lambda records: [{key: value for key, value in row.items() if key != "elapsed_seconds"}
                                    for row in records]
    assert strip_timing(rows) == strip_timing(reference_rows[:updates])
    assert result["max_updates"] == result["optimizer_steps"] == updates
    assert result["presentations"] == presentations
    assert result["epochs"] == len(result["epoch_results"]) == passes
    assert result["epoch_results"][-1]["total"] == last_pass_count
    assert result["scheduler"] == reference["scheduler"]
    assert result["final_learning_rate"] == rows[-1]["learning_rate_next"]


@pytest.mark.parametrize("budget, expected_steps, expected_presentations", [
    ({"epochs": 10}, 3, 5), ({"max_updates": 100}, 3, 5), ({"max_updates": 1}, 1, 2),
])
def test_smoke_budget_stops_in_the_first_shuffled_pass(
        train_cpu, budget, expected_steps, expected_presentations):
    result, rows = train_cpu(smoke=True, **budget)
    assert result["run_kind"] == "smoke"
    assert result["epochs"] == 1
    assert result["optimizer_steps"] == expected_steps
    assert result["presentations"] == expected_presentations
    assert {row["epoch"] for row in rows} == {1}


@pytest.mark.parametrize("budget", [{"epochs": 10}, {"max_updates": 1000}])
def test_balanced_twenty_pair_smoke_performs_one_update(train_cpu, budget):
    result, rows = train_cpu(pair_count=20, batch_size=20, smoke=True, **budget)
    assert result["optimizer_steps"] == len(rows) == 1
    assert result["presentations"] == 20


@pytest.mark.parametrize("budget", [{}, {"epochs": 1, "max_updates": 2}])
def test_training_requires_exactly_one_budget_before_any_model_work(tmp_path, budget):
    with pytest.raises(ValueError, match="exactly one of epochs or max_updates"):
        train.train_alignment(
            None, None, [object()], None, None, "cpu", seed=42, location="N",
            output_path=tmp_path / "steps.jsonl", batch_size=2, learning_rate=0.01, **budget)
    assert not (tmp_path / "steps.jsonl").exists()


@pytest.mark.parametrize("name", ["epochs", "max_updates", "batch_size"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "2"])
def test_training_rejects_nonpositive_or_noninteger_budget_options(tmp_path, name, value):
    options = {"epochs": 1, "batch_size": 2}
    if name == "max_updates":
        options.pop("epochs")
    options[name] = value
    with pytest.raises(ValueError, match=f"{name} must be a positive integer"):
        train.train_alignment(
            None, None, [object()], None, None, "cpu", seed=42, location="N",
            output_path=tmp_path / "steps.jsonl", learning_rate=0.01, **options)
    assert not (tmp_path / "steps.jsonl").exists()


def test_training_rejects_missing_batch_size_value(tmp_path):
    with pytest.raises(ValueError, match="batch_size must be a positive integer"):
        train.train_alignment(
            None, None, [object()], None, None, "cpu", seed=42, location="N",
            output_path=tmp_path / "steps.jsonl", epochs=1, batch_size=None, learning_rate=0.01)


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
    ("bert-base-uncased", PINNED_REVISION, {}, "GPT-2"),
    ("gpt2", "", {}, "pinned revision"),
    ("gpt2", "pinned", {}, "pinned revision"),
    ("gpt2", PINNED_REVISION, {"local_files_only": False}, "existing cache"),
    ("gpt2", PINNED_REVISION, {"dtype": "float16"}, "Unsupported model dtype"),
    ("gpt2", PINNED_REVISION, {"attn_implementation": "sdpa"}, "Unsupported model dtype"),
])
def test_model_loader_rejects_unsupported_settings(name, revision, options, diagnostic):
    with pytest.raises(ValueError, match=diagnostic):
        load_model(name, revision, "cpu", **options)


@pytest.mark.parametrize("family", ["gpt2", "gpt2-medium", "gpt2-large", "gpt2-xl"])
@pytest.mark.parametrize("prefix", ["", "openai-community/"])
def test_model_loader_accepts_pinned_family_without_downloading(monkeypatch, family, prefix):
    import transformers

    name = prefix + family
    model = torch.nn.Linear(1, 1)
    model.config = SimpleNamespace(eos_token_id=50256, use_cache=True, pad_token_id=None)
    for parameter in model.parameters():
        parameter.grad = torch.ones_like(parameter)
    calls, cache_calls = [], []

    def cached(*args, **kwargs):
        cache_calls.append((args, kwargs))
        return {}

    def pretrained(*args, **kwargs):
        calls.append((args, kwargs))
        return model

    monkeypatch.setattr(intervention, "require_cached_model", cached)
    monkeypatch.setattr(transformers.GPT2LMHeadModel, "from_pretrained", pretrained)
    loaded = load_model(name, PINNED_REVISION, "cpu")
    assert loaded is model
    assert cache_calls == [((name, PINNED_REVISION), {"include_tokenizer": False})]
    assert calls == [((name,), {"revision": PINNED_REVISION, "local_files_only": True,
                              "use_safetensors": True, "dtype": torch.float32,
                              "attn_implementation": "eager"})]
    assert model.config.use_cache is False
    assert model.config.pad_token_id == model.config.eos_token_id
    assert model.training is False
    assert all(not parameter.requires_grad and parameter.grad is None
               for parameter in model.parameters())
