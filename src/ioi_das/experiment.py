"""Run only the authorized Phase 2 condition using the unchanged saved dataset."""

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from .audit import ensure_saved_pairs, runtime_environment, verify_upstream, write_json
from .data import sha256_file
from .tokenization import load_tokenizers


def load_phase2_config(path: Path, output_override: str | None = None) -> dict:
    """Resolve explicit paths and reject conditions outside this checkpoint."""
    path = path.expanduser().resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    root = (path.parent / config["project_root"]).resolve()
    for key in ("upstream_dir", "generated_dir", "output_dir"):
        value = output_override if key == "output_dir" and output_override else config[key]
        config[key] = (root / value).resolve()
    config["project_root"] = root
    config["config_path"] = path
    required = {"target_variable": "position", "intervention_location": "N", "readout_location": "N",
                "layer": 8, "component": "block_output", "rank": 1}
    if any(config.get(key) != value for key, value in required.items()):
        raise ValueError("Phase 2 permits only position / GPT-2 / layer 8 / block_output / N / rank 1.")
    for key in ("seed", "dataset_seed", "cpu_threads", "evaluation_batch_size"):
        if isinstance(config.get(key), bool) or not isinstance(config.get(key), int):
            raise ValueError(f"{key} must be an integer.")
    if config["cpu_threads"] <= 0 or config["evaluation_batch_size"] <= 0:
        raise ValueError("Thread and evaluation batch counts must be positive.")
    model = config["model"]
    if model.get("name") != "gpt2" or model.get("dtype") != "float32" or model.get("attn_implementation") != "eager":
        raise ValueError("Phase 2 requires GPT-2 float32 with eager attention.")
    if not model.get("revision") or not model.get("local_files_only"):
        raise ValueError("Specify a pinned cached model revision with local_files_only=true.")
    if config["tokenizer"]["name"] != model["name"] or config["tokenizer"]["revision"] != model["revision"]:
        raise ValueError("Model and tokenizer identities/revisions must match for Phase 2.")
    training = config["training"]
    if training != {
        "epochs": 10, "batch_size": 20, "optimizer": "Adam", "learning_rate": 0.01,
        "betas": [0.9, 0.999], "eps": 1e-8, "weight_decay": 0.0,
        "scheduler": {"name": "LinearLR", "start_factor": 1 / 3, "end_factor": 0.1,
                      "total_iters": 10, "step_interval": "batch"},
    }:
        raise ValueError("Phase 2 preserves the pinned tutorial's 10 epochs, batch 20, "
                         "Adam and per-batch LinearLR schedule; restore configs/phase2.json settings.")
    return config


def _json_config(config: dict, run_kind: str) -> dict:
    return {**{key: str(value) if isinstance(value, Path) else value for key, value in config.items()},
            "run_kind": run_kind}


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


def run_condition(config: dict, smoke: bool = False) -> dict:
    """Train and evaluate one condition, with separately labeled smoke artifacts."""
    import torch
    from transformers import set_seed
    from transformers.utils.hub import cached_file

    from .evaluate import evaluate_condition
    from .intervention import (alignment_state, build_intervention, cleanup_intervention,
                               intervention_forward, load_model, prepare_batch)
    from .train import train_alignment
    from .validation import hook_snapshot, run_preflight_validation, validate_after_training

    kind = "smoke" if smoke else "full"
    output = config["output_dir"] / kind
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Run directory is not empty: {output}; preserve it and select a new --output-dir.")
    # Phase 2 must never generate a replacement for the completed saved data.
    for name in ("manifest.json", "train.jsonl", "test.jsonl"):
        if not (config["generated_dir"] / name).is_file():
            raise FileNotFoundError(f"Missing saved dataset file {name}; restore the completed Phase 1 dataset.")
    provenance = verify_upstream(config["upstream_dir"])
    data_config = {**config, "seed": config["dataset_seed"]}
    pairs, manifest, reused = ensure_saved_pairs(data_config, provenance)
    if not reused:
        raise RuntimeError("Phase 2 requires reusing saved datasets.")
    original_counts = {split: len(records) for split, records in pairs.items()}
    if smoke:
        pairs = {"train": _balanced_subset(pairs["train"], 5),
                 "test": _balanced_subset(pairs["test"], 2)}
    torch.set_num_threads(config["cpu_threads"])
    torch.set_float32_matmul_precision("highest")
    device = torch.device(config["device"])
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("The configured Phase 2 run requires a server CUDA device. "
                           "Run outside a GPU-restricted sandbox; no CPU fallback is performed.")
    # Initialize the allocator before resetting its statistics (torch 2.5.1).
    torch.cuda.set_device(device)
    torch.cuda.reset_peak_memory_stats(device)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "config.json", _json_config(config, kind))
    model, intervenable = None, None
    validation = {}
    started = time.perf_counter()
    try:
        tokenizer, reference = load_tokenizers(config["tokenizer"])
        environment = runtime_environment(config, tokenizer)
        environment.update({"model_weights_loaded": False, "gpu_required": True,
                            "device": str(device), "device_name": torch.cuda.get_device_name(device),
                            "torch_cuda_runtime": torch.version.cuda,
                            "visible_device_count": torch.cuda.device_count(),
                            "cpu_threads": torch.get_num_threads(), "dependency_changes": []})
        model_assets = {}
        for filename in ("config.json", "model.safetensors"):
            path = Path(cached_file(config["model"]["name"], filename,
                                    revision=config["model"]["revision"], local_files_only=True))
            model_assets[filename] = {"path": str(path), "bytes": path.stat().st_size,
                                      "sha256": sha256_file(path)}
        environment["model_assets"] = model_assets
        write_json(output / "environment.json", environment)
        print(f"Loading pinned GPT-2 on {device} ({environment['device_name']}); run_kind={kind}.", flush=True)
        model = load_model(config["model"], device)
        environment.update({"model_weights_loaded": True, "parameter_count": sum(p.numel() for p in model.parameters()),
                            "model_dtype": str(next(model.parameters()).dtype),
                            "model_device": str(next(model.parameters()).device),
                            "attention_implementation": model.config._attn_implementation})
        write_json(output / "environment.json", environment)
        original_hooks = hook_snapshot(model)
        # Upstream seeds alignment after the already-created model, before DAS.
        set_seed(config["seed"])
        intervenable = build_intervention(model, config["layer"], config["rank"])
        initial_alignment = alignment_state(intervenable)
        torch.save({"interventions": initial_alignment}, output / "initial_alignment.pt")
        validation["preflight"] = run_preflight_validation(
            model, intervenable, pairs["train"], tokenizer, reference, device, "N")
        write_json(output / "validation.json", validation)
        print("Preflight passed: identity, frozen weights, alignment gradients, and variable-length batching.", flush=True)
        initial = evaluate_condition(model, intervenable, pairs["train"], tokenizer, reference,
                                     device, config["evaluation_batch_size"], "N", "train")
        _write_predictions(output / "initial_train_predictions.jsonl", initial["predictions"])
        training = train_alignment(model, intervenable, pairs["train"], tokenizer, reference,
                                   device, config["training"], config["seed"], "N",
                                   output / "training_steps.jsonl", smoke)
        write_json(output / "training.json", training)
        if not smoke and (training["optimizer_steps"] != 100 or training["presentations"] != 2000):
            raise RuntimeError("The full Phase 2 run did not complete 100 updates / 2000 training presentations.")
        validation["frozen_weights_and_alignment"] = validate_after_training(
            model, intervenable, validation["preflight"]["model_sha256"], initial_alignment)
        validation["trained_identity_and_batching"] = run_preflight_validation(
            model, intervenable, pairs["train"], tokenizer, reference, device, "N")
        write_json(output / "validation.json", validation)
        final = {}
        for split in ("train", "test"):
            evaluated = evaluate_condition(model, intervenable, pairs[split], tokenizer, reference,
                                            device, config["evaluation_batch_size"], "N", split)
            final[split] = evaluated["metrics"]
            _write_predictions(output / f"{split}_predictions.jsonl", evaluated["predictions"])
        state = alignment_state(intervenable)
        checkpoint = {
            "schema_version": 1,
            "condition": {key: config[key] for key in ("layer", "component", "rank", "target_variable", "intervention_location")},
            "model": config["model"], "interventions": state,
            "effective_projection": {key: intervention.rotate_layer.weight.detach().cpu().clone()
                                     for key, intervention in intervenable.interventions.items()},
        }
        torch.save(checkpoint, output / "alignment.pt")
        # Exercise the saved raw orthogonal state, not just its derived direction.
        probe = prepare_batch(pairs["train"][:2], tokenizer, reference, device, "N")
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
        metrics = {"initial_train": initial["metrics"], **final}
        write_json(output / "metrics.json", metrics)
        result = {
            "status": "complete", "run_kind": kind,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "condition": checkpoint["condition"], "model": config["model"],
            "tokenizer": config["tokenizer"], "seed": config["seed"],
            "original_dataset_counts": original_counts,
            "run_dataset_counts": {split: len(records) for split, records in pairs.items()},
            "dataset_reused": True, "dataset_manifest_sha256": sha256_file(config["generated_dir"] / "manifest.json"),
            "dataset_files": manifest["files"], "config_source_sha256": sha256_file(config["config_path"]),
            "implementation_sha256": {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))},
            "upstream_commit": provenance["commit"], "metrics": metrics,
            "optimizer_steps": training["optimizer_steps"], "validation_status": "passed",
            "language_model_weights_changed": False, "elapsed_seconds": time.perf_counter() - started,
            "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
            "artifacts": {path.name: sha256_file(path) for path in sorted(output.iterdir()) if path.is_file()},
        }
        (output / "summary.md").write_text(
            f"# Phase 2 {kind} run\n\n"
            "GPT-2, layer 8, block_output, N, rank 1, target_variable=position.\n\n"
            f"Optimizer updates: {training['optimizer_steps']}; training pairs: {len(pairs['train'])}.\n\n"
            f"Train IIA: {final['train']['iia_correct']}/{final['train']['iia_total']} = {final['train']['iia']}.\n\n"
            f"Test IIA: {final['test']['iia_correct']}/{final['test']['iia_total']} = {final['test']['iia']}.\n\n"
            f"Test factual accuracy: {final['test']['factual_correct']}/{final['test']['factual_total']} = {final['test']['factual_accuracy']}.\n\n"
            "Identity, gradients, bit-identical frozen model state, variable-length batching, saved alignment reload, "
            "and hook cleanup passed. Full-precision values and counts are in metrics.json; this run does not use test data for tuning.\n",
            encoding="utf-8")
        result["artifacts"] = {path.name: sha256_file(path) for path in sorted(output.iterdir())
                               if path.is_file() and path.name != "result.json"}
        write_json(output / "result.json", result)
        print(f"Phase 2 {kind} complete: test IIA={final['test']['iia_correct']}/{final['test']['iia_total']}; evidence={output}.", flush=True)
        return result
    except Exception as error:
        write_json(output / "failure.json", {"status": "failed", "run_kind": kind,
                                            "error_type": type(error).__name__, "error": str(error)})
        raise
    finally:
        if intervenable is not None:
            cleanup_intervention(intervenable)
