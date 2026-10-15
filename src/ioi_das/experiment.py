"""Train and evaluate an independent DAS condition with explicit runtime inputs."""

from collections import defaultdict
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import gc
from typing import Any, Iterator
import json
from pathlib import Path
import time

from .audit import runtime_environment, write_json
from .data import sha256_file
from .tokenization import load_tokenizers


def _write_predictions(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _balanced_subset(pairs, count_per_pairing: int):
    buckets = defaultdict(list)
    selected = []
    for pair in pairs:
        key = pair.base.pattern, pair.source.pattern
        if len(buckets[key]) < count_per_pairing:
            buckets[key].append(pair)
            selected.append(pair)
    return selected


def run_condition(
    output: Path, pairs: dict, *, model_options: dict, tokenizer_options: dict,
    training_options: dict, layer: int, rank: int, component: str,
    target_variable: str, location: str, seed: int, device_name: str,
    cpu_threads: int, evaluation_batch_size: int, dataset_metadata: dict,
    provenance: dict, config_sha256: str, evaluation_splits: tuple[str, ...],
    smoke: bool = False,
) -> dict[str, Any]:
    """Save one freshly initialized alignment and all exact evaluation evidence."""
    import torch
    from transformers import set_seed
    from transformers.utils.hub import cached_file

    from .evaluate import evaluate_condition
    from .intervention import (alignment_state, build_intervention, cleanup_intervention,
                               intervention_forward, load_model, prepare_batch)
    from .train import train_alignment
    from .validation import hook_snapshot, run_preflight_validation, validate_after_training

    kind = "smoke" if smoke else "full"
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Condition directory is not empty: {output}; preserve it and resume only missing conditions.")
    original_counts = {split: len(records) for split, records in pairs.items()}
    if smoke:
        pairs = {split: _balanced_subset(records, 5 if split == "train" else 2)
                 for split, records in pairs.items()}
    torch.set_num_threads(cpu_threads)
    torch.set_float32_matmul_precision("highest")
    device = torch.device(device_name)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("The configured run requires a server CUDA device. "
                           "Run outside a GPU-restricted sandbox; no CPU fallback is performed.")
    # Initialize the allocator before resetting its statistics (torch 2.5.1).
    torch.cuda.set_device(device)
    torch.cuda.reset_peak_memory_stats(device)
    output.mkdir(parents=True, exist_ok=True)

    model, intervenable = None, None
    validation = {}
    started = time.perf_counter()
    try:
        tokenizer, reference = load_tokenizers(tokenizer_options)
        environment = runtime_environment({"tokenizer": tokenizer_options}, tokenizer)
        environment.update({"model_weights_loaded": False, "gpu_required": True,
                            "device": str(device), "device_name": torch.cuda.get_device_name(device),
                            "torch_cuda_runtime": torch.version.cuda,
                            "visible_device_count": torch.cuda.device_count(),
                            "cpu_threads": torch.get_num_threads(), "dependency_changes": []})
        model_assets = {}
        for filename in ("config.json", "model.safetensors"):
            path = Path(cached_file(model_options["name"], filename,
                                    revision=model_options["revision"], local_files_only=True))
            model_assets[filename] = {"path": str(path), "bytes": path.stat().st_size,
                                      "sha256": sha256_file(path)}
        environment["model_assets"] = model_assets
        write_json(output / "environment.json", environment)
        print(f"Loading pinned GPT-2 on {device} ({environment['device_name']}); run_kind={kind}.", flush=True)
        model = load_model(model_options["name"], model_options["revision"], device,
                           local_files_only=model_options["local_files_only"],
                           dtype=model_options["dtype"], attn_implementation=model_options["attn_implementation"])
        environment.update({"model_weights_loaded": True, "parameter_count": sum(p.numel() for p in model.parameters()),
                            "model_dtype": str(next(model.parameters()).dtype),
                            "model_device": str(next(model.parameters()).device),
                            "attention_implementation": model.config._attn_implementation})
        write_json(output / "environment.json", environment)
        original_hooks = hook_snapshot(model)
        # Upstream seeds alignment after the already-created model, before DAS.
        set_seed(seed)
        intervenable = build_intervention(model, layer, rank)
        initial_alignment = alignment_state(intervenable)
        torch.save({"interventions": initial_alignment}, output / "initial_alignment.pt")
        validation["preflight"] = run_preflight_validation(
            model, intervenable, pairs["train"], tokenizer, reference, device, location)
        write_json(output / "validation.json", validation)
        print("Preflight passed: identity, frozen weights, alignment gradients, and variable-length batching.", flush=True)
        initial = {}
        for split in evaluation_splits:
            evaluated = evaluate_condition(model, intervenable, pairs[split], tokenizer, reference,
                                            device, evaluation_batch_size, location, split)
            initial[f"initial_{split}"] = evaluated["metrics"]
            _write_predictions(output / f"initial_{split}_predictions.jsonl", evaluated["predictions"])
        scheduler = training_options["scheduler"]
        training = train_alignment(
            model, intervenable, pairs["train"], tokenizer, reference, device,
            seed=seed, location=location, output_path=output / "training_steps.jsonl",
            epochs=training_options.get("epochs"), max_updates=training_options.get("max_updates"),
            batch_size=training_options["batch_size"],
            learning_rate=training_options["learning_rate"], betas=tuple(training_options["betas"]),
            eps=training_options["eps"], weight_decay=training_options["weight_decay"],
            schedule=training_options["schedule"], schedule_start_factor=scheduler["start_factor"],
            schedule_end_factor=scheduler["end_factor"], schedule_total_iters=scheduler["total_iters"],
            smoke=smoke)
        write_json(output / "training.json", training)
        validation["frozen_weights_and_alignment"] = validate_after_training(
            model, intervenable, validation["preflight"]["model_sha256"], initial_alignment)
        validation["trained_identity_and_batching"] = run_preflight_validation(
            model, intervenable, pairs["train"], tokenizer, reference, device, location)
        write_json(output / "validation.json", validation)
        final = {}
        for split in evaluation_splits:
            evaluated = evaluate_condition(model, intervenable, pairs[split], tokenizer, reference,
                                            device, evaluation_batch_size, location, split)
            final[split] = evaluated["metrics"]
            _write_predictions(output / f"{split}_predictions.jsonl", evaluated["predictions"])
        state = alignment_state(intervenable)
        checkpoint = {
            "schema_version": 1,
            "condition": {"layer": layer, "component": component, "rank": rank,
                          "target_variable": target_variable, "intervention_location": location},
            "model": model_options, "interventions": state,
            "effective_projection": {key: intervention.rotate_layer.weight.detach().cpu().clone()
                                     for key, intervention in intervenable.interventions.items()},
        }
        torch.save(checkpoint, output / "alignment.pt")
        # Exercise the saved raw orthogonal state, not just its derived direction.
        probe = prepare_batch(pairs["train"][:2], tokenizer, reference, device, location)
        with torch.no_grad():
            before_reload = intervention_forward(intervenable, probe)
            saved = torch.load(output / "alignment.pt", map_location=device, weights_only=True)
            for key, intervention in intervenable.interventions.items():
                intervention.load_state_dict(saved["interventions"][key])
            after_reload = intervention_forward(intervenable, probe)
        if not torch.equal(before_reload, after_reload):
            raise RuntimeError("Saved alignment reload did not reproduce exact logits.")
        validation["saved_alignment_reload"] = {"status": "passed", "logits_bit_identical": True,
                                                "sample_ids": [p.sample_id for p in probe.pairs]}
        cleanup_intervention(intervenable)
        if hook_snapshot(model) != original_hooks:
            raise RuntimeError("Condition-owned hooks remained after cleanup.")
        if intervenable.activations or intervenable.full_intervention_outputs:
            raise RuntimeError("Condition activation/output caches remained after cleanup.")
        validation["cleanup"] = {"status": "passed", "hooks_before": original_hooks,
                                 "hooks_after": hook_snapshot(model),
                                 "cached_activation_count": len(intervenable.activations)}
        write_json(output / "validation.json", validation)
        metrics = {**initial, **final}
        write_json(output / "metrics.json", metrics)
        result = {
            "status": "complete", "run_kind": kind,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "condition": checkpoint["condition"], "model": model_options,
            "model_metadata": {"name": model_options["name"], "revision": model_options["revision"],
                               "parameter_count": sum(p.numel() for p in model.parameters()),
                               "layer_count": model.config.n_layer, "hidden_size": model.config.n_embd},
            "tokenizer": tokenizer_options, "seed": seed,
            "original_dataset_counts": original_counts,
            "run_dataset_counts": {split: len(records) for split, records in pairs.items()},
            "dataset_reused": True, "datasets": dataset_metadata,
            "resolved_config_sha256": config_sha256,
            "implementation_sha256": {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))},
            "upstream_commit": provenance["commit"], "metrics": metrics,
            "optimizer_steps": training["optimizer_steps"], "validation_status": "passed",
            "language_model_weights_changed": False, "elapsed_seconds": time.perf_counter() - started,
            "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
            "artifacts": {path.name: sha256_file(path) for path in sorted(output.iterdir()) if path.is_file()},
        }
        write_json(output / "result.json", result)
        display = ", ".join(f"{split} IIA={value['iia_correct']}/{value['iia_total']}"
                            for split, value in final.items())
        print(f"Condition {kind} complete: {display}; evidence={output}.", flush=True)
        return result
    except Exception as error:
        write_json(output / "failure.json", {"status": "failed", "run_kind": kind,
                                            "error_type": type(error).__name__, "error": str(error)})
        raise
    finally:
        if intervenable is not None:
            cleanup_intervention(intervenable)
        del intervenable, model
        gc.collect()
        torch.cuda.empty_cache()


@dataclass(frozen=True)
class EvaluationRuntime:
    """Hold the frozen model and tokenizers shared by locked evaluations."""

    model: Any
    tokenizer: Any
    reference: Any
    device: Any


@contextmanager
def evaluation_runtime(*, model_options: dict, tokenizer_options: dict,
                       device_name: str, cpu_threads: int) -> Iterator[EvaluationRuntime]:
    """Load one frozen model for a batch of checkpoint evaluations and release it."""
    import torch

    from .intervention import load_model

    torch.set_num_threads(cpu_threads)
    torch.set_float32_matmul_precision("highest")
    device = torch.device(device_name)
    model = None
    try:
        tokenizer, reference = load_tokenizers(tokenizer_options)
        model = load_model(model_options["name"], model_options["revision"], device,
                           local_files_only=model_options["local_files_only"],
                           dtype=model_options["dtype"], attn_implementation=model_options["attn_implementation"])
        yield EvaluationRuntime(model, tokenizer, reference, device)
    finally:
        del model
        gc.collect()
        torch.cuda.empty_cache()


def evaluate_checkpoint(
    output: Path, checkpoint_path: Path, *, pairs: dict, model_options: dict,
    tokenizer_options: dict, layer: int, rank: int, location: str, seed: int,
    device_name: str, cpu_threads: int, evaluation_batch_size: int,
    selection_path: Path, selection_sha256: str, checkpoint_sha256: str,
    dataset_metadata: dict, runtime: EvaluationRuntime | None = None,
) -> dict[str, Any]:
    """Evaluate a saved alignment only after verifying its immutable selection lock."""
    if not selection_path.is_file() or sha256_file(selection_path) != selection_sha256:
        raise ValueError(f"Missing or changed selection lock {selection_path}; lock selection before evaluation.")
    if sha256_file(checkpoint_path) != checkpoint_sha256:
        raise ValueError(f"Checkpoint hash mismatch: {checkpoint_path}; restore the selected checkpoint.")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Locked evaluation directory is not empty: {output}; preserve saved evidence.")
    import torch

    from .evaluate import evaluate_condition
    from .intervention import build_intervention, cleanup_intervention
    from .validation import fingerprint_model, hook_snapshot

    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    context = nullcontext(runtime) if runtime is not None else evaluation_runtime(
        model_options=model_options, tokenizer_options=tokenizer_options,
        device_name=device_name, cpu_threads=cpu_threads)
    with context as active:
        model, tokenizer, reference, device = active.model, active.tokenizer, active.reference, active.device
        original_hooks = hook_snapshot(model)
        model_hash = fingerprint_model(model)
        intervenable = None
        try:
            try:
                intervenable = build_intervention(model, layer, rank)
                checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
                for key, intervention in intervenable.interventions.items():
                    intervention.load_state_dict(checkpoint["interventions"][key])
                metrics = {}
                for split, records in pairs.items():
                    evaluated = evaluate_condition(model, intervenable, records, tokenizer, reference,
                                                    device, evaluation_batch_size, location, split)
                    metrics[split] = evaluated["metrics"]
                    _write_predictions(output / f"{split}_predictions.jsonl", evaluated["predictions"])
            finally:
                if intervenable is not None:
                    cleanup_intervention(intervenable)
                    if intervenable.activations or intervenable.full_intervention_outputs:
                        raise RuntimeError("Locked evaluation activation/output caches remained after cleanup.")
                if hook_snapshot(model) != original_hooks or fingerprint_model(model) != model_hash:
                    raise RuntimeError("Locked evaluation changed model weights or left condition-owned hooks.")
            result = {"status": "complete", "run_kind": "full", "seed": seed,
                      "condition": checkpoint["condition"], "metrics": metrics,
                      "selection_sha256": selection_sha256, "checkpoint_sha256": checkpoint_sha256,
                      "datasets": dataset_metadata, "model_sha256": model_hash,
                      "model_metadata": {"name": model_options["name"], "revision": model_options["revision"],
                                         "parameter_count": sum(p.numel() for p in model.parameters()),
                                         "layer_count": model.config.n_layer, "hidden_size": model.config.n_embd},
                      "elapsed_seconds": time.perf_counter() - started,
                      "validation": {"cleanup": "passed", "frozen_weights": "passed"},
                      "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                      "artifacts": {path.name: sha256_file(path) for path in sorted(output.iterdir()) if path.is_file()}}
            write_json(output / "result.json", result)
            print(f"Locked evaluation complete: layer={layer}, seed={seed}; evidence={output}.", flush=True)
            return result
        except BaseException as error:
            write_json(output / "failure.json", {"status": "failed", "error": f"{type(error).__name__}: {error}"})
            raise
