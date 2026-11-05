# intervention-sites / gpt2-small-l9h9-q

Run kind: **full**; run status: **complete**.

Config SHA-256: `4e11a8638bbbb2e08d3601f4ccaceedbe167c50d282ededaeceabaccdb8fb6d5`.

Conditions: complete=3.

The legacy test set is a descriptive benchmark, previously inspected in earlier runs.
It is not an untouched held-out test.

Selected layer: **9**; metric: `validation_iia`.
The choice was locked in `selection.json` before post-lock evaluation.

| Condition | Status | Initial train IIA | Train IIA | No intervention train IIA | Initial validation IIA | Validation IIA | No intervention validation IIA | Test IIA (descriptive) | No intervention test IIA (descriptive) | Post-lock status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conditions/seed=42 | complete | 94/200 = 0.47 | 96/200 = 0.48 | 94/200 = 0.47 | 0/200 = 0.0 | 3/200 = 0.015 | 0/200 = 0.0 | 0/100 = 0.0 | 0/100 = 0.0 | complete |
| conditions/seed=43 | complete | 94/200 = 0.47 | 96/200 = 0.48 | 94/200 = 0.47 | 0/200 = 0.0 | 4/200 = 0.02 | 0/200 = 0.0 | 0/100 = 0.0 | 0/100 = 0.0 | complete |
| conditions/seed=44 | complete | 95/200 = 0.475 | 96/200 = 0.48 | 94/200 = 0.47 | 0/200 = 0.0 | 4/200 = 0.02 | 0/200 = 0.0 | 0/100 = 0.0 | 0/100 = 0.0 | complete |

Full-precision metrics and exact counts are saved in `conditions.csv`.
Missing metrics are shown as —; failed and pending conditions remain in the table.

Per-layer means and sample SD across seeds are saved in `layer_summary.csv`.
Seed SD describes variation across seeds; it is not a confidence interval.
A single available seed has no sample SD. Incomplete layers are flagged in the CSV.

Per-pairing and target-change groups (counts summed across seeds; means give equal weight to each seed):

| Layer | Split | Group | IIA | No-intervention IIA |
| --- | --- | --- | --- | --- |
| 9 | initial_train | ABB->ABB | 138/150; mean 0.92 | 138/150; mean 0.92 |
| 9 | initial_train | ABB->BAB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 9 | initial_train | BAB->ABB | 1/150; mean 0.006666666666666667 | 0/150; mean 0.0 |
| 9 | initial_train | BAB->BAB | 144/150; mean 0.96 | 144/150; mean 0.96 |
| 9 | initial_train | switch_required | 1/300; mean 0.0033333333333333335 | 0/300; mean 0.0 |
| 9 | initial_train | unchanged_target | 282/300; mean 0.94 | 282/300; mean 0.94 |
| 9 | train | ABB->ABB | 138/150; mean 0.92 | 138/150; mean 0.92 |
| 9 | train | ABB->BAB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 9 | train | BAB->ABB | 6/150; mean 0.04 | 0/150; mean 0.0 |
| 9 | train | BAB->BAB | 144/150; mean 0.96 | 144/150; mean 0.96 |
| 9 | train | switch_required | 6/300; mean 0.02 | 0/300; mean 0.0 |
| 9 | train | unchanged_target | 282/300; mean 0.94 | 282/300; mean 0.94 |
| 9 | initial_validation | ABB->ABB | 0/0; mean — | 0/0; mean — |
| 9 | initial_validation | ABB->BAB | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 9 | initial_validation | BAB->ABB | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 9 | initial_validation | BAB->BAB | 0/0; mean — | 0/0; mean — |
| 9 | initial_validation | switch_required | 0/600; mean 0.0 | 0/600; mean 0.0 |
| 9 | initial_validation | unchanged_target | 0/0; mean — | 0/0; mean — |
| 9 | validation | ABB->ABB | 0/0; mean — | 0/0; mean — |
| 9 | validation | ABB->BAB | 3/300; mean 0.01 | 0/300; mean 0.0 |
| 9 | validation | BAB->ABB | 8/300; mean 0.026666666666666665 | 0/300; mean 0.0 |
| 9 | validation | BAB->BAB | 0/0; mean — | 0/0; mean — |
| 9 | validation | switch_required | 11/600; mean 0.018333333333333333 | 0/600; mean 0.0 |
| 9 | validation | unchanged_target | 0/0; mean — | 0/0; mean — |
| 9 | test | ABB->ABB | 0/0; mean — | 0/0; mean — |
| 9 | test | ABB->BAB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 9 | test | BAB->ABB | 0/150; mean 0.0 | 0/150; mean 0.0 |
| 9 | test | BAB->BAB | 0/0; mean — | 0/0; mean — |
| 9 | test | switch_required | 0/300; mean 0.0 | 0/300; mean 0.0 |
| 9 | test | unchanged_target | 0/0; mean — | 0/0; mean — |

![Validation IIA by layer](figures/validation_by_layer.svg)

![Train and validation IIA by layer](figures/train_validation_by_layer.svg)

![Post-lock test IIA by layer](figures/test_by_layer.svg)

![Saved IIA by condition](figures/iia.svg)
