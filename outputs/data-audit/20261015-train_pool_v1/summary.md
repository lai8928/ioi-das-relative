# Position audit

Real-tokenizer position audit passed.

- Registered dataset: train_pool_v1.
- Saved pair counts: {'train': 5000}.
- Saved dataset reused: True.
- Fast/reference GPT-2 comparisons: {'inputs': 10000, 'continuations': 30000, 'batched_sides': 500}.
- Batch/individual position comparisons: 40000.
- Unsupported answer checks: 0 (examples retained).
- Unequal-length original pairs: 0.
- Focused real-tokenizer checks passed, including synthetic unequal-length 18/22-token inputs.
- No model weights loaded and no DAS training started.

## Original-rule prompt lengths

- train: {'base': {15: 2452, 19: 2548}, 'source': {15: 2452, 19: 2548}}

## Original-rule example subset

Indices are zero-based. GOAL_NAME is each input's factual IO; name anchors use the last span token.

| ID | Base/source patterns | Lengths | GOAL_NAME base/source | N base/source | N-1 base/source | N-2 base/source | Base IO / CF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| train-0000 | ABB/ABB | 15/15 | 2/2 | 14/14 | 13/13 | 12/12 | Joshua / Joshua |
| train-0002 | ABB/ABB | 19/19 | 2/2 | 18/18 | 17/17 | 16/16 | Amber / Amber |
| train-2409 | BAB/ABB | 19/19 | 4/2 | 18/18 | 17/17 | 16/16 | Danielle / Joshua |
| train-2410 | BAB/ABB | 15/15 | 4/2 | 14/14 | 13/13 | 12/12 | Melissa / Sarah |

### train-0000

Base: Then, Joshua and Nicole went to the garden. Nicole gave a ring to

Source: Then, Joshua and Nicole went to the garden. Nicole gave a ring to

### train-0002

Base: Then, Amber and Timothy had a lot of fun at the garden. Timothy gave a basketball to

Source: Then, Amber and Timothy had a lot of fun at the garden. Timothy gave a basketball to

### train-2409

Base: Then, Joshua and Danielle had a lot of fun at the garden. Joshua gave a kiss to

Source: Then, Danielle and Joshua had a lot of fun at the garden. Joshua gave a kiss to

### train-2410

Base: Then, Sarah and Melissa went to the store. Sarah gave a kiss to

Source: Then, Melissa and Sarah went to the store. Sarah gave a kiss to

## Synthetic focused evidence

Synthetic data is excluded from all registered dataset pairs. The mixed batch has base lengths [18, 22] and source lengths [22, 18]. Expected N-1 arrays are base [16, 20] and source [20, 16]. END/END-1/END-2 match individual tokenization. Repeated subjects map to distinct occurrences. Mary Jane retains both continuation tokens and is diagnosed as unsupported for single-token evaluation. See focused_checks.json for exact texts, all expected indices, and invalid-offset diagnostics.
