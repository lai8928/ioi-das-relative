"""Frozen GPT-2 and a scoped pyvene low-rank intervention."""

from dataclasses import dataclass, replace
from typing import Any, Callable, Sequence

import torch
from pyvene import (
    IntervenableConfig,
    IntervenableModel,
    LowRankRotatedSpaceIntervention,
    RepresentationConfig,
)

from .data import PairRecord
from .positions import resolve_pair_positions
from .tokenization import check_answer, encode_pair_batch


@dataclass(frozen=True)
class PreparedBatch:
    """Keep each side's mask and positions, with readout always at base N."""

    pairs: tuple[PairRecord, ...]
    base_inputs: dict[str, torch.Tensor]
    source_inputs: dict[str, torch.Tensor]
    base_positions: list[int]
    source_positions: list[int]
    base_readout: torch.Tensor
    factual_labels: torch.Tensor
    counterfactual_labels: torch.Tensor


def prepare_batch(pairs: Sequence[PairRecord], tokenizer: Any, reference: Any,
                  device: str | torch.device, location: str = "N") -> PreparedBatch:
    """Reuse audited encoders and reject unsupported answers without dropping pairs."""
    if not pairs:
        raise ValueError("Cannot prepare an empty intervention batch.")
    if any(pair.target_variable != "position" for pair in pairs):
        identifiers = [p.sample_id for p in pairs if p.target_variable != "position"]
        raise ValueError(f"{identifiers}: target_variable must be 'position'.")
    encoded = encode_pair_batch(pairs, tokenizer, reference)
    positions = resolve_pair_positions(encoded, location)
    readout = resolve_pair_positions(encoded, "N")["base"]
    factual, counterfactual = [], []
    for pair, base in zip(encoded.pairs, encoded.base.examples):
        for name, labels in ((pair.base.io_name, factual),
                             (pair.counterfactual_answer, counterfactual)):
            answer = check_answer(tokenizer, reference, base, name)
            if answer.token_id is None:
                raise ValueError(f"{answer.diagnostic} Full continuation IDs: "
                                 f"{list(answer.token_ids)}. Saved examples are unchanged.")
            labels.append(answer.token_id)
    tensor = lambda values: torch.tensor(values, dtype=torch.long, device=device)
    base_inputs = {name: tensor(values) for name, values in encoded.base.model_inputs().items()}
    source_inputs = {name: tensor(values) for name, values in encoded.source.model_inputs().items()}
    return PreparedBatch(encoded.pairs, base_inputs, source_inputs,
                         positions["base"], positions["source"], tensor(readout),
                         tensor(factual), tensor(counterfactual))


def load_model(name: str, revision: str, device: str | torch.device, *,
               local_files_only: bool = True, dtype: str = "float32",
               attn_implementation: str = "eager") -> Any:
    """Load pinned cached safetensors in float32 with deterministic eager attention."""
    from transformers import GPT2LMHeadModel

    if name != "gpt2" or not revision:
        raise ValueError(f"Model {name!r} requires name 'gpt2' and a pinned revision.")
    if not local_files_only:
        raise ValueError("Model weights must use the existing cache; set local_files_only=true.")
    if dtype != "float32" or attn_implementation != "eager":
        raise ValueError(f"Unsupported model dtype={dtype!r}, attn_implementation={attn_implementation!r}; "
                         "use float32 with eager attention for deterministic alignment training.")
    model = GPT2LMHeadModel.from_pretrained(
        name, revision=revision,
        local_files_only=True, use_safetensors=True,
        dtype=torch.float32, attn_implementation="eager",
    )
    model.config.use_cache = False
    model.config.pad_token_id = model.config.eos_token_id
    model.to(device)
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
        parameter.grad = None
    return model


class ScopedIntervenableModel(IntervenableModel):
    """Remove only this wrapper's handles, including after failed forward calls.

    pyvene 0.1.8 removes every forward/pre-forward hook on its model during
    cleanup. Tracking registrations locally preserves unrelated user hooks
    without modifying pyvene or any installed package.
    """

    def __init__(self, config: Any, model: Any) -> None:
        super().__init__(config, model, use_fast=False)
        self._owned_hook_handles: list[Any] = []
        self.intervention_hooks = {
            key: self._tracked_registration(register)
            for key, register in self.intervention_hooks.items()
        }

    def _tracked_registration(self, register: Callable[..., Any]) -> Callable[..., Any]:
        def tracked(*args: Any, **kwargs: Any) -> Any:
            handle = register(*args, **kwargs)
            self._owned_hook_handles.append(handle)
            return handle
        return tracked

    def _remove_forward_hooks(self) -> None:
        for handle in getattr(self, "_owned_hook_handles", ()):
            handle.remove()
        if hasattr(self, "_owned_hook_handles"):
            self._owned_hook_handles.clear()


def build_intervention(model: Any, layer: int = 8,
                       rank: int = 1) -> ScopedIntervenableModel:
    """Create one block_output intervention with per-example token gathering."""
    if not 0 <= layer < model.config.n_layer:
        raise ValueError(f"Layer {layer} is outside 0..{model.config.n_layer - 1}.")
    if not 1 <= rank <= model.config.n_embd:
        raise ValueError(f"Rank {rank} is outside 1..{model.config.n_embd}.")
    config = IntervenableConfig(
        representations=[RepresentationConfig(
            layer=layer, component="block_output", unit="pos",
            max_number_of_units=1, low_rank_dimension=rank,
        )],
        intervention_types=LowRankRotatedSpaceIntervention,
        mode="parallel",
    )
    intervenable = ScopedIntervenableModel(config, model)
    intervenable.set_device(next(model.parameters()).device, set_model=False)
    intervenable.disable_model_gradients()
    return intervenable


def _readout(logits: torch.Tensor, batch: PreparedBatch) -> torch.Tensor:
    rows = torch.arange(len(batch.pairs), device=logits.device)
    return logits[rows, batch.base_readout]


def factual_forward(model: Any, batch: PreparedBatch) -> torch.Tensor:
    """Read factual next-token logits at each base's last valid input token."""
    outputs = model(**batch.base_inputs, use_cache=False, return_dict=True)
    return _readout(outputs.logits, batch)


def intervention_forward(intervenable: ScopedIntervenableModel,
                         batch: PreparedBatch) -> torch.Tensor:
    """Share the same masked forward between optimization and IIA evaluation.

    Do not disable autograd here: frozen language-model parameters still need
    to propagate gradients from the readout through the learned intervention.
    The location tensor contract is side/intervention/example/unit.
    """
    locations = {
        "sources->base": (
            [[[position] for position in batch.source_positions]],
            [[[position] for position in batch.base_positions]],
        )
    }
    try:
        _, outputs = intervenable(
            batch.base_inputs, [batch.source_inputs], unit_locations=locations,
            output_original_output=False, use_cache=False,
        )
        return _readout(outputs.logits, batch)
    finally:
        # Also cover pyvene input-validation failures before its internal try.
        intervenable._cleanup_states()
        intervenable.full_intervention_outputs.clear()


def identity_forward(intervenable: ScopedIntervenableModel,
                     batch: PreparedBatch) -> torch.Tensor:
    """Use the identical base activation as source through the learned projection."""
    identity = replace(batch, source_inputs=batch.base_inputs,
                       source_positions=list(batch.base_positions))
    return intervention_forward(intervenable, identity)


def alignment_state(intervenable: ScopedIntervenableModel) -> dict[str, dict[str, torch.Tensor]]:
    """Clone raw orthogonal-parametrization state for exact CPU checkpoint reload."""
    return {
        key: {name: value.detach().cpu().clone()
              for name, value in intervention.state_dict().items()}
        for key, intervention in intervenable.interventions.items()
    }


def cleanup_intervention(intervenable: ScopedIntervenableModel) -> None:
    """Release condition-owned hooks, activation caches, outputs, and gradient buffers."""
    intervenable._cleanup_states()
    intervenable.full_intervention_outputs.clear()
    for intervention in intervenable.interventions.values():
        intervention.zero_grad(set_to_none=True)
