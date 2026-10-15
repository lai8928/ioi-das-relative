# model-scale / gpt2-medium

Run kind: **smoke**; run status: **complete**.

Config SHA-256: `eabd40352b8126963b57b7f438288ec20e468af014f3b0ace2e7140aaa0a09f3`.

Conditions: complete=1.

This is a smoke run for execution checks; it is not a full experimental result.

| Condition | Status | Initial train IIA | Train IIA | No intervention train IIA | Initial validation IIA | Validation IIA | No intervention validation IIA |
| --- | --- | --- | --- | --- | --- | --- | --- |
| conditions/intervention.layer=12/seed=42 | complete | 9/20 = 0.45 | 9/20 = 0.45 | 9/20 = 0.45 | 0/4 = 0.0 | 0/4 = 0.0 | 0/4 = 0.0 |

Full-precision metrics and exact counts are saved in `conditions.csv`.
Missing metrics are shown as —; failed and pending conditions remain in the table.

Per-layer means and sample SD across seeds are saved in `layer_summary.csv`.
Seed SD describes variation across seeds; it is not a confidence interval.
A single available seed has no sample SD. Incomplete layers are flagged in the CSV.

Per-pairing and target-change groups (counts summed across seeds; means give equal weight to each seed):

| Layer | Split | Group | IIA | No-intervention IIA |
| --- | --- | --- | --- | --- |
| 12 | initial_train | ABB->ABB | 4/5; mean 0.8 | 4/5; mean 0.8 |
| 12 | initial_train | ABB->BAB | 0/5; mean 0.0 | 0/5; mean 0.0 |
| 12 | initial_train | BAB->ABB | 0/5; mean 0.0 | 0/5; mean 0.0 |
| 12 | initial_train | BAB->BAB | 5/5; mean 1.0 | 5/5; mean 1.0 |
| 12 | initial_train | switch_required | 0/10; mean 0.0 | 0/10; mean 0.0 |
| 12 | initial_train | unchanged_target | 9/10; mean 0.9 | 9/10; mean 0.9 |
| 12 | train | ABB->ABB | 4/5; mean 0.8 | 4/5; mean 0.8 |
| 12 | train | ABB->BAB | 0/5; mean 0.0 | 0/5; mean 0.0 |
| 12 | train | BAB->ABB | 0/5; mean 0.0 | 0/5; mean 0.0 |
| 12 | train | BAB->BAB | 5/5; mean 1.0 | 5/5; mean 1.0 |
| 12 | train | switch_required | 0/10; mean 0.0 | 0/10; mean 0.0 |
| 12 | train | unchanged_target | 9/10; mean 0.9 | 9/10; mean 0.9 |
| 12 | initial_validation | ABB->ABB | 0/0; mean — | 0/0; mean — |
| 12 | initial_validation | ABB->BAB | 0/2; mean 0.0 | 0/2; mean 0.0 |
| 12 | initial_validation | BAB->ABB | 0/2; mean 0.0 | 0/2; mean 0.0 |
| 12 | initial_validation | BAB->BAB | 0/0; mean — | 0/0; mean — |
| 12 | initial_validation | switch_required | 0/4; mean 0.0 | 0/4; mean 0.0 |
| 12 | initial_validation | unchanged_target | 0/0; mean — | 0/0; mean — |
| 12 | validation | ABB->ABB | 0/0; mean — | 0/0; mean — |
| 12 | validation | ABB->BAB | 0/2; mean 0.0 | 0/2; mean 0.0 |
| 12 | validation | BAB->ABB | 0/2; mean 0.0 | 0/2; mean 0.0 |
| 12 | validation | BAB->BAB | 0/0; mean — | 0/0; mean — |
| 12 | validation | switch_required | 0/4; mean 0.0 | 0/4; mean 0.0 |
| 12 | validation | unchanged_target | 0/0; mean — | 0/0; mean — |

![Validation IIA by layer](figures/validation_by_layer.svg)

![Train and validation IIA by layer](figures/train_validation_by_layer.svg)

![Saved IIA by condition](figures/iia.svg)
