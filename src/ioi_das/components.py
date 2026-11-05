"""Describe supported activation sites without loading a model or runtime."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentSpec:
    """Resolve a component's pyvene unit and per-token intervention size."""

    unit: str

    def size(self, n_embd: int, n_head: int) -> int:
        """Return the full residual width or one head's projected width."""
        return n_embd // n_head if self.unit == "h.pos" else n_embd


COMPONENTS = {
    "block_output": ComponentSpec("pos"),
    "attention_output": ComponentSpec("pos"),
    "mlp_output": ComponentSpec("pos"),
    "head_attention_value_output": ComponentSpec("h.pos"),
    "head_query_output": ComponentSpec("h.pos"),
    "head_key_output": ComponentSpec("h.pos"),
    "head_value_output": ComponentSpec("h.pos"),
}


def validate_site(component: str, head: int | None, rank: int,
                  n_embd: int, n_head: int) -> int:
    """Return a site's size after checking the selected head and DAS rank."""
    if component not in COMPONENTS:
        raise ValueError(f"Unsupported intervention component {component!r}; choose {', '.join(COMPONENTS)}.")
    spec = COMPONENTS[component]
    if spec.unit == "h.pos":
        if type(head) is not int or not 0 <= head < n_head:
            raise ValueError(f"Component {component!r} requires an integer head in 0..{n_head - 1}; got {head!r}.")
    elif head is not None:
        raise ValueError(f"Component {component!r} does not accept head={head!r}; remove intervention.head.")
    size = spec.size(n_embd, n_head)
    if type(rank) is not int or not 1 <= rank <= size:
        raise ValueError(f"Component {component!r} has size {size}; rank must be in 1..{size}, got {rank!r}.")
    return size
