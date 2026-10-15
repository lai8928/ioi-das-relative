# Dataset registry

Every dataset used by an experiment is listed here. Datasets are generated
once, hashed, and never rewritten; a changed dataset gets a new versioned
name. Configs refer to datasets by name.

| Name | Split | Pairs | Path | SHA-256 | Purpose |
| --- | --- | ---: | --- | --- | --- |
| `legacy_v1` | train | 200 | `data/generated/train.jsonl` | `3867b316d469df4b4c2d80136324c8cda4e001c617c584c30703283ad75db346` | Original POSITION training pairs: ABB/BAB × ABB/BAB, 50 per combination |
| `legacy_v1` | test | 100 | `data/generated/test.jsonl` | `dd7e6de16f4ccb0e295086ba97d80abf8b6bcda01852f1ee8bb61ff3154f8ded` | Original held-out pairs: ABB→BAB and BAB→ABB, 50 each. Inspected in earlier runs, so descriptive only |
| `val_indist_v1` | validation | 200 | `data/generated/m3_validation_v1/validation.jsonl` (branch `m3-complete-20261015`, not yet on `main`) | `f62945c14803c2d9b8832b736bf5dd0d79226ea2e5fa7727b5aaa32aa54ba8e5` | Fixed in-distribution validation for selection: ABB→BAB and BAB→ABB, 100 each; no prompt or semantic-group overlap with `legacy_v1` |

## Generation records

- `legacy_v1`: manifest `data/generated/manifest.json`; generator revision
  `ioi-position-v1-ordered-symbols`, seed 42, upstream pyvene commit
  `9e333904dcf9e597ca76170010d17f4d4580de8d`.
- `val_indist_v1`: manifest `data/generated/m3_validation_v1/manifest.json` on
  branch `m3-complete-20261015`; candidate seeds 314159–314161, one prompt
  overlap rejected, training resource pools and templates 0/1.
