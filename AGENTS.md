# Agent rules

## Read first, in this order

1. `docs/PLAN.md`: what the current meeting cycle authorizes.
2. `docs/STATUS.md`: what is actually done, with evidence.
3. `docs/PROTOCOL.md`: scientific rules every experiment obeys.
4. `docs/CONVENTIONS.md`: how code, configs, scripts, outputs, and git
   history are written.
5. The newest file in `docs/meetings/`: why the plan looks this way.
6. When implementing: the brief in `docs/briefs/` you were given.

## Roles

- Claude Code maintains documents, writes briefs, reviews branches, and
  syncs Notion (see `CLAUDE.md`).
- Codex implements briefs: one brief, one branch, merged when its Acceptance
  passes. Stay inside the brief's Scope; if the brief is wrong or incomplete,
  stop and report instead of widening it. Codex does not edit
  `docs/STATUS.md`, `docs/PLAN.md`, or `docs/meetings/`; it puts evidence in
  commit message bodies, and Claude Code updates those documents after review.

`docs/archive/` holds superseded documents (the bootstrap brief, phase-era
plans and status, milestone specs). Read it for history only; it never
authorizes work.

## Language

- Code, identifiers, comments, docstrings, CLI output, configs, and docs are
  in English.
- Exception: the "Raw notes" section of a meeting file keeps the user's text
  verbatim, in any language.
- Explain progress and findings to the user in Traditional Chinese.

## Planning model

- The planning unit is the meeting cycle: from one advisor meeting to the
  next. There are no phases, milestones, or letter/number stages. Do not
  invent any. Older names (Phase 0–2, M3/M4/M5, A/B/C) survive only in
  archived documents, legacy output paths, and the "Formerly" column of the
  STATUS task table.
- Work is grouped into tasks with stable kebab-case IDs, registered in the
  STATUS task table. A task keeps its ID across cycles; only its status
  changes. Status values: `active`, `paused`, `deferred`, `done`, `dropped`.
- New research question → new task ID. Same question with different settings
  → new experiment (config) under the existing task.
- Scope: only work listed under "This cycle" in `docs/PLAN.md` is authorized.
  Items under "Deferred" or "Open questions" need an explicit user request.
- Document ownership:

  | File | Answers | Update mode |
  | --- | --- | --- |
  | `docs/meetings/YYYY-MM-DD.md` | What was reported, said, and decided | One new file per meeting, from `docs/templates/meeting.md`; past files get only appended Amendments |
  | `docs/PLAN.md` | What we do until the next meeting | Rewritten each cycle; keep its section structure |
  | `docs/STATUS.md` | What is done, with which evidence | Edited in place; current state only |
  | `docs/PROTOCOL.md` | Rules that hold for every experiment | Rare; each change cites a meeting decision in its change log |
  | `docs/CONVENTIONS.md` | How code, configs, scripts, outputs, and commits are written | Rare; changed by Claude Code, cited in the commit |
  | `docs/briefs/YYYY-MM-DD-<slug>.md` | One code change for Codex: goal, scope, acceptance | New file per change, from `docs/templates/brief.md`; update its Status line when merged or dropped |
  | `data/registry.json` | Which datasets exist and what they are for | Append a row per new dataset |

- Never create `PLAN_v2.md`, `STATUS_old.md`, `NEXT_*.md`, or other new
  document types. History lives in git, `docs/meetings/`, and `docs/archive/`.

## Meeting workflow

- "Prepare meeting <date>": create `docs/meetings/<date>.md` from the
  template. Fill "Reported" from STATUS with links to evidence and draft
  "Proposed questions". Leave Feedback and Decisions empty.
- "Here are the notes for <date>": paste the notes verbatim into Raw notes,
  then write Feedback and Decisions. Mark anything ambiguous as undecided
  rather than guessing. Then reconcile STATUS (done vs. only discussed),
  rewrite PLAN, and update the task table. Show the user the PLAN change
  before starting work.
- Mid-cycle change of direction: append a dated Amendment with the reason to
  the latest meeting file, then rewrite PLAN.
- Notion mirror: the repository is the source of truth. The private Notion
  page "IOI DAS Relative · 研究進度 Research Log" holds a Chinese and an English
  version of each meeting note. Sync to Notion only when the user asks.

## Code and configuration

Full rules are in `docs/CONVENTIONS.md`; the essentials:

- Organize code by function, never by task, meeting, or date. No phase or task
  names in modules or identifiers (no `m3.py`, no `if task == ...`).
- A new experiment that only changes values or choices adds a config file and
  no code. Change code only for a new capability: add a package function,
  expose it as a config option, and add a test.
- New configs live in `configs/<task-id>/<name>.json`, use `extends` to record
  only their differences from a base, and produce outputs under
  `outputs/<task-id>/<YYYYMMDD>-<name>/`. Every run saves its fully resolved
  config and SHA-256. The output path is derived from the config, never
  hand-named. Smoke runs use the same code path with an override; their
  experiment IDs start with `smoke-`.
- Legacy configs (`configs/audit.json`, `configs/phase2.json`), legacy data
  under `data/generated/`, and legacy outputs keep their current paths:
  recorded hashes and verifiers reference them.
- `scripts/` holds thin wrappers over package functions. One-off
  investigations go in `scripts/adhoc/YYYYMMDD-<name>.py`; logic used twice
  moves into the package.
- Notebooks present saved results. By default they never load a language
  model, train, or start a sweep. Label saved evidence, synthetic
  demonstrations, online metrics, and fixed-weight evaluations accurately.

## Data, artifacts, and upstream

- Register every dataset in `data/registry.json`. Save once, verify the
  manifest before reuse, and never rewrite; a changed dataset gets a new
  versioned name. Do not call generated data historical samples.
- Completed outputs are immutable. Keep and report failed and partial runs.
- Keep the eight pinned upstream originals byte-for-byte under
  `vendor/pyvene_upstream/`, with provenance in `docs/UPSTREAM.md` and the
  activation-patching-illusion credit. Adaptations go in `src/ioi_das/`;
  pyvene is an external versioned dependency.

## Git

- `main` always passes the tests. Code changes happen on the branch named in
  their brief; experiments are configs and outputs committed on `main`.
- Commit messages: `<type>(<scope>): <summary>`, with types `feat`, `fix`,
  `refactor`, `test`, `docs`, `config`, `data`, `results`.
- Tag `main` as `meeting/YYYY-MM-DD` when a meeting brief is final.

## Environment and remote

- Use the existing `ioi-das-v2` Conda interpreter (commands in `README.md`).
  Ask before installing packages, downloading model weights, or changing
  Python, CUDA, or system settings.
- Check GPU availability on the shared server before launching a job.
- Do not push or create remotes without authorization.

## Reporting

- Run the tests before claiming completion. Record actual commands, results,
  hashes, blockers, and output paths in STATUS, plus the exact next command.
- Label smoke and full runs separately. Never substitute tutorial or
  synthetic data for missing results.
