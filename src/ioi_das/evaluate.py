"""Factual IOI accuracy, counterfactual IIA, and per-example next-token results.

Accuracy follows the upstream full-vocabulary argmax, with counts and without
rounding. Readout uses each base input's last valid token through the shared
forward functions. Upstream's ``kl_div`` is a target-logit mean rather than a
KL divergence; the corresponding quantity is named ``mean_target_logit`` here.
"""

from __future__ import annotations

from typing import Any, Sequence

from .data import PairRecord
from .intervention import factual_forward, intervention_forward, prepare_batch


def _prediction(tokenizer: Any, token_id: int) -> dict[str, Any]:
    """Keep the exact vocabulary token as well as its decoded continuation."""
    return {
        "token_id": token_id,
        "token": tokenizer.convert_ids_to_tokens(token_id),
        "continuation": tokenizer.decode([token_id]),
    }


def _group_metrics(predictions: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reduce intervention and no-intervention counts for every pairing group."""
    names = [f"{base}->{source}" for base in ("ABB", "BAB") for source in ("ABB", "BAB")]
    groups = {name: {"iia_correct": 0, "iia_total": 0,
                     "no_intervention_iia_correct": 0, "no_intervention_iia_total": 0}
              for name in (*names, "switch_required", "unchanged_target")}
    for row in predictions:
        pairing = f"{row['base_pattern']}->{row['source_pattern']}"
        target_group = "switch_required" if row["switch_required"] else "unchanged_target"
        for name in (pairing, target_group):
            group = groups[name]
            group["iia_correct"] += int(row["counterfactual_correct"])
            group["iia_total"] += 1
            group["no_intervention_iia_correct"] += int(row["no_intervention_correct"])
            group["no_intervention_iia_total"] += 1
    for group in groups.values():
        count = group["iia_total"]
        group["iia"] = group["iia_correct"] / count if count else None
        group["no_intervention_iia"] = group["no_intervention_iia_correct"] / count if count else None
    return groups


def evaluate_condition(
    model: Any,
    intervenable: Any,
    pairs: Sequence[PairRecord],
    tokenizer: Any,
    reference: Any,
    device: Any,
    batch_size: int = 20,
    location: str = "N",
    split: str = "test",
) -> dict[str, Any]:
    """Evaluate every saved pair with factual and intervened full-vocabulary logits.

    Single-token labels are checked by ``prepare_batch`` before a forward call.
    Unsupported continuations fail with their sample diagnostics instead of
    being truncated or silently excluded from the accuracy denominator.
    ``no_grad`` applies only to this evaluation, leaving training gradient flow
    untouched. Base and source positions and masks are independent.
    """
    import torch
    import torch.nn.functional as functional

    pairs = tuple(pairs)
    if not pairs:
        raise ValueError("Cannot evaluate an empty dataset.")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("Evaluation batch_size must be a positive integer.")
    if len({pair.sample_id for pair in pairs}) != len(pairs):
        raise ValueError("Evaluation requires unique sample IDs.")
    mismatches = [pair.sample_id for pair in pairs if pair.split != split]
    if mismatches:
        raise ValueError(f"Evaluation split {split!r} does not match samples {mismatches!r}.")

    model.eval()
    intervenable.eval()
    predictions = []
    factual_correct = 0
    iia_correct = 0
    no_intervention_iia_correct = 0
    with torch.no_grad():
        for start in range(0, len(pairs), batch_size):
            batch = prepare_batch(pairs[start:start + batch_size], tokenizer,
                                  reference, device, location=location)
            factual_logits = factual_forward(model, batch).float()
            counterfactual_logits = intervention_forward(intervenable, batch).float()
            expected_rows = len(batch.pairs)
            for name, logits in (("factual", factual_logits),
                                 ("counterfactual", counterfactual_logits)):
                if logits.ndim != 2 or logits.shape[0] != expected_rows:
                    raise ValueError(f"{name} readout logits must have shape (batch, vocabulary).")
                if not torch.isfinite(logits).all().item():
                    identifiers = [pair.sample_id for pair in batch.pairs]
                    raise ValueError(f"{identifiers}: {name} readout logits contain nonfinite values.")

            rows = torch.arange(expected_rows, device=batch.factual_labels.device)
            factual_ids = factual_logits.argmax(dim=-1)
            counterfactual_ids = counterfactual_logits.argmax(dim=-1)
            factual_ok = factual_ids.eq(batch.factual_labels)
            counterfactual_ok = counterfactual_ids.eq(batch.counterfactual_labels)
            no_intervention_ok = factual_ids.eq(batch.counterfactual_labels)
            factual_correct += int(factual_ok.sum().item())
            iia_correct += int(counterfactual_ok.sum().item())
            no_intervention_iia_correct += int(no_intervention_ok.sum().item())
            factual_log_probabilities = factual_logits.log_softmax(dim=-1)
            counterfactual_log_probabilities = counterfactual_logits.log_softmax(dim=-1)
            factual_losses = functional.cross_entropy(
                factual_logits, batch.factual_labels, reduction="none").cpu().tolist()
            counterfactual_losses = functional.cross_entropy(
                counterfactual_logits, batch.counterfactual_labels, reduction="none").cpu().tolist()
            factual_target_logits = factual_logits[rows, batch.factual_labels].cpu().tolist()
            target_logits = counterfactual_logits[rows, batch.counterfactual_labels].cpu().tolist()
            factual_target_probs = factual_log_probabilities[
                rows, batch.factual_labels].exp().cpu().tolist()
            target_probs = counterfactual_log_probabilities[
                rows, batch.counterfactual_labels].exp().cpu().tolist()
            factual_pred_probs = factual_log_probabilities[rows, factual_ids].exp().cpu().tolist()
            counterfactual_pred_probs = counterfactual_log_probabilities[
                rows, counterfactual_ids].exp().cpu().tolist()
            factual_ids = factual_ids.cpu().tolist()
            counterfactual_ids = counterfactual_ids.cpu().tolist()
            factual_labels = batch.factual_labels.cpu().tolist()
            counterfactual_labels = batch.counterfactual_labels.cpu().tolist()
            factual_ok = factual_ok.cpu().tolist()
            counterfactual_ok = counterfactual_ok.cpu().tolist()
            no_intervention_ok = no_intervention_ok.cpu().tolist()
            base_lengths = batch.base_inputs["attention_mask"].sum(dim=-1).cpu().tolist()
            source_lengths = batch.source_inputs["attention_mask"].sum(dim=-1).cpu().tolist()
            readout_positions = batch.base_readout.cpu().tolist()

            for index, pair in enumerate(batch.pairs):
                predictions.append({
                    "sample_id": pair.sample_id,
                    "split": pair.split,
                    "target_variable": pair.target_variable,
                    "intervention_location": location,
                    "readout_location": "N",
                    "base_text": pair.base.text,
                    "source_text": pair.source.text,
                    "base_pattern": pair.base.pattern,
                    "source_pattern": pair.source.pattern,
                    "base_io_name": pair.base.io_name,
                    "base_subject_name": pair.base.subject_name,
                    "source_io_name": pair.source.io_name,
                    "source_subject_name": pair.source.subject_name,
                    "base_valid_length": int(base_lengths[index]),
                    "source_valid_length": int(source_lengths[index]),
                    "base_position": int(batch.base_positions[index]),
                    "source_position": int(batch.source_positions[index]),
                    "base_readout_position": int(readout_positions[index]),
                    "factual_target_name": pair.base.io_name,
                    "factual_target_token_id": factual_labels[index],
                    "factual_prediction": _prediction(tokenizer, factual_ids[index]),
                    "factual_correct": factual_ok[index],
                    "no_intervention_correct": no_intervention_ok[index],
                    "switch_required": pair.counterfactual_answer != pair.base.io_name,
                    "factual_target_logit": factual_target_logits[index],
                    "factual_target_probability": factual_target_probs[index],
                    "factual_prediction_probability": factual_pred_probs[index],
                    "factual_loss": factual_losses[index],
                    "counterfactual_target_name": pair.counterfactual_answer,
                    "counterfactual_alternative_name": pair.counterfactual_alternative,
                    "counterfactual_target_token_id": counterfactual_labels[index],
                    "counterfactual_prediction": _prediction(tokenizer, counterfactual_ids[index]),
                    "counterfactual_correct": counterfactual_ok[index],
                    "counterfactual_target_logit": target_logits[index],
                    "counterfactual_target_probability": target_probs[index],
                    "counterfactual_prediction_probability": counterfactual_pred_probs[index],
                    "counterfactual_loss": counterfactual_losses[index],
                })

    # Reduce saved per-example values in Python float precision, weighting every
    # example equally even when the final batch is smaller than batch_size.
    count = len(predictions)
    metrics = {
        "factual_correct": factual_correct,
        "factual_total": count,
        "factual_accuracy": factual_correct / count,
        "iia_correct": iia_correct,
        "iia_total": count,
        "iia": iia_correct / count,
        "no_intervention_iia_correct": no_intervention_iia_correct,
        "no_intervention_iia_total": count,
        "no_intervention_iia": no_intervention_iia_correct / count,
        "groups": _group_metrics(predictions),
        "mean_factual_loss": sum(row["factual_loss"] for row in predictions) / count,
        "mean_counterfactual_loss": sum(row["counterfactual_loss"] for row in predictions) / count,
        "mean_target_logit": sum(row["counterfactual_target_logit"] for row in predictions) / count,
        "prediction_rule": "argmax_full_vocabulary",
    }
    return {"metrics": metrics, "predictions": predictions}
