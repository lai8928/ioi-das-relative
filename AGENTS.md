# Project rules

- Read `CODEX_IOI_DAS_BOOTSTRAP.txt` and `docs/STATUS.md` before continuing work.
- Write source, identifiers, comments, docstrings, CLI output, configuration, and documentation in English. Explain progress and findings to the user in Traditional Chinese.
- Work in this project root. Preserve existing work. Do not create a remote repository or push without authorization.
- The current authorization is Phase 0/1 only: extract sources, save original POSITION samples, tokenize, resolve positions, and audit. Do not load model weights, train DAS, or implement later phases without a new request.
- Prefer the discovered existing `ioi-das-v2` Conda interpreter. Do not install packages or change the Python, CUDA, or system environment during bootstrap.
- Keep the eight pinned upstream originals byte-for-byte unchanged under `vendor/pyvene_upstream/`; preserve provenance and the activation-patching-illusion credit. Put adaptations in `src/ioi_das/`. Treat pyvene as an external versioned dependency.
- Preserve POSITION pairing counts, original asset halves, template split, base-to-source resampling, and counterfactual role logic. Save datasets once and verify their manifest before reuse. Do not call them historical samples.
- Track occurrence-level character spans during construction. Use fast tokenizer offsets and retain full name token spans; a scalar name anchor selects the last token of that occurrence.
- Resolve base and source positions independently. `GOAL_NAME` means factual IO in each input; `N` means its last valid input token. Keep separate masks and position arrays. Readout always uses base `N`.
- Do not truncate, discard, rewrite, or append answers to prompts. Reject invalid positions with sample IDs. Preserve and report unsupported multi-token answer continuations without taking only the first token.
- Resolve artifact paths against explicit config/project locations. Keep generated samples in `data/generated/` and outputs in `outputs/`.
- Run focused meaningful checks and the real tokenizer audit when supported. Record actual commands, versions, hashes, evidence, blockers, and the exact next command in `docs/STATUS.md`.
