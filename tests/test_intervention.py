"""Intervention contracts with a tiny random GPT-2 and the pinned tokenizer.

The random model is only a correctness fixture. These checks are not the
configured pretrained-GPT-2 DAS experiment and provide no research metrics.
"""

from dataclasses import replace
import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch", reason="Intervention checks require the DAS runtime")
pytest.importorskip("pyvene", reason="Intervention checks require the external pyvene dependency")
from transformers import GPT2Config, GPT2LMHeadModel

from ioi_das.data import PairRecord, build_prompt, load_pairs
from ioi_das.checks import SHORT_TEMPLATE
from ioi_das.intervention import (
    alignment_state, build_intervention, cleanup_intervention,
    intervention_forward, prepare_batch,
)
from ioi_das.tokenization import load_tokenizers
from ioi_das.validation import (
    fingerprint_model, hook_snapshot, run_preflight_validation,
    synthetic_unequal_pairs, validate_after_training,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def intervention_inputs():
    config = json.loads((PROJECT_ROOT / "configs/base.json").read_text())
    tokenizer, reference = load_tokenizers(config["tokenizer"])
    pairs = load_pairs(PROJECT_ROOT / "data/generated/train.jsonl")
    return tokenizer, reference, pairs


@pytest.fixture
def tiny_intervention(intervention_inputs):
    tokenizer, _, _ = intervention_inputs
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(17)
        config = GPT2Config(
            vocab_size=tokenizer.vocab_size, n_positions=32, n_ctx=32,
            n_embd=16, n_layer=9, n_head=2,
            resid_pdrop=0, embd_pdrop=0, attn_pdrop=0,
            use_cache=False, pad_token_id=tokenizer.pad_token_id,
        )
        config._attn_implementation = "eager"
        model = GPT2LMHeadModel(config)
        wrapper = build_intervention(model, layer=8, rank=1)
    yield model, wrapper
    cleanup_intervention(wrapper)


def test_real_tokenizer_frozen_gradients_identity_and_mixed_batching(
        intervention_inputs, tiny_intervention):
    tokenizer, reference, pairs = intervention_inputs
    model, wrapper = tiny_intervention
    initial_hash = fingerprint_model(model)
    initial_alignment = alignment_state(wrapper)

    result = run_preflight_validation(model, wrapper, pairs, tokenizer, reference, "cpu")
    assert result["status"] == "passed"
    assert result["gradients"]["alignment_gradient_norm"] > 0
    assert result["identity_intervention"]["max_absolute_difference"] == 0
    assert result["hooks_before"] == result["hooks_after"] == {}
    synthetic = result["synthetic_unequal_length_batching"]["checks"]
    assert synthetic["N"]["base_positions"] == [17, 21]
    assert synthetic["N"]["source_positions"] == [21, 17]
    assert synthetic["N-2"]["base_positions"] == [15, 19]
    assert synthetic["N-2"]["source_positions"] == [19, 15]
    assert synthetic["N-2"]["base_readout"] == [17, 21]
    assert fingerprint_model(model) == initial_hash
    assert all(parameter.grad is None for parameter in wrapper.get_trainable_parameters())
    with pytest.raises(ValueError, match="alignment state did not change"):
        validate_after_training(model, wrapper, initial_hash, initial_alignment)

    # One fixture-only optimizer step verifies that the frozen model can learn
    # an alignment; the full pretrained experiment is executed by the CLI.
    batch = prepare_batch(pairs[50:52], tokenizer, reference, "cpu")
    optimizer = torch.optim.Adam(wrapper.get_trainable_parameters(), lr=1e-3)
    loss = torch.nn.functional.cross_entropy(
        intervention_forward(wrapper, batch), batch.counterfactual_labels)
    loss.backward()
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    postflight = validate_after_training(model, wrapper, initial_hash, initial_alignment)
    assert postflight["alignment_changed"]
    assert postflight["model_weights_bit_identical"]

    # A frozen flag alone cannot prove that weights stayed unchanged: a direct
    # in-place mutation must still be detected by the complete model hash.
    parameter = next(model.parameters())
    original = parameter.detach().clone()
    try:
        with torch.no_grad():
            parameter.view(-1)[0].add_(0.125)
        with pytest.raises(ValueError, match="language-model SHA-256 differs"):
            validate_after_training(model, wrapper, initial_hash, initial_alignment)
    finally:
        with torch.no_grad():
            parameter.copy_(original)
    cleanup_intervention(wrapper)
    assert hook_snapshot(model) == {}


def test_hook_cleanup_preserves_unrelated_hooks_even_after_failure(
        intervention_inputs, tiny_intervention):
    tokenizer, reference, _ = intervention_inputs
    model, wrapper = tiny_intervention
    observed = []
    sentinel = model.transformer.h[8].register_forward_hook(
        lambda module, inputs, output: observed.append(True))
    try:
        baseline_hooks = hook_snapshot(model)
        batch = prepare_batch(synthetic_unequal_pairs(), tokenizer, reference, "cpu")
        intervention_forward(wrapper, batch)
        assert observed
        assert hook_snapshot(model) == baseline_hooks
        invalid = replace(batch, base_positions=[1000, 1000])
        with pytest.raises((IndexError, RuntimeError)):
            intervention_forward(wrapper, invalid)
        cleanup_intervention(wrapper)
        assert hook_snapshot(model) == baseline_hooks
        assert not wrapper.activations
        assert not wrapper.full_intervention_outputs
    finally:
        sentinel.remove()
    assert hook_snapshot(model) == {}


def test_prepare_batch_preserves_and_reports_multi_token_answer(intervention_inputs):
    tokenizer, reference, _ = intervention_inputs
    prompt = build_prompt(("Mary Jane", "Bob", "Bob"), SHORT_TEMPLATE,
                          0, "ABB", "ring", "store")
    pair = PairRecord("synthetic-multi-token", "synthetic", prompt, prompt,
                      "Mary Jane", "Bob")
    with pytest.raises(ValueError, match=r"synthetic-multi-token/base.*2 continuation tokens"):
        prepare_batch([pair], tokenizer, reference, "cpu")
    assert pair.base.text == prompt.text
    assert pair.counterfactual_answer == "Mary Jane"


def test_evaluation_full_vocabulary_argmax_counts_and_sample_weighted_losses(
        intervention_inputs, monkeypatch):
    from ioi_das import evaluate

    tokenizer, reference, all_pairs = intervention_inputs
    pairs = all_pairs[:3]
    sample_index = {pair.sample_id: index for index, pair in enumerate(pairs)}
    target_logit = [1.0, 3.0, 7.0]

    class EvaluationOnlyModel:
        def eval(self):
            return self

    def logits_for(batch, counterfactual):
        labels = batch.counterfactual_labels if counterfactual else batch.factual_labels
        logits = torch.zeros((len(batch.pairs), tokenizer.vocab_size))
        for row, pair in enumerate(batch.pairs):
            index = sample_index[pair.sample_id]
            label = int(labels[row])
            assert label != 0  # Token zero is punctuation, outside the two names.
            logits[row, label] = target_logit[index]
            wrong = index == (0 if counterfactual else 1)
            if wrong:
                logits[row, 0] = target_logit[index] + 2
        return logits

    monkeypatch.setattr(evaluate, "factual_forward", lambda model, batch: logits_for(batch, False))
    monkeypatch.setattr(evaluate, "intervention_forward", lambda wrapper, batch: logits_for(batch, True))
    model = EvaluationOnlyModel()
    result = evaluate.evaluate_condition(model, model, pairs, tokenizer, reference,
                                         "cpu", batch_size=2, split="train")
    metrics = result["metrics"]
    predictions = result["predictions"]
    assert metrics["prediction_rule"] == "argmax_full_vocabulary"
    assert (metrics["factual_correct"], metrics["factual_total"]) == (2, 3)
    assert (metrics["iia_correct"], metrics["iia_total"]) == (2, 3)
    assert metrics["factual_accuracy"] == metrics["iia"] == 2 / 3
    assert (metrics["no_intervention_iia_correct"], metrics["no_intervention_iia_total"]) == (2, 3)
    assert metrics["no_intervention_iia"] == 2 / 3
    assert metrics["groups"]["ABB->ABB"]["iia_total"] == 3
    for name in ("ABB->BAB", "BAB->ABB", "BAB->BAB", "switch_required"):
        assert metrics["groups"][name] == {
            "iia_correct": 0, "iia_total": 0, "iia": None,
            "no_intervention_iia_correct": 0, "no_intervention_iia_total": 0,
            "no_intervention_iia": None,
        }
    assert predictions[0]["counterfactual_prediction"] == {
        "token_id": 0, "token": tokenizer.convert_ids_to_tokens(0),
        "continuation": tokenizer.decode([0]),
    }
    assert metrics["mean_target_logit"] == sum(target_logit) / 3
    assert metrics["mean_counterfactual_loss"] == sum(
        row["counterfactual_loss"] for row in predictions) / 3
    assert [row["sample_id"] for row in predictions] == [pair.sample_id for pair in pairs]
    assert all(row["base_readout_position"] == row["base_valid_length"] - 1
               for row in predictions)


def test_evaluation_groups_score_factual_predictions_against_counterfactual_targets(
        intervention_inputs, monkeypatch):
    from ioi_das import evaluate

    tokenizer, reference, all_pairs = intervention_inputs
    pairs = tuple(all_pairs[index] for index in (0, 50, 100, 150))
    sample_index = {pair.sample_id: index for index, pair in enumerate(pairs)}

    class EvaluationOnlyModel:
        def eval(self):
            return self

    def factual_logits(batch):
        logits = torch.zeros((len(batch.pairs), tokenizer.vocab_size))
        for row, pair in enumerate(batch.pairs):
            index = sample_index[pair.sample_id]
            # A factual error can still be correct against a changed target.
            target = batch.counterfactual_labels[row] if index == 1 else batch.factual_labels[row]
            prediction = 0 if index == 3 else int(target)
            logits[row, prediction] = 5
        return logits

    def intervention_logits(batch):
        logits = torch.zeros((len(batch.pairs), tokenizer.vocab_size))
        for row, pair in enumerate(batch.pairs):
            index = sample_index[pair.sample_id]
            prediction = int(batch.counterfactual_labels[row]) if index in (1, 3) else 0
            logits[row, prediction] = 5
        return logits

    monkeypatch.setattr(evaluate, "factual_forward", lambda model, batch: factual_logits(batch))
    monkeypatch.setattr(evaluate, "intervention_forward", lambda model, batch: intervention_logits(batch))
    model = EvaluationOnlyModel()
    rng_before = torch.random.get_rng_state()
    result = evaluate.evaluate_condition(model, model, pairs, tokenizer, reference,
                                         "cpu", batch_size=3, split="train")
    assert torch.equal(rng_before, torch.random.get_rng_state())
    metrics = result["metrics"]
    assert metrics["factual_correct"] == metrics["iia_correct"] == 2
    assert metrics["no_intervention_iia_correct"] == 2
    assert metrics["no_intervention_iia_total"] == 4
    assert metrics["no_intervention_iia"] == 0.5
    assert [row["no_intervention_correct"] for row in result["predictions"]] == [True, True, False, False]
    assert [row["switch_required"] for row in result["predictions"]] == [False, True, True, False]
    expected = {"ABB->ABB": (0, 1, 1), "ABB->BAB": (1, 1, 1),
                "BAB->ABB": (0, 0, 1), "BAB->BAB": (1, 0, 1),
                "switch_required": (1, 1, 2), "unchanged_target": (1, 1, 2)}
    for name, (correct, no_intervention_correct, total) in expected.items():
        assert metrics["groups"][name] == {
            "iia_correct": correct, "iia_total": total, "iia": correct / total,
            "no_intervention_iia_correct": no_intervention_correct,
            "no_intervention_iia_total": total,
            "no_intervention_iia": no_intervention_correct / total,
        }
