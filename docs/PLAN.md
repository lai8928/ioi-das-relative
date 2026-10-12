# Implementation plan and contracts

The current authorized checkpoint covers Phase 0 and Phase 1 of `CODEX_IOI_DAS_BOOTSTRAP.txt`. Later phases require a new request. The implementation separates `find_variable_at()` into small modules so sampling, token positions, interventions, optimization, evaluation, and plotting each have one responsibility.

## Modules

| Module under `src/ioi_das/` | Responsibility | Phase |
| --- | --- | --- |
| `data.py` | Adapt original prompt construction and POSITION sampling; retain roles, occurrence spans, counterfactual labels, validated serialization, and fixed splits. | 1 |
| `tokenization.py` | Load the pinned GPT-2 fast/slow tokenizers, check token IDs, encode full prompts, map character spans, right-pad independently, and check full answer continuations. | 1 |
| `positions.py` | Resolve named anchors and offsets into per-example indices with actionable failures; retain separate base/source arrays and masks. | 1 |
| `checks.py` | Run independent hand-derived role, occurrence, unequal-length, padding, offset, and multi-token-answer checks with the real tokenizer. | 1 |
| `audit.py` | Verify provenance and the dataset manifest before reuse; audit saved pairs and produce records, a summary, and validation evidence. | 1 |
| `cli.py` | Provide the runnable audit entry point and resolve configuration/artifact paths. | 1 |
| `intervention.py` | Build the pyvene intervention and share a forward function between training and evaluation. | 2, planned |
| `train.py` | Optimize alignment parameters with frozen model weights and intact intervention gradients. | 2, planned |
| `evaluate.py` | Compute factual IOI accuracy and counterfactual IIA; save full predictions and read logits at each base's last valid token. | 2, planned |
| `experiment.py` | Run one condition or an independent sweep using the same saved data. | 2–3, planned |
| `plot.py` | Read saved results and render figures without training. | 3, planned |

Only modules needed for the current checkpoint are created. The original notebook is a preserved reference; it is not the implementation or evidence of this project's results.

## Fixed data contract

Training uses base patterns ABB/BAB crossed with source patterns ABB/BAB, with 50 pairs per combination: 200 pairs in total. Test uses ABB to BAB and BAB to ABB, with 50 pairs each: 100 pairs. Names, objects, and places retain their original order and are divided at `len(asset) // 2`; templates 0–1 are training templates and templates 2–14 are test templates. The 99 names therefore split into 49 training names and 50 test names; objects and places each split 4/4.

For each base, source resampling preserves the mapping of pattern symbols to names, the template, object, and place. The source is derived from its base according to upstream `resample_pattern()` rules. Fixed JSONL files are generated once and reused across conditions. The manifest records seed, adapted generator revision, upstream commit, tokenizer identity/revision, and dataset hashes. A saved seed is not a substitute for saved examples, and these files are not claimed to be historical samples.

Each pair retains a stable ID and split, base/source input text and pattern, template identifier and construction values, factual IO and subject names, first/second NAME order metadata, occurrence-level character spans, and the counterfactual answer as text. Encoding retains token IDs as well as readable tokens and complete name spans so another tokenizer can later use the same textual data.

POSITION counterfactual labels apply the source position variable to the base names. If the first subject occurrence has the same NAME-order index in base and source, the answer is the base IO; if that index differs, the answer is the base subject. The source answer must not be substituted for that rule. Upstream `io_pos` and `s1_pos` refer to NAME order (0 or 1), not tensor coordinates.

Upstream `sample_one()` uses `list(set(pattern))`, so hash-dependent set iteration changes the symbol-to-name assignment for an identical random seed. The adaptation uses first-occurrence symbol order, preserving the sampling distribution and pair construction while making new saved samples deterministic. It does not reproduce a historical sample sequence.

## Token and position contract

Three separate concepts govern later experiments:

- `target_variable="position"` is the high-level causal variable and counterfactual rule.
- `intervention_location` selects an activation anchor and offset within each input.
- `readout_location` is the last valid token of each base input.

Name character spans are captured during construction and mapped using fast tokenizer offsets. The complete token span of each occurrence is retained. The initial scalar name anchor selects the span's last token. Name lookup must not search for the first matching token ID because repeated names have different roles and occurrences.

| Anchor | Meaning within one prompt |
| --- | --- |
| `IO` / `GOAL_NAME` | The occurrence of that input's factual indirect-object name. |
| `S1` | The subject's first occurrence. |
| `S2` | The subject's second occurrence. |
| `END` / `N` | Last non-padding input token. |
| `N-k` | `END` with offset `-k`. |

Inputs are right-padded. `N = sum(attention_mask) - 1`, and offsets are checked against that input's valid length. Base and source positions are resolved independently: lengths 18 and 22 have `N-1` indices 16 and 20. Each side's arrays and attention masks remain separate. Later next-token evaluation reads logits at each base `N`, including when the intervention is at `N-2`.

Prompts retain their original variable lengths. No 18-token assertion, truncation, prompt filtering, answer appending, or rewriting is permitted. Invalid anchors and offsets fail with sample IDs, the requested location, valid bounds, and corrective guidance.

Initial answer evaluation requires a single token in the actual continuation, including its leading space and prompt boundary. Full factual and counterfactual continuation IDs are retained. Multi-token answers and boundary incompatibilities are reported as unsupported evaluation cases; examples are preserved and no first-token fallback is allowed.

## Phase acceptance criteria

### Phase 0: extract and document

Retrieve exactly the eight specified sources at commit `9e333904dcf9e597ca76170010d17f4d4580de8d`, preserve their original bytes and repository-relative paths, and record hashes, dates, attribution, and source-to-module mapping. Inspect dependencies before adding any transitive source. Inspect the existing environment and record the interpreter and installed versions. Create README, durable AGENTS rules, plan, status, and provenance documentation.

### Phase 1: position audit

Implement fixed data generation/loading, encoding, named/relative position resolution, and the audit CLI without loading model weights. Audit all 200 training and 100 test pairs using the actual pinned GPT-2 tokenizer when available. Save a dataset manifest, per-pair output, an English summary, runtime environment details, and focused-check evidence. Include different lengths and both ABB/BAB patterns in the readable subset.

Focused checks must independently verify hand-checked roles and POSITION counterfactuals; distinguish the subject's first and second occurrences; compare batch and individual tokenization; check a separately identified synthetic unequal-length pair; verify `END`, `END-1`, and `END-2` at explicit expected indices in mixed-length right-padded batches; diagnose invalid offsets and multi-token answers without silent drops. Synthetic checks supplement the original generated data and must be labeled accordingly. Runtime blockers must identify the exact unfulfilled criterion and resume command rather than presenting fixture checks as a real-tokenizer audit.

The real-tokenizer audit has completed over all 300 original-rule pairs, with 600 fast/slow input comparisons, 1,800 continuation comparisons, 2,400 batch/individual position comparisons, and no unsupported original answers. Sampled training lengths are 15/19 and test lengths are 14/15/16/17/18/20; synthetic checks supply unequal-length 18/22 coverage. An audit rerun from `/tmp` with the absolute config path verified saved-dataset reuse. Detailed final evidence and test results belong in `docs/STATUS.md` and `outputs/audit/`.

### Phase 2: one DAS condition, planned only

Use saved original data with GPT-2, `block_output`, layer 8, `END/N`, rank 1, and `target_variable="position"`. Extract the upstream optimizer/scheduler behavior explicitly and document intentional fixes. Share intervention-forward logic between training and evaluation. Save configuration, losses, counts, full predictions, and alignment weights. Verify frozen language-model weights, an identity intervention, gradients, and batch-versus-individual behavior on variable lengths. Remove hooks and per-condition state. Distinguish a short smoke run from the configured full experiment.

### Phase 3: eight independent conditions, planned only

Cross layers 7 and 8 with `GOAL_NAME`, `N`, `N-1`, and `N-2`. Reuse fixed examples, record initialization seeds, and independently train each condition. Save actual per-example indices alongside semantic labels. Plot END-relative IIA in explicit offset order with separate `GOAL_NAME` display. Explain that IO anchors use known factual task roles and that END-relative locations align distance from the end rather than a guaranteed syntactic role.

### Phase 4: expanded experiments, planned only

Expand to layers 0–11 and offsets `N-4` through `N`, then add checkpointing, resume, and failure analysis. Consider rank, controlled data variation, or larger models one factor at a time. Preserve the held-out test split; create separate validation data before tuning or selecting conditions.

Future results must come from this project's saved runs. Do not use tutorial CSVs or notebook outputs as experiment results. Save IIA numerators/denominators and full precision, rounding only for display. The upstream `kl_div` implementation averages target logits and is not a KL divergence; check or correct that metric before adopting it.
