# single-condition-das / layer8-seed42

Run kind: **smoke**; run status: **complete**.

Config SHA-256: `f9c74ce47dc4ac9a94c090a533d6628544e0cdf93fb5a5ae850f898243015f5b`.

Conditions: complete=1.

This is a smoke run for execution checks; it is not a full experimental result.

The legacy test set is a descriptive benchmark, previously inspected in earlier runs.
It is not an untouched held-out test.

| Condition | Status | Initial train IIA | Train IIA | Test IIA (descriptive) |
| --- | --- | --- | --- | --- |
| conditions/intervention.layer=8/seed=42 | complete | 10/20 = 0.5 | 10/20 = 0.5 | 0/4 = 0.0 |

Full-precision metrics and exact counts are saved in `conditions.csv`.
Missing metrics are shown as —; failed and pending conditions remain in the table.

![Saved IIA by condition](figures/iia.svg)
