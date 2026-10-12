# Phase 2 full run

GPT-2, layer 8, block_output, N, rank 1, target_variable=position.

Optimizer updates: 100; training pairs: 200.

Train IIA: 173/200 = 0.865.

Test IIA: 79/100 = 0.79.

Test factual accuracy: 98/100 = 0.98.

Identity, gradients, bit-identical frozen model state, variable-length batching, saved alignment reload, and hook cleanup passed. Full-precision values and counts are in metrics.json; this run does not use test data for tuning.
