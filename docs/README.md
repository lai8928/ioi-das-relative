# Research log

*Imported from the Notion page "LLM_fractionation" on 2026-11-16. This file is now the maintained copy; its task table is updated together with [STATUS.md](STATUS.md).*

## Project overview

This project uses Distributed Alignment Search (DAS) to test whether interpretable causal variables in the Indirect Object Identification (IOI) task align with internal representations of GPT-2. The experiments examine how intervention success changes across layers, model sizes, subspace ranks, training-data sizes, and intervention sites.

For a first read, start with [Background and method notes](#background-and-method-notes) below, then read the [Experiment reports](#experiment-reports) for our experimental evidence. [Current tasks](#current-tasks) summarizes the latest status; [Meeting notes](#meeting-notes) and [Progress reports](#progress-reports) record the research decisions and progress over time.

## Current tasks

| Task ID | What | Status | Report |
| --- | --- | --- | --- |
| `position-audit` | Original IOI data and per-example position audit | Done (2026-10-12) | [2026-10-12 meeting](meetings/2026-10-12.md) |
| `single-condition-das` | One DAS run: GPT-2 Small, layer 8, N, rank 1 | Done (2026-10-12) | [2026-10-12 meeting](meetings/2026-10-12.md) |
| `layer-sweep` | Every layer at the last token, GPT-2 Small | Done (2026-10-15): layer 8, validation IIA 0.83 | [layer-sweep report](reports/2026-10-15-layer-sweep.md) |
| `model-scale` | Same protocol on a larger model (GPT-2 Medium) | Done (2026-10-15): layer 14, validation IIA 0.28; follow-ups in rank-sweep and data-scale | [model-scale report](reports/2026-10-15-model-scale.md) |
| `data-scale` | Larger training sets (200 / 1000 / 5000 pairs) | Closed (2026-11-05): GPT-2 Medium × rank, 10 of 16 done; layer-14 IIA stays at 0.25–0.32; the rest will not run | [data-scale report](reports/2026-10-19-data-scale.md) |
| `rank-sweep` | DAS rank 1 / 2 / 4 / 8 (GPT-2 Medium and Small) | Closed (2026-11-05): Medium, every rank about 0.28–0.30; Small and the learning-rate check will not run | [rank-sweep report](reports/2026-10-18-rank-sweep.md) |
| `object-names` | Object nouns in place of person names: behavior and DAS | Dropped (2026-11-05): never started | [2026-10-19 meeting](meetings/2026-10-19.md) |
| `intervention-sites` | DAS at sites other than the block output: attention, MLP, and one head's Z / Q / K / V | Active: first GPT-2 Small round done (2026-11-05); the signal comes from attention in layers 7–8, single heads at most 0.05 | [intervention-sites report](reports/2026-11-05-intervention-sites.md) |

## Background and method notes

These English notes provide the conceptual and implementation background for the project. Suggested reading order:

1. [DAS Foundations: Causal Abstraction, Interventions, and Hierarchical Equality](notes/das-foundations.md) — Introduces high- and low-level causal models, interchange interventions, and the hierarchical equality example.
2. [Understanding DAS II: From Exchanging an Intermediate Value to Learning an Alignment](notes/das-alignment-learning.md) — Explains rotation, subspace exchange, alignment learning, IIA, and the distinction between probing and causal intervention.
3. [DAS Notebook Implementation Notes: High-Level Models, Handcrafted Tests, and Learned Alignment](notes/das-notebook-implementation.md) — Walks through the introductory Pyvene notebook, from handcrafted and trained MLPs to counterfactual targets and DAS training.
4. [IOI Circuit Paper Notes: Section-by-Section Outline](notes/ioi-circuit-paper.md) — Summarizes the IOI circuit paper, including Name Movers, S-Inhibition, position signals, and circuit validation.
5. [IOI with DAS: Hypotheses, Experimental Design, and Results](notes/ioi-with-das-notebook.md) — Reviews the official IOI DAS notebook's POSITION and NAME hypotheses, intervention designs, reported results, and implementation details.

These are earlier reading and method notes; their execution statuses reflect when they were written. Author-reported results and illustrative examples should be distinguished from our experiment reports.

## Experiment reports

One report per completed experiment: setup, figures, conclusions, and reproducibility details. Each report is kept as written on its date, so its "Next steps" section shows the plan at that time; the current status is in the task table above. Later corrections appear in a report's Amendments section.

- [layer-sweep · Per-layer DAS at the last token of GPT-2 Small (2026-10-15)](reports/2026-10-15-layer-sweep.md)
- [model-scale · Per-layer DAS at the last token of GPT-2 Medium (2026-10-15)](reports/2026-10-15-model-scale.md)
- [rank-sweep · DAS rank 1/2/4/8 on GPT-2 Medium (2026-10-18)](reports/2026-10-18-rank-sweep.md)
- [data-scale · Training size × rank on GPT-2 Medium (2026-10-19)](reports/2026-10-19-data-scale.md)
- [intervention-sites · Attention, MLP, and single-head DAS on GPT-2 Small (2026-11-05)](reports/2026-11-05-intervention-sites.md)

## Meeting notes

What was reported, said, and decided at each advisor meeting.

- [2026-10-12](meetings/2026-10-12.md)
- [2026-10-15](meetings/2026-10-15.md)
- [2026-10-19](meetings/2026-10-19.md)
- [2026-11-02](meetings/2026-11-02.md)

## Progress reports

Weekly progress reports written for the professor before a meeting.

- [2026-10-15 Weekly progress report](progress/2026-10-15.md)
- [2026-10-19 Weekly progress report](progress/2026-10-19.md)

## Working documents

The project's plan for the current meeting cycle is in [PLAN.md](PLAN.md), the done work with its evidence in [STATUS.md](STATUS.md), the rules every experiment follows in [PROTOCOL.md](PROTOCOL.md), and how code, configs, outputs, and documents are written in [CONVENTIONS.md](CONVENTIONS.md). How to install, run, and reproduce the experiments is in the [repository README](../README.md).
