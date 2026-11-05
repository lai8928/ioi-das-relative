"""Reload each activation site's real alignment for locked CPU evaluation."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch", reason="Checkpoint checks require the DAS runtime")
pytest.importorskip("pyvene", reason="Checkpoint checks require pyvene")
from transformers import GPT2Config, GPT2LMHeadModel

from ioi_das.data import sha256_file
from ioi_das.evaluate import evaluate_condition
from ioi_das.experiment import EvaluationRuntime, evaluate_checkpoint
from ioi_das.intervention import alignment_state, build_intervention, cleanup_intervention
from ioi_das.tokenization import load_tokenizers
from ioi_das.validation import fingerprint_model, hook_snapshot, synthetic_unequal_pairs


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def checkpoint_inputs():
    settings = json.loads((ROOT / "configs/base.json").read_text(encoding="utf-8"))
    tokenizer, reference = load_tokenizers(settings["tokenizer"])
    pairs = [replace(pair, split="test") for pair in synthetic_unequal_pairs()]
    return settings, tokenizer, reference, pairs


@pytest.mark.parametrize("component,head,location", [
    ("block_output", None, "N"),
    ("attention_output", None, "N"),
    ("mlp_output", None, "N"),
    ("head_attention_value_output", 1, "N"),
    ("head_query_output", 1, "N"),
    ("head_key_output", 1, "S2"),
    ("head_value_output", 1, "S2"),
])
def test_locked_checkpoint_matches_direct_site_evaluation(
        tmp_path, checkpoint_inputs, component, head, location):
    settings, tokenizer, reference, pairs = checkpoint_inputs
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(29)
        config = GPT2Config(
            vocab_size=tokenizer.vocab_size, n_positions=32, n_ctx=32,
            n_embd=16, n_layer=2, n_head=2, resid_pdrop=0,
            embd_pdrop=0, attn_pdrop=0, use_cache=False,
            pad_token_id=tokenizer.pad_token_id,
        )
        config._attn_implementation = "eager"
        model = GPT2LMHeadModel(config).eval()
        wrapper = build_intervention(model, layer=1, rank=1,
                                     component=component, head=head)
    condition = {"layer": 1, "component": component, "head": head,
                 "site_size": 8 if head is not None else 16, "rank": 1,
                 "target_variable": "position", "intervention_location": location}
    checkpoint = tmp_path / "alignment.pt"
    try:
        torch.save({"schema_version": 1, "condition": condition,
                    "interventions": alignment_state(wrapper)}, checkpoint)
        expected = evaluate_condition(model, wrapper, pairs, tokenizer, reference,
                                      "cpu", batch_size=2, location=location, split="test")
    finally:
        cleanup_intervention(wrapper)

    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"selected_layer": 1}), encoding="utf-8")
    model_hash = fingerprint_model(model)
    hooks_before = hook_snapshot(model)
    output = tmp_path / "post_lock"
    result = evaluate_checkpoint(
        output, checkpoint, pairs={"test": pairs}, model_options=settings["model"],
        tokenizer_options=settings["tokenizer"], layer=1, rank=1,
        component=component, head=head, location=location, seed=29,
        device_name="cpu", cpu_threads=2, evaluation_batch_size=2,
        selection_path=selection, selection_sha256=sha256_file(selection),
        checkpoint_sha256=sha256_file(checkpoint), dataset_metadata={},
        runtime=EvaluationRuntime(model, tokenizer, reference, torch.device("cpu")),
    )
    saved = json.loads((output / "result.json").read_text(encoding="utf-8"))
    predictions = [json.loads(line) for line in
                   (output / "test_predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert result["status"] == saved["status"] == "complete"
    assert result["condition"] == saved["condition"] == condition
    assert result["metrics"]["test"] == expected["metrics"]
    assert predictions == expected["predictions"]
    assert all(row["base_position"] != row["source_position"] for row in predictions)
    assert fingerprint_model(model) == model_hash
    assert hook_snapshot(model) == hooks_before == {}
    assert all(not parameter.requires_grad and parameter.grad is None
               for parameter in model.parameters())
