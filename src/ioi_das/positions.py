"""Resolve named anchors and offsets independently for each encoded prompt."""

import re
from typing import Sequence

from .tokenization import EncodedPrompt, PairBatch


class PositionError(ValueError):
    """An invalid anchor, mask, or out-of-range per-example position."""


def resolve_position(example: EncodedPrompt, location: str,
                     attention_mask: Sequence[int] | None = None) -> int:
    """Resolve IO/GOAL_NAME, S1, S2, END/N and signed token offsets.

    Name anchors select the last token of their full occurrence span. END is
    always the last non-padding input token, independent of the readout caller.
    """
    context = f"{example.sample_id}/{example.side}"
    match = re.fullmatch(r"(GOAL_NAME|IO|S1|S2|END|N)([+-]\d+)?", location)
    if not match:
        raise PositionError(f"{context}: invalid location {location!r}; use "
                            "GOAL_NAME, IO, S1, S2, END/N, or a signed offset such as N-2.")
    mask = tuple(example.attention_mask if attention_mask is None else attention_mask)
    length = sum(mask)
    if not length or any(x not in (0, 1) for x in mask) or mask != (1,) * length + (0,) * (len(mask) - length):
        raise PositionError(f"{context}: mask must contain a nonempty input followed "
                            "only by right padding; check tokenization and batching.")
    if length != example.valid_length:
        raise PositionError(f"{context}: batch mask length {length} differs from "
                            f"input length {example.valid_length}; check batch alignment.")
    anchor, offset_text = match.groups()
    offset = int(offset_text or 0)
    if anchor in ("END", "N"):
        index = length - 1
    else:
        role = "IO" if anchor in ("IO", "GOAL_NAME") else anchor
        if role not in example.name_spans:
            raise PositionError(f"{context}: missing {role} occurrence span; "
                                "rebuild role metadata and tokenizer offsets.")
        start, stop = example.name_spans[role].token_span
        if not 0 <= start < stop <= length:
            raise PositionError(f"{context}: invalid {role} token span {(start, stop)} "
                                f"for input length {length}; inspect occurrence offsets.")
        index = stop - 1
    resolved = index + offset
    if not 0 <= resolved < length:
        raise PositionError(f"{context}: {location} resolves to {resolved}, outside "
                            f"valid token indices 0..{length - 1} (length={length}); "
                            "choose an offset that stays inside this prompt.")
    return resolved


def resolve_pair_positions(batch: PairBatch, location: str) -> dict[str, list[int]]:
    """Return separate base/source position arrays, using each side's own mask."""
    return {
        "base": [resolve_position(example, location, mask)
                 for example, mask in zip(batch.base.examples, batch.base.attention_mask)],
        "source": [resolve_position(example, location, mask)
                   for example, mask in zip(batch.source.examples, batch.source.attention_mask)],
    }
