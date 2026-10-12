# Position audit

Full real-tokenizer Phase 1 audit passed.

- Original-rule samples: 200 training / 100 test pairs.
- Saved dataset reused: True.
- Fast/reference GPT-2 comparisons: {'inputs': 600, 'continuations': 1800, 'batched_sides': 30}.
- Batch/individual position comparisons: 2400.
- Unsupported answer checks: 0 (examples retained).
- Unequal-length original pairs: 0.
- Focused real-tokenizer checks passed, including synthetic unequal-length 18/22-token inputs.
- No model weights loaded and no DAS training started.

## Original-rule prompt lengths

- train: {'base': {15: 87, 19: 113}, 'source': {15: 87, 19: 113}}
- test: {'base': {14: 17, 15: 45, 16: 7, 17: 11, 18: 10, 20: 10}, 'source': {14: 17, 15: 45, 16: 7, 17: 11, 18: 10, 20: 10}}

## Original-rule example subset

Indices are zero-based. GOAL_NAME is each input's factual IO; name anchors use the last span token.

| ID | Base/source patterns | Lengths | GOAL_NAME base/source | N base/source | N-1 base/source | N-2 base/source | Base IO / CF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| train-0000 | ABB/ABB | 15/15 | 2/2 | 14/14 | 13/13 | 12/12 | Christopher / Christopher |
| train-0002 | ABB/ABB | 19/19 | 2/2 | 18/18 | 17/17 | 16/16 | Jessica / Jessica |
| train-0100 | BAB/ABB | 15/15 | 4/2 | 14/14 | 13/13 | 12/12 | Elizabeth / Amanda |
| train-0101 | BAB/ABB | 19/19 | 4/2 | 18/18 | 17/17 | 16/16 | Eric / Amy |
| test-0000 | ABB/BAB | 15/15 | 1/3 | 14/14 | 13/13 | 12/12 | Rebecca / Jamie |
| test-0003 | ABB/BAB | 14/14 | 2/4 | 13/13 | 12/12 | 11/11 | Kelly / Mary |
| test-0008 | ABB/BAB | 16/16 | 3/5 | 15/15 | 14/14 | 13/13 | Angela / Jose |
| test-0050 | BAB/ABB | 16/16 | 5/3 | 15/15 | 14/14 | 13/13 | Nathan / Bryan |

### train-0000

Base: Then, Christopher and Jeffrey went to the garden. Jeffrey gave a bone to

Source: Then, Christopher and Jeffrey went to the garden. Jeffrey gave a bone to

### train-0002

Base: Then, Jessica and Christopher had a lot of fun at the garden. Christopher gave a ring to

Source: Then, Jessica and Christopher had a lot of fun at the garden. Christopher gave a ring to

### train-0100

Base: Then, Amanda and Elizabeth went to the school. Amanda gave a kiss to

Source: Then, Elizabeth and Amanda went to the school. Amanda gave a kiss to

### train-0101

Base: Then, Amy and Eric had a lot of fun at the school. Amy gave a basketball to

Source: Then, Eric and Amy had a lot of fun at the school. Amy gave a basketball to

### test-0000

Base: While Rebecca and Jamie were working at the office, Jamie gave a snack to

Source: While Jamie and Rebecca were working at the office, Jamie gave a snack to

### test-0003

Base: Then, Kelly and Mary had a long argument. Afterwards Mary said to

Source: Then, Mary and Kelly had a long argument. Afterwards Mary said to

### test-0008

Base: Afterwards, Angela and Jose went to the house. Jose gave a drink to

Source: Afterwards, Jose and Angela went to the house. Jose gave a drink to

### test-0050

Base: Afterwards, Bryan and Nathan went to the station. Bryan gave a snack to

Source: Afterwards, Nathan and Bryan went to the station. Bryan gave a snack to

## Synthetic focused evidence

Synthetic data is excluded from the 200/100 sampled pairs. The mixed batch has base lengths [18, 22] and source lengths [22, 18]. Expected N-1 arrays are base [16, 20] and source [20, 16]. END/END-1/END-2 match individual tokenization. Repeated subjects map to distinct occurrences. Mary Jane retains both continuation tokens and is diagnosed as unsupported for single-token evaluation. See focused_checks.json for exact texts, all expected indices, and invalid-offset diagnostics.
