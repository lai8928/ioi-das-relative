"""DAS validation using real prompts, complete logits, and frozen model hashes."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
import hashlib
from typing import Any

from .checks import LONG_TEMPLATE, SHORT_TEMPLATE
from .data import PairRecord, build_prompt, counterfactual_names


def fingerprint_model(model: Any) -> str:
    """Hash every language-model parameter and buffer, including exact tensor bytes."""
    import torch

    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        descriptor = f"{name}\0{value.dtype}\0{tuple(value.shape)}\0"
        digest.update(descriptor.encode("utf-8"))
        digest.update(value.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def hook_snapshot(model: Any) -> dict[str, int]:
    """Record every active module hook so condition cleanup can preserve unrelated hooks."""
    snapshot = {}
    for name, module in model.named_modules():
        for kind in ("_forward_hooks", "_forward_pre_hooks", "_backward_hooks",
                     "_backward_pre_hooks"):
            count = len(getattr(module, kind, {}))
            if count:
                snapshot[f"{name or '<root>'}.{kind}"] = count
    return snapshot


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Phase 2 validation failed: {message}")


def _state_tensors(state: Mapping, prefix: str = "") -> dict[str, Any]:
    """Flatten alignment state dictionaries without including the language model."""
    import torch

    result = {}
    for key, value in state.items():
        name = f"{prefix}/{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            result.update(_state_tensors(value, name))
        elif isinstance(value, torch.Tensor):
            result[name] = value
    return result


def _logit_comparison(actual: Any, expected: Any, description: str,
                      atol: float = 1e-4, rtol: float = 1e-4) -> dict[str, Any]:
    import torch

    _require(actual.shape == expected.shape, f"{description}: logit shapes differ.")
    _require(bool(torch.isfinite(actual).all()) and bool(torch.isfinite(expected).all()),
             f"{description}: non-finite logits.")
    maximum = float((actual - expected).abs().max().item())
    matches = bool(torch.allclose(actual, expected, atol=atol, rtol=rtol))
    argmax_matches = bool(torch.equal(actual.argmax(-1), expected.argmax(-1)))
    _require(matches, f"{description}: full-vocabulary logits differ; "
             f"max absolute difference={maximum}, atol={atol}, rtol={rtol}.")
    _require(argmax_matches, f"{description}: next-token argmax differs.")
    return {
        "status": "passed", "full_vocabulary_shape": list(actual.shape),
        "max_absolute_difference": maximum, "atol": atol, "rtol": rtol,
        "argmax_matches": argmax_matches,
    }


def synthetic_unequal_pairs() -> list[PairRecord]:
    """Build the Phase 1 18/22-token validation prompts outside the saved research data."""
    short = build_prompt(("Alice", "Bob", "Bob"), SHORT_TEMPLATE, 0,
                         "ABB", "ring", "small local grocery store")
    long = build_prompt(("Bob", "Alice", "Bob"), LONG_TEMPLATE, 1,
                        "BAB", "ring", "small local grocery store")
    pairs = []
    for sample_id, base, source in (("synthetic-unequal", short, long),
                                    ("synthetic-reverse", long, short)):
        answer, distractor = counterfactual_names(base, source)
        pairs.append(PairRecord(sample_id, "synthetic", base, source, answer, distractor))
    return pairs


def _mixed_length_pairs(pairs: Sequence[PairRecord], tokenizer: Any) -> list[PairRecord]:
    _require(bool(pairs), "no original saved pairs supplied for validation.")
    lengths = [len(tokenizer.encode(pair.base.text, add_special_tokens=False))
               for pair in pairs]
    shortest = min(range(len(pairs)), key=lengths.__getitem__)
    longest = max(range(len(pairs)), key=lengths.__getitem__)
    _require(lengths[shortest] < lengths[longest],
             "original validation inputs must include at least two valid lengths.")
    selected = [pairs[shortest], pairs[longest]]
    for pair in pairs:
        if pair.base.pattern != selected[0].base.pattern and pair not in selected:
            selected.append(pair)
            break
    return selected


def _validate_batching(model: Any, intervenable: Any, pairs: Sequence[PairRecord],
                       tokenizer: Any, reference: Any, device: Any,
                       location: str) -> dict[str, Any]:
    import torch
    from .intervention import factual_forward, intervention_forward, prepare_batch

    batch = prepare_batch(pairs, tokenizer, reference, device, location=location)
    with torch.no_grad():
        factual_batch = factual_forward(model, batch)
        counterfactual_batch = intervention_forward(intervenable, batch)
        individual = [prepare_batch([pair], tokenizer, reference, device, location=location)
                      for pair in pairs]
        factual_individual = torch.cat([factual_forward(model, item) for item in individual])
        counterfactual_individual = torch.cat([
            intervention_forward(intervenable, item) for item in individual])
    base_lengths = batch.base_inputs["attention_mask"].sum(-1).tolist()
    source_lengths = batch.source_inputs["attention_mask"].sum(-1).tolist()
    readout = torch.as_tensor(batch.base_readout).tolist()
    _require(readout == [length - 1 for length in base_lengths],
             f"{location}: next-token readout must use each base N.")
    return {
        "status": "passed", "sample_ids": [pair.sample_id for pair in pairs],
        "intervention_location": location, "readout_location": "N",
        "base_lengths": base_lengths, "source_lengths": source_lengths,
        "base_positions": list(batch.base_positions),
        "source_positions": list(batch.source_positions), "base_readout": readout,
        "base_attention_mask": batch.base_inputs["attention_mask"].tolist(),
        "source_attention_mask": batch.source_inputs["attention_mask"].tolist(),
        "factual_logits": _logit_comparison(
            factual_batch, factual_individual, f"{location} factual batch/individual"),
        "intervened_logits": _logit_comparison(
            counterfactual_batch, counterfactual_individual,
            f"{location} intervened batch/individual"),
    }


def run_preflight_validation(model: Any, intervenable: Any,
                             pairs: Sequence[PairRecord], tokenizer: Any,
                             reference: Any, device: Any,
                             location: str = "N") -> dict[str, Any]:
    """Check gradients, identity, unequal lengths, readout, and cleanup before training."""
    import torch
    from .intervention import alignment_state, factual_forward, intervention_forward, prepare_batch

    _require(not any(parameter.requires_grad for parameter in model.parameters()),
             "language-model parameters must all be frozen before validation.")
    model.eval()
    initial_hash = fingerprint_model(model)
    initial_hooks = hook_snapshot(model)
    initial_alignment = _state_tensors(alignment_state(intervenable))
    selected = _mixed_length_pairs(pairs, tokenizer)
    batch = prepare_batch(selected, tokenizer, reference, device, location=location)
    parameters = list(intervenable.get_trainable_parameters())
    _require(bool(parameters) and all(parameter.requires_grad for parameter in parameters),
             "alignment parameters must be present and require gradients.")
    language_model_ids = {id(parameter) for parameter in model.parameters()}
    _require(not any(id(parameter) in language_model_ids for parameter in parameters),
             "optimizer parameter set includes language-model weights.")
    for parameter in parameters:
        parameter.grad = None
    try:
        logits = intervention_forward(intervenable, batch)
        loss = torch.nn.functional.cross_entropy(logits, batch.counterfactual_labels)
        _require(bool(torch.isfinite(loss)), "non-finite gradient-check loss.")
        loss.backward()
        gradients = [parameter.grad for parameter in parameters]
        _require(all(gradient is not None for gradient in gradients),
                 "one or more alignment parameters are disconnected from the loss.")
        _require(all(bool(torch.isfinite(gradient).all()) for gradient in gradients),
                 "alignment gradient contains non-finite values.")
        gradient_norm = sum(float(gradient.detach().double().square().sum().item())
                            for gradient in gradients) ** 0.5
        _require(gradient_norm > 0, "alignment gradient norm is zero.")
        _require(all(parameter.grad is None for parameter in model.parameters()),
                 "frozen language-model parameters received gradients.")
        gradient_result = {
            "status": "passed", "loss": float(loss.detach().item()),
            "alignment_gradient_norm": gradient_norm,
            "alignment_parameter_count": sum(parameter.numel() for parameter in parameters),
            "model_gradients_present": False, "optimizer_steps": 0,
        }
    finally:
        for parameter in parameters:
            parameter.grad = None

    identity_pairs = [replace(pair, source=pair.base,
                              counterfactual_answer=pair.base.io_name,
                              counterfactual_alternative=pair.base.subject_name)
                      for pair in selected]
    identity_batch = prepare_batch(identity_pairs, tokenizer, reference, device,
                                   location=location)
    with torch.no_grad():
        identity_result = _logit_comparison(
            intervention_forward(intervenable, identity_batch),
            factual_forward(model, identity_batch), "base-as-source identity intervention")
    identity_result["sample_ids"] = [pair.sample_id for pair in selected]
    identity_result["source_rule"] = "each base serves as its own source at identical positions"

    original_batching = _validate_batching(
        model, intervenable, selected, tokenizer, reference, device, location)
    synthetic_pairs = synthetic_unequal_pairs()
    synthetic_batching = {}
    for synthetic_location, base_expected, source_expected in (
            ("N", [17, 21], [21, 17]), ("N-2", [15, 19], [19, 15])):
        result = _validate_batching(model, intervenable, synthetic_pairs, tokenizer,
                                    reference, device, synthetic_location)
        _require(result["base_lengths"] == [18, 22] and
                 result["source_lengths"] == [22, 18],
                 "synthetic unequal lengths must remain exactly 18/22 and 22/18.")
        _require(result["base_positions"] == base_expected and
                 result["source_positions"] == source_expected and
                 result["base_readout"] == [17, 21],
                 f"synthetic {synthetic_location}: independent indices or base N readout differ.")
        _require(result["base_attention_mask"] == [[1] * 18 + [0] * 4, [1] * 22] and
                 result["source_attention_mask"] == [[1] * 22, [1] * 18 + [0] * 4],
                 "synthetic inputs lost separate base/source right-padding masks.")
        synthetic_batching[synthetic_location] = result

    _require(fingerprint_model(model) == initial_hash,
             "language-model tensor bytes changed during validation.")
    final_alignment = _state_tensors(alignment_state(intervenable))
    _require(initial_alignment.keys() == final_alignment.keys() and
             all(torch.equal(initial_alignment[name], final_alignment[name])
                 for name in initial_alignment),
             "alignment weights changed during preflight without an optimizer step.")
    final_hooks = hook_snapshot(model)
    _require(final_hooks == initial_hooks, "validation left intervention hooks attached.")
    return {
        "status": "passed", "model_sha256": initial_hash,
        "frozen_model_weights": True, "preflight_changes_alignment": False,
        "gradients": gradient_result, "identity_intervention": identity_result,
        "saved_data_mixed_length_batching": original_batching,
        "synthetic_unequal_length_batching": {
            "data_origin": "synthetic validation only; excluded from research dataset and metrics",
            "trained": False, "checks": synthetic_batching,
        },
        "hooks_before": initial_hooks, "hooks_after": final_hooks,
    }


def validate_after_training(model: Any, intervenable: Any, initial_model_hash: str,
                             initial_alignment: Mapping) -> dict[str, Any]:
    """Verify every model tensor is unchanged while finite alignment state has changed."""
    import torch
    from .intervention import alignment_state

    final_hash = fingerprint_model(model)
    _require(final_hash == initial_model_hash,
             "language-model SHA-256 differs after alignment training.")
    _require(not any(parameter.requires_grad for parameter in model.parameters()),
             "language-model weights became trainable.")
    _require(all(parameter.grad is None for parameter in model.parameters()),
             "language-model gradients exist after alignment training.")
    before = _state_tensors(initial_alignment)
    after = _state_tensors(alignment_state(intervenable))
    _require(bool(before) and before.keys() == after.keys(),
             "alignment state keys changed or alignment state is empty.")
    _require(all(bool(torch.isfinite(value).all()) for value in after.values()),
             "trained alignment state has non-finite values.")
    changed = [name for name in before if not torch.equal(before[name], after[name])]
    _require(bool(changed), "alignment state did not change during training.")
    return {
        "status": "passed", "model_sha256_before": initial_model_hash,
        "model_sha256_after": final_hash, "model_weights_bit_identical": True,
        "model_gradients_present": False, "alignment_finite": True,
        "alignment_changed": True, "changed_alignment_state_keys": changed,
    }
