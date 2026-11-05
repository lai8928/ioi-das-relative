"""Validate activation-site semantics with a tiny random frozen GPT-2 on CPU."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch", reason="Site checks require the DAS runtime")
pytest.importorskip("pyvene", reason="Site checks require the external pyvene dependency")
from transformers import GPT2Config, GPT2LMHeadModel

from ioi_das.components import COMPONENTS, validate_site
from ioi_das.data import load_pairs
from ioi_das.intervention import (
    alignment_state, build_intervention, cleanup_intervention, factual_forward,
    identity_forward, intervention_forward, prepare_batch,
)
from ioi_das.tokenization import load_tokenizers
from ioi_das.validation import hook_snapshot, run_preflight_validation, synthetic_unequal_pairs


ROOT = Path(__file__).resolve().parents[1]
HEAD_SITES = [component for component, spec in COMPONENTS.items() if spec.unit == "h.pos"]


@pytest.fixture(scope="module")
def site_inputs():
    config = json.loads((ROOT / "configs/base.json").read_text())
    tokenizer, reference = load_tokenizers(config["tokenizer"])
    return tokenizer, reference, load_pairs(ROOT / "data/generated/train.jsonl")


@pytest.fixture
def site_model(site_inputs):
    tokenizer, _, _ = site_inputs
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(17)
        config = GPT2Config(
            vocab_size=tokenizer.vocab_size, n_positions=32, n_ctx=32,
            n_embd=16, n_layer=2, n_head=2,
            resid_pdrop=0, embd_pdrop=0, attn_pdrop=0,
            use_cache=False, pad_token_id=tokenizer.pad_token_id,
        )
        config._attn_implementation = "eager"
        model = GPT2LMHeadModel(config).eval()
    return model


def _site_wrapper(model, component):
    return build_intervention(model, layer=1, rank=1, component=component,
                              head=1 if component in HEAD_SITES else None)


@pytest.mark.parametrize("component", COMPONENTS)
def test_site_preflight_training_reload_and_failure_cleanup(
        component, site_inputs, site_model, tmp_path):
    tokenizer, reference, pairs = site_inputs
    wrapper = _site_wrapper(site_model, component)
    location = "S2" if component in {"head_key_output", "head_value_output"} else "N"
    expected_size = 8 if component in HEAD_SITES else 16
    assert wrapper.site_size == expected_size
    assert next(iter(wrapper.interventions.values())).embed_dim == expected_size
    if component == "block_output":
        assert list(wrapper.interventions) == ["layer_1_comp_block_output_unit_pos_nunit_1#0"]
    sentinel = site_model.transformer.h[1].register_forward_hook(lambda *args: None)
    hooks = hook_snapshot(site_model)
    reloaded = None
    try:
        preflight = run_preflight_validation(
            site_model, wrapper, pairs, tokenizer, reference, "cpu", location)
        assert preflight["gradients"]["alignment_gradient_norm"] > 0
        assert preflight["identity_intervention"]["max_absolute_difference"] == 0
        assert preflight["hooks_before"] == preflight["hooks_after"] == hooks
        batch = prepare_batch(synthetic_unequal_pairs(), tokenizer, reference, "cpu", location)
        with torch.no_grad():
            assert torch.equal(identity_forward(wrapper, batch), factual_forward(site_model, batch))
        initial = alignment_state(wrapper)
        optimizer = torch.optim.Adam(wrapper.get_trainable_parameters(), lr=1e-3)
        loss = torch.nn.functional.cross_entropy(
            intervention_forward(wrapper, batch), batch.counterfactual_labels)
        loss.backward()
        assert all(parameter.grad is None for parameter in site_model.parameters())
        assert all(parameter.grad is not None and torch.isfinite(parameter.grad).all()
                   for parameter in wrapper.get_trainable_parameters())
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        trained = alignment_state(wrapper)
        assert any(not torch.equal(value, initial[key][name])
                   for key, state in trained.items() for name, value in state.items())
        with torch.no_grad():
            expected = intervention_forward(wrapper, batch)
        path = tmp_path / "alignment.pt"
        torch.save({"interventions": trained}, path)
        reloaded = _site_wrapper(site_model, component)
        saved = torch.load(path, weights_only=True)
        for key, intervention in reloaded.interventions.items():
            intervention.load_state_dict(saved["interventions"][key])
        with torch.no_grad():
            assert torch.equal(intervention_forward(reloaded, batch), expected)
        with pytest.raises((IndexError, RuntimeError)):
            intervention_forward(wrapper, replace(batch, base_positions=[1000, 1000]))
        assert hook_snapshot(site_model) == hooks
        assert not wrapper.activations
        assert not wrapper.full_intervention_outputs
    finally:
        cleanup_intervention(wrapper)
        if reloaded is not None:
            cleanup_intervention(reloaded)
        sentinel.remove()
    assert hook_snapshot(site_model) == {}


def _capture_tensor(model, inputs, module, pre_hook):
    observed = []
    if pre_hook:
        handle = module.register_forward_pre_hook(
            lambda module, args: observed.append(args[0].detach().clone()))
    else:
        handle = module.register_forward_hook(
            lambda module, args, output: observed.append(output.detach().clone()))
    try:
        with torch.no_grad():
            model(**inputs, use_cache=False)
        return observed[-1]
    finally:
        handle.remove()


@pytest.mark.parametrize("component", HEAD_SITES)
def test_head_interchange_changes_only_its_slice_and_attention(
        component, site_inputs, site_model, monkeypatch):
    tokenizer, reference, _ = site_inputs
    wrapper = _site_wrapper(site_model, component)
    location = "S2" if component in {"head_key_output", "head_value_output"} else "N"
    batch = prepare_batch(synthetic_unequal_pairs(), tokenizer, reference, "cpu", location)
    assert batch.base_positions != batch.source_positions
    attention = site_model.transformer.h[1].attn
    pre_hook = component == "head_attention_value_output"
    module = attention.c_proj if pre_hook else attention.c_attn
    base = _capture_tensor(site_model, batch.base_inputs, module, pre_hook)
    source = _capture_tensor(site_model, batch.source_inputs, module, pre_hook)
    factual_probs = _capture_tensor(site_model, batch.base_inputs, attention.attn_dropout, False)
    observed, probabilities, handles = [], [], []
    register_setter = wrapper._intervention_setter

    def observe_after_setter(*args, **kwargs):
        result = register_setter(*args, **kwargs)
        # pyvene registers its patch for each call; the observer must follow it.
        if pre_hook:
            handle = module.register_forward_pre_hook(
                lambda module, args: observed.append(args[0].detach().clone()))
        else:
            handle = module.register_forward_hook(
                lambda module, args, output: observed.append(output.detach().clone()))
        handles.append(handle)
        return result

    monkeypatch.setattr(wrapper, "_intervention_setter", observe_after_setter)
    handles.append(attention.attn_dropout.register_forward_hook(
        lambda module, args, output: probabilities.append(output.detach().clone())))
    try:
        with torch.no_grad():
            intervention_forward(wrapper, batch)
        patched, patched_probs = observed[-1], probabilities[-1]
        part = {"head_attention_value_output": 0, "head_query_output": 0,
                "head_key_output": 1, "head_value_output": 2}[component]
        columns = slice(part * 16 + 8, part * 16 + 16)
        rows = torch.arange(2)
        base_positions = torch.tensor(batch.base_positions)
        source_positions = torch.tensor(batch.source_positions)
        allowed = torch.zeros_like(base, dtype=torch.bool)
        allowed[rows, base_positions, columns] = True
        assert torch.equal(patched[~allowed], base[~allowed])
        assert not torch.equal(patched[allowed], base[allowed])
        intervention = next(iter(wrapper.interventions.values()))
        with torch.no_grad():
            expected = intervention(base[rows, base_positions, columns],
                                    source[rows, source_positions, columns])
        torch.testing.assert_close(patched[rows, base_positions, columns], expected,
                                   rtol=0, atol=0)
        if component == "head_value_output":
            assert torch.equal(patched_probs, factual_probs)
        elif component in {"head_query_output", "head_key_output"}:
            assert torch.equal(patched_probs[:, 0], factual_probs[:, 0])
            assert not torch.equal(patched_probs[:, 1], factual_probs[:, 1])
            if component == "head_query_output":
                other_rows = torch.ones_like(factual_probs[:, 1], dtype=torch.bool)
                other_rows[rows, base_positions] = False
                assert torch.equal(patched_probs[:, 1][other_rows], factual_probs[:, 1][other_rows])
    finally:
        for handle in handles:
            handle.remove()
        cleanup_intervention(wrapper)
    assert hook_snapshot(site_model) == {}


@pytest.mark.parametrize("component", COMPONENTS)
def test_site_dimension_bounds_rejected_before_building(component, site_model, monkeypatch):
    from ioi_das import intervention

    def forbidden_wrapper(*args, **kwargs):
        pytest.fail("An invalid site must fail before constructing a pyvene wrapper")

    monkeypatch.setattr(intervention, "ScopedIntervenableModel", forbidden_wrapper)
    head = 1 if component in HEAD_SITES else None
    size = 8 if component in HEAD_SITES else 16
    for rank in (0, size + 1, True):
        with pytest.raises(ValueError, match=rf"{component}.*size {size}.*rank"):
            build_intervention(site_model, layer=1, rank=rank, component=component, head=head)
    for invalid_head in ((None, -1, 2, True) if component in HEAD_SITES else (0, 1)):
        with pytest.raises(ValueError, match=rf"{component}.*head"):
            build_intervention(site_model, layer=1, rank=1, component=component, head=invalid_head)


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("n_embd,n_head", [(16, 2), (768, 12), (1024, 16)])
def test_registry_sizes_follow_model_dimensions(component, n_embd, n_head):
    head = n_head - 1 if component in HEAD_SITES else None
    size = n_embd // n_head if component in HEAD_SITES else n_embd
    assert validate_site(component, head, size, n_embd, n_head) == size
