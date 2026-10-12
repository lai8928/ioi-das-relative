"""Offset-based IOI encoding, continuation checks, and independent right padding."""

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from .data import PairRecord, PromptRecord


@dataclass(frozen=True)
class NameTokenSpan:
    """Half-open character and token spans for one formatted name occurrence."""

    name: str
    field: str
    occurrence: int
    char_span: tuple[int, int]
    token_span: tuple[int, int]


@dataclass(frozen=True)
class EncodedPrompt:
    sample_id: str
    side: str
    prompt: PromptRecord
    input_ids: tuple[int, ...]
    readable_tokens: tuple[str, ...]
    attention_mask: tuple[int, ...]
    offsets: tuple[tuple[int, int], ...]
    name_spans: dict[str, NameTokenSpan]

    @property
    def valid_length(self) -> int:
        return sum(self.attention_mask)


@dataclass(frozen=True)
class EncodedBatch:
    examples: tuple[EncodedPrompt, ...]
    input_ids: tuple[tuple[int, ...], ...]
    attention_mask: tuple[tuple[int, ...], ...]

    def model_inputs(self) -> dict[str, tuple[tuple[int, ...], ...]]:
        """Retain both arrays for future model calls; convert to tensors there."""
        return {"input_ids": self.input_ids, "attention_mask": self.attention_mask}


@dataclass(frozen=True)
class PairBatch:
    pairs: tuple[PairRecord, ...]
    base: EncodedBatch
    source: EncodedBatch


@dataclass(frozen=True)
class AnswerCheck:
    name: str
    continuation: str
    token_ids: tuple[int, ...]
    readable_tokens: tuple[str, ...]
    standalone_token_ids: tuple[int, ...]
    prefix_preserved: bool
    status: str
    token_id: int | None
    diagnostic: str | None


def load_tokenizers(config: dict[str, Any]) -> tuple[Any, Any]:
    """Load pinned fast and reference GPT-2 tokenizers, without loading weights."""
    from transformers import GPT2Tokenizer, GPT2TokenizerFast

    if not config.get("revision"):
        raise ValueError("Specify a pinned tokenizer revision in the configuration.")
    options = {
        "revision": config["revision"],
        "local_files_only": config.get("local_files_only", True),
    }
    fast = GPT2TokenizerFast.from_pretrained(config["name"], **options)
    reference = GPT2Tokenizer.from_pretrained(config["name"], **options)
    if not fast.is_fast:
        raise ValueError("Name occurrence mapping requires a compatible fast tokenizer.")
    fast.padding_side = "right"
    fast.pad_token = fast.eos_token
    reference.padding_side = "right"
    reference.pad_token = reference.eos_token
    return fast, reference


def encode_prompt(tokenizer: Any, reference: Any, prompt: PromptRecord,
                  sample_id: str, side: str) -> EncodedPrompt:
    """Encode the original input and map construction spans to full token spans."""
    encoded = tokenizer(prompt.text, add_special_tokens=False,
                        return_offsets_mapping=True, return_attention_mask=True,
                        truncation=False)
    ids = tuple(encoded["input_ids"])
    if ids != tuple(reference.encode(prompt.text, add_special_tokens=False)):
        raise ValueError(f"{sample_id}/{side}: fast token IDs differ from reference GPT-2; "
                         "check tokenizer revision and configuration.")
    offsets = tuple(tuple(span) for span in encoded["offset_mapping"])
    spans = {}
    for occurrence in prompt.occurrences:
        start, end = occurrence.char_span
        selected = [i for i, (left, right) in enumerate(offsets)
                    if left < end and right > start]
        if not selected or selected != list(range(selected[0], selected[-1] + 1)):
            raise ValueError(f"{sample_id}/{side}: cannot map {occurrence.role} "
                             f"character span {occurrence.char_span}; inspect offsets.")
        left, right = offsets[selected[0]][0], offsets[selected[-1]][1]
        if left > start or right < end or prompt.text[start:end] != occurrence.name:
            raise ValueError(f"{sample_id}/{side}: incomplete or incorrect "
                             f"{occurrence.role} occurrence span.")
        if prompt.text[left:start].strip() or prompt.text[end:right].strip():
            raise ValueError(f"{sample_id}/{side}: {occurrence.role} token span "
                             "includes non-name text; use a compatible tokenizer.")
        decoded = tokenizer.decode(list(ids[selected[0]:selected[-1] + 1]))
        if decoded.strip() != occurrence.name:
            raise ValueError(f"{sample_id}/{side}: decoded {occurrence.role} "
                             f"span {decoded!r} does not match {occurrence.name!r}.")
        spans[occurrence.role] = NameTokenSpan(
            occurrence.name, occurrence.field, occurrence.occurrence,
            occurrence.char_span, (selected[0], selected[-1] + 1))
    if set(spans) != {"IO", "S1", "S2"}:
        raise ValueError(f"{sample_id}/{side}: expected exactly IO/S1/S2 spans.")
    return EncodedPrompt(sample_id, side, prompt, ids,
                         tuple(tokenizer.convert_ids_to_tokens(list(ids))),
                         tuple(encoded["attention_mask"]), offsets, spans)


def check_answer(tokenizer: Any, reference: Any, encoded: EncodedPrompt,
                 name: str) -> AnswerCheck:
    """Check the actual leading-space continuation without changing the input."""
    continuation = " " + name
    joint = tuple(tokenizer.encode(encoded.prompt.text + continuation,
                                   add_special_tokens=False))
    if joint != tuple(reference.encode(encoded.prompt.text + continuation,
                                       add_special_tokens=False)):
        raise ValueError(f"{encoded.sample_id}/{encoded.side}: continuation IDs "
                         "differ between fast and reference GPT-2 tokenizers.")
    standalone = tuple(tokenizer.encode(continuation, add_special_tokens=False))
    prefix_preserved = joint[:len(encoded.input_ids)] == encoded.input_ids
    suffix = joint[len(encoded.input_ids):] if prefix_preserved else joint
    diagnostic = None
    if not prefix_preserved or suffix != standalone:
        status = "unsupported_boundary"
        diagnostic = "Continuation changes input tokenization; inspect the prompt boundary."
    elif len(suffix) != 1:
        status = "unsupported_multi_token" if suffix else "unsupported_empty"
        diagnostic = (f"Answer requires {len(suffix)} continuation tokens; "
                      "sequence-level evaluation is required. The example is retained.")
    else:
        status = "supported_single_token"
    if diagnostic:
        diagnostic = f"{encoded.sample_id}/{encoded.side}: {name!r}: {diagnostic}"
    return AnswerCheck(name, continuation, suffix,
                       tuple(tokenizer.convert_ids_to_tokens(list(suffix))),
                       standalone, prefix_preserved, status,
                       suffix[0] if status == "supported_single_token" else None,
                       diagnostic)


def pad_examples(examples: Sequence[EncodedPrompt], pad_token_id: int) -> EncodedBatch:
    """Right-pad one side using masks, without truncation or answer appending."""
    if not examples:
        raise ValueError("Cannot pad an empty batch.")
    width = max(len(example.input_ids) for example in examples)
    ids, masks = [], []
    for example in examples:
        padding = width - len(example.input_ids)
        ids.append(example.input_ids + (pad_token_id,) * padding)
        masks.append(example.attention_mask + (0,) * padding)
    return EncodedBatch(tuple(examples), tuple(ids), tuple(masks))


def encode_pair_batch(pairs: Sequence[PairRecord], tokenizer: Any,
                      reference: Any) -> PairBatch:
    base = [encode_prompt(tokenizer, reference, p.base, p.sample_id, "base") for p in pairs]
    source = [encode_prompt(tokenizer, reference, p.source, p.sample_id, "source") for p in pairs]
    batches = [pad_examples(examples, tokenizer.pad_token_id) for examples in (base, source)]
    for side, batch in zip(("base", "source"), batches):
        texts = [example.prompt.text for example in batch.examples]
        for encoder in (tokenizer, reference):
            actual = encoder(texts, padding=True, truncation=False, add_special_tokens=False,
                             return_attention_mask=True)
            if tuple(tuple(row) for row in actual["input_ids"]) != batch.input_ids or \
                    tuple(tuple(row) for row in actual["attention_mask"]) != batch.attention_mask:
                identifiers = [example.sample_id for example in batch.examples]
                raise ValueError(f"{identifiers}/{side}: actual batch tokenizer output differs "
                                 "from individually encoded right-padded inputs; check padding configuration.")
    return PairBatch(tuple(pairs), batches[0], batches[1])


def encoded_to_dict(encoded: EncodedPrompt) -> dict[str, Any]:
    """Serialize unpadded tokens and complete occurrence metadata for the audit."""
    return {
        "text": encoded.prompt.text,
        "pattern": encoded.prompt.pattern,
        "template_id": encoded.prompt.template_id,
        "io_name": encoded.prompt.io_name,
        "subject_name": encoded.prompt.subject_name,
        "input_ids": encoded.input_ids,
        "readable_tokens": encoded.readable_tokens,
        "attention_mask": encoded.attention_mask,
        "offsets": encoded.offsets,
        "valid_length": encoded.valid_length,
        "name_spans": {role: asdict(span) for role, span in encoded.name_spans.items()},
    }
