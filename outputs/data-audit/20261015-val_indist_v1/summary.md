# Position audit

Real-tokenizer position audit passed.

- Registered dataset: val_indist_v1.
- Saved pair counts: {'validation': 200}.
- Saved dataset reused: True.
- Fast/reference GPT-2 comparisons: {'inputs': 400, 'continuations': 1200, 'batched_sides': 20}.
- Batch/individual position comparisons: 1600.
- Unsupported answer checks: 0 (examples retained).
- Unequal-length original pairs: 0.
- Focused real-tokenizer checks passed, including synthetic unequal-length 18/22-token inputs.
- No model weights loaded and no DAS training started.

## Original-rule prompt lengths

- validation: {'base': {15: 106, 19: 94}, 'source': {15: 106, 19: 94}}

## Original-rule example subset

Indices are zero-based. GOAL_NAME is each input's factual IO; name anchors use the last span token.

| ID | Base/source patterns | Lengths | GOAL_NAME base/source | N base/source | N-1 base/source | N-2 base/source | Base IO / CF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| validation-0000 | ABB/BAB | 15/15 | 2/4 | 14/14 | 13/13 | 12/12 | Brittany / Joseph |
| validation-0002 | ABB/BAB | 19/19 | 2/4 | 18/18 | 17/17 | 16/16 | Eric / Sarah |
| validation-0050 | BAB/ABB | 19/19 | 4/2 | 18/18 | 17/17 | 16/16 | Amber / Megan |
| validation-0051 | BAB/ABB | 15/15 | 4/2 | 14/14 | 13/13 | 12/12 | Justin / Brian |

### validation-0000

Base: Then, Brittany and Joseph went to the school. Joseph gave a basketball to

Source: Then, Joseph and Brittany went to the school. Joseph gave a basketball to

### validation-0002

Base: Then, Eric and Sarah had a lot of fun at the school. Sarah gave a ring to

Source: Then, Sarah and Eric had a lot of fun at the school. Sarah gave a ring to

### validation-0050

Base: Then, Megan and Amber had a lot of fun at the store. Megan gave a ring to

Source: Then, Amber and Megan had a lot of fun at the store. Megan gave a ring to

### validation-0051

Base: Then, Brian and Justin went to the restaurant. Brian gave a bone to

Source: Then, Justin and Brian went to the restaurant. Brian gave a bone to

## Synthetic focused evidence

Synthetic data is excluded from all registered dataset pairs. The mixed batch has base lengths [18, 22] and source lengths [22, 18]. Expected N-1 arrays are base [16, 20] and source [20, 16]. END/END-1/END-2 match individual tokenization. Repeated subjects map to distinct occurrences. Mary Jane retains both continuation tokens and is diagnosed as unsupported for single-token evaluation. See focused_checks.json for exact texts, all expected indices, and invalid-offset diagnostics.
