# intervention-sites / gpt2-small-l7h3-k

Run kind: **full**; run status: **complete**.

Config SHA-256: `68ea1b15d4b9615feb9d35f518772f55deea289e9f0c95b4f2e588307282ee50`.

Conditions: complete=3.

The legacy test set is a descriptive benchmark, previously inspected in earlier runs.
It is not an untouched held-out test.

Selected layer: **7**; metric: `validation_iia`.
The choice was locked in `selection.json` before post-lock evaluation.

| Condition | Status | Initial train IIA | Train IIA | No intervention train IIA | Initial validation IIA | Validation IIA | No intervention validation IIA | Test IIA (descriptive) | No intervention test IIA (descriptive) | Post-lock status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conditions/seed=42 | complete | 94/200 = 0.47 | 94/200 = 0.47 | 94/200 = 0.47 | 0/200 = 0.0 | 0/200 = 0.0 | 0/200 = 0.0 | 0/100 = 0.0 | 0/100 = 0.0 | complete |
| conditions/seed=43 | complete | 94/200 = 0.47 | 94/200 = 0.47 | 94/200 = 0.47 | 0/200 = 0.0 | 0/200 = 0.0 | 0/200 = 0.0 | 0/100 = 0.0 | 0/100 = 0.0 | complete |
| conditions/seed=44 | complete | 94/200 = 0.47 | 94/200 = 0.47 | 94/200 = 0.47 | 0/200 = 0.0 | 0/200 = 0.0 | 0/200 = 0.0 | 0/100 = 0.0 | 0/100 = 0.0 | complete |

Full-precision metrics and exact counts are saved in `conditions.csv`.
Missing metrics are shown as —; failed and pending conditions remain in the table.

Per-layer means and sample SD across seeds are saved in `layer_summary.csv`.
Seed SD describes variation across seeds; it is not a confidence interval.
A single available seed has no sample SD. Incomplete layers are flagged in the CSV.

Per-pairing and target-change groups (counts summed across seeds; means give equal weight to each seed):

| Layer | Split | Group | IIA | No-intervention IIA |
| --- | --- | --- | --- | --- |
| 7 | initial_train | ABB->ABB | 138/150; mean 0.92 | 138/150; mean 0.92 |
| 7 | initial_train | ABB->BAB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 7 | initial_train | BAB->ABB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 7 | initial_train | BAB->BAB | 144/150; mean 0.96 | 144/150; mean 0.96 |
| 7 | initial_train | switch_required | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 7 | initial_train | unchanged_target | 282/300; mean 0.94 | 282/300; mean 0.94 |
| 7 | train | ABB->ABB | 138/150; mean 0.92 | 138/150; mean 0.92 |
| 7 | train | ABB->BAB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 7 | train | BAB->ABB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 7 | train | BAB->BAB | 144/150; mean 0.96 | 144/150; mean 0.96 |
| 7 | train | switch_required | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 7 | train | unchanged_target | 282/300; mean 0.94 | 282/300; mean 0.94 |
| 7 | initial_validation | ABB->ABB | 0/0; mean — | 0/0; mean — |
| 7 | initial_validation | ABB->BAB | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 7 | initial_validation | BAB->ABB | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 7 | initial_validation | BAB->BAB | 0/0; mean — | 0/0; mean — |
| 7 | initial_validation | switch_required | 0/600; mean 0.0 | 0/600; mean 0.0 |
| 7 | initial_validation | unchanged_target | 0/0; mean — | 0/0; mean — |
| 7 | validation | ABB->ABB | 0/0; mean — | 0/0; mean — |
| 7 | validation | ABB->BAB | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 7 | validation | BAB->ABB | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 7 | validation | BAB->BAB | 0/0; mean — | 0/0; mean — |
| 7 | validation | switch_required | 0/600; mean 0.0 | 0/600; mean 0.0 |
| 7 | validation | unchanged_target | 0/0; mean — | 0/0; mean — |
| 7 | test | ABB->ABB | 0/0; mean — | 0/0; mean — |
| 7 | test | ABB->BAB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 7 | test | BAB->ABB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 7 | test | BAB->BAB | 0/0; mean — | 0/0; mean — |
| 7 | test | switch_required | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 7 | test | unchanged_target | 0/0; mean — | 0/0; mean — |

![Validation IIA by layer](figures/validation_by_layer.svg)

![Train and validation IIA by layer](figures/train_validation_by_layer.svg)

![Post-lock test IIA by layer](figures/test_by_layer.svg)

![Saved IIA by condition](figures/iia.svg)
