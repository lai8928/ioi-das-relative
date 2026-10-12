"""Optimize only alignment parameters with the pinned tutorial's Adam schedule."""

import json
import time

import numpy as np
import torch
from torch.nn import functional as F

from .intervention import intervention_forward, prepare_batch


def train_alignment(model, intervenable, pairs, tokenizer, reference, device,
                    training_config: dict, seed: int, location: str, output_path,
                    smoke: bool = False) -> dict:
    """Preserve per-batch LinearLR steps and eval-mode language-model dropout.

    No test data is consulted during optimization. Preflight backward checks
    do not consume the independent MT19937 batch-shuffle RNG used here.
    """
    model.eval()
    parameters = list(intervenable.get_trainable_parameters())
    if not parameters or any(not parameter.requires_grad for parameter in parameters):
        raise ValueError("Expected trainable alignment parameters.")
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise ValueError("Language-model parameters must be frozen before training.")
    optimizer = torch.optim.Adam(parameters, lr=training_config["learning_rate"],
                                 betas=tuple(training_config["betas"]), eps=training_config["eps"],
                                 weight_decay=training_config["weight_decay"])
    schedule = training_config["scheduler"]
    scheduler = torch.optim.lr_scheduler.LinearLR(
        optimizer, start_factor=schedule["start_factor"], end_factor=schedule["end_factor"],
        total_iters=schedule["total_iters"])
    rng = np.random.RandomState(seed)
    epochs = 1 if smoke else training_config["epochs"]
    batch_size = training_config["batch_size"]
    steps, epoch_records = [], []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for epoch in range(epochs):
            order = rng.permutation(len(pairs))
            total_loss, correct, seen = 0.0, 0, 0
            for start in range(0, len(order), batch_size):
                chosen = [pairs[int(index)] for index in order[start:start + batch_size]]
                batch = prepare_batch(chosen, tokenizer, reference, device, location)
                optimizer.zero_grad(set_to_none=True)
                used_lr = optimizer.param_groups[0]["lr"]
                began = time.perf_counter()
                logits = intervention_forward(intervenable, batch)
                loss = F.cross_entropy(logits, batch.counterfactual_labels)
                if not torch.isfinite(loss):
                    raise RuntimeError(f"Nonfinite loss in epoch {epoch + 1}, batch starting at {start}.")
                loss.backward()
                gradients = [parameter.grad for parameter in parameters if parameter.grad is not None]
                if not gradients or any(not torch.isfinite(gradient).all() for gradient in gradients):
                    raise RuntimeError("Alignment gradients are absent or nonfinite.")
                if any(parameter.grad is not None for parameter in model.parameters()):
                    raise RuntimeError("Frozen language-model parameters unexpectedly received gradients.")
                gradient_norm = sum(gradient.detach().float().pow(2).sum().item() for gradient in gradients) ** 0.5
                batch_correct = int((logits.detach().argmax(-1) == batch.counterfactual_labels).sum().item())
                optimizer.step()
                # Upstream steps LinearLR every batch with total_iters=n_epochs.
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                record = {
                    "step": len(steps) + 1, "epoch": epoch + 1,
                    "batch": start // batch_size + 1,
                    "sample_ids": [pair.sample_id for pair in chosen],
                    "loss": loss.item(), "correct": batch_correct, "total": len(chosen),
                    "accuracy": batch_correct / len(chosen),
                    "learning_rate_used": used_lr,
                    "learning_rate_next": optimizer.param_groups[0]["lr"],
                    "gradient_norm": gradient_norm,
                    "elapsed_seconds": time.perf_counter() - began,
                }
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                steps.append(record)
                total_loss += record["loss"] * len(chosen)
                correct += batch_correct
                seen += len(chosen)
            epoch_record = {"epoch": epoch + 1, "mean_loss": total_loss / seen,
                            "correct": correct, "total": seen, "accuracy": correct / seen}
            epoch_records.append(epoch_record)
            print(f"Epoch {epoch + 1}/{epochs}: mean_loss={epoch_record['mean_loss']:.6f}, "
                  f"train IIA={correct}/{seen}, lr={optimizer.param_groups[0]['lr']:.6g}", flush=True)
    return {
        "run_kind": "smoke" if smoke else "full", "epochs": epochs,
        "optimizer_steps": len(steps), "training_pair_count": len(pairs),
        "presentations": sum(record["total"] for record in steps),
        "optimizer": "Adam", "scheduler": schedule,
        "initial_effective_learning_rate": steps[0]["learning_rate_used"],
        "final_learning_rate": optimizer.param_groups[0]["lr"],
        "first_step_loss": steps[0]["loss"], "last_step_loss": steps[-1]["loss"],
        "epoch_results": epoch_records,
        "shuffle": "NumPy RandomState(seed), MT19937; same permutation algorithm as upstream",
        "model_training_mode": model.training,
    }
