"""Focused real-tokenizer checks, including explicitly synthetic research exclusions."""

from .data import PairRecord, build_prompt, counterfactual_names
from .positions import PositionError, resolve_pair_positions, resolve_position
from .tokenization import check_answer, encode_pair_batch, encode_prompt


SHORT_TEMPLATE = "Then, {name_A} and {name_B} went to the {place}. {name_C} gave a {object} to"
LONG_TEMPLATE = "Then, {name_A} and {name_B} had a lot of fun at the {place}. {name_C} gave a {object} to"


def run_focused_checks(tokenizer, reference) -> dict:
    """Use literal expected indices and hand-derived roles, separate from sampled data."""
    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    base = build_prompt(("Alice", "Bob", "Bob"), SHORT_TEMPLATE, 0,
                        "ABB", "ring", "small local grocery store")
    source = build_prompt(("Bob", "Alice", "Bob"), LONG_TEMPLATE, 1,
                          "BAB", "ring", "small local grocery store")
    require((base.io_name, base.subject_name, base.io_pos, base.s1_pos) ==
            ("Alice", "Bob", 0, 1), "Hand-checked ABB roles differ.")
    require((source.io_name, source.subject_name, source.io_pos, source.s1_pos) ==
            ("Alice", "Bob", 1, 0), "Hand-checked BAB roles differ.")
    require(counterfactual_names(base, source) == ("Bob", "Alice"),
            "ABB->BAB should select the second base name.")
    require(counterfactual_names(base, base) == ("Alice", "Bob"),
            "ABB->ABB should retain the factual base IO.")
    require(counterfactual_names(source, base) == ("Bob", "Alice"),
            "BAB->ABB should select the first base name.")
    require(counterfactual_names(source, source) == ("Alice", "Bob"),
            "BAB->BAB should retain the factual base IO.")
    distinct_source = build_prompt(("Carol", "Dave", "Carol"), SHORT_TEMPLATE,
                                   0, "BAB", "ring", "store")
    require(counterfactual_names(base, distinct_source) == ("Bob", "Alice"),
            "POSITION must apply source order to base names, not source answer Dave.")
    pair = PairRecord("synthetic-unequal", "synthetic", base, source, "Bob", "Alice")
    reverse = PairRecord("synthetic-reverse", "synthetic", source, base, "Bob", "Alice")
    batch = encode_pair_batch([pair, reverse], tokenizer, reference)
    require([e.valid_length for e in batch.base.examples] == [18, 22],
            "Pinned GPT-2 synthetic input lengths must be exactly 18 and 22.")
    expected = {
        "GOAL_NAME": {"base": [2, 4], "source": [4, 2]},
        "S1": {"base": [4, 2], "source": [2, 4]},
        "S2": {"base": [13, 17], "source": [17, 13]},
        "N": {"base": [17, 21], "source": [21, 17]},
        "N-1": {"base": [16, 20], "source": [20, 16]},
        "N-2": {"base": [15, 19], "source": [19, 15]},
        "END": {"base": [17, 21], "source": [21, 17]},
        "END-1": {"base": [16, 20], "source": [20, 16]},
        "END-2": {"base": [15, 19], "source": [19, 15]},
    }
    actual = {}
    for location, indices in expected.items():
        actual[location] = resolve_pair_positions(batch, location)
        require(actual[location] == indices, f"Unexpected mixed-batch indices for {location}.")
        for side in ("base", "source"):
            examples = getattr(batch, side).examples
            for i, example in enumerate(examples):
                individual = encode_prompt(tokenizer, reference, example.prompt,
                                           example.sample_id, side)
                require(resolve_position(individual, location) == indices[side][i],
                        f"Batch and individual {side}/{location} positions differ.")
    require(batch.base.attention_mask[0] == (1,) * 18 + (0,) * 4,
            "Short base must receive exactly four right-padding mask zeros.")
    require(batch.source.attention_mask[1] == (1,) * 18 + (0,) * 4,
            "Short source must receive its own right-padding mask.")
    base_encoded = batch.base.examples[0]
    require(base_encoded.name_spans["S1"].char_span != base_encoded.name_spans["S2"].char_span,
            "Repeated subject occurrences must have distinct character spans.")
    require(base_encoded.name_spans["S1"].token_span == (4, 5) and
            base_encoded.name_spans["S2"].token_span == (13, 14),
            "Repeated Bob must map to first and second occurrence, respectively.")
    diagnostics = []
    for invalid in ("N-18", "N+1", "UNKNOWN", "IO-3"):
        try:
            resolve_position(base_encoded, invalid)
        except PositionError as exc:
            require("synthetic-unequal/base" in str(exc), "Position diagnostic lost sample ID.")
            diagnostics.append(str(exc))
        else:
            raise AssertionError(f"Invalid position {invalid} was accepted.")
    try:
        resolve_position(base_encoded, "N", (0,) + (1,) * 18)
    except PositionError as exc:
        diagnostics.append(str(exc))
    else:
        raise AssertionError("Left-padded mask was accepted.")
    multi_prompt = build_prompt(("Mary Jane", "Bob", "Bob"), SHORT_TEMPLATE,
                                0, "ABB", "ring", "store")
    multi_encoded = encode_prompt(tokenizer, reference, multi_prompt,
                                  "synthetic-multi-token", "base")
    require(multi_encoded.name_spans["IO"].token_span == (2, 4) and
            resolve_position(multi_encoded, "GOAL_NAME") == 3,
            "Multi-token name anchor must use the last token of the full span.")
    answer = check_answer(tokenizer, reference, multi_encoded, "Mary Jane")
    require(answer.status == "unsupported_multi_token" and answer.token_id is None and
            answer.token_ids == (5335, 12091) and answer.prefix_preserved,
            "Multi-token continuation must retain all tokens and remain unsupported.")
    single = check_answer(tokenizer, reference, base_encoded, "Alice")
    require(single.status == "supported_single_token" and single.prefix_preserved,
            "Single-token continuation must preserve the original input boundary.")
    return {
        "status": "passed",
        "data_origin": "synthetic; not included in the 200/100 original-rule samples",
        "checks": ["four hand-derived ABB/BAB POSITION cases",
                   "different-name source uses base names",
                   "repeated subject occurrence spans",
                   "18/22 unequal lengths with separate base/source masks",
                   "explicit mixed-batch and individual indices for nine locations",
                   "invalid locations, offsets, and left padding diagnosed",
                   "full multi-token name span and unsupported answer retained",
                   "leading-space prompt continuation boundary"],
        "synthetic_texts": {"base": base.text, "source": source.text},
        "valid_lengths": {"base": [18, 22], "source": [22, 18]},
        "expected_indices": expected,
        "actual_indices": actual,
        "invalid_position_diagnostics": diagnostics,
        "multi_token_answer": {
            "name": answer.name, "token_ids": answer.token_ids,
            "status": answer.status, "token_id": answer.token_id,
            "diagnostic": answer.diagnostic,
        },
    }
