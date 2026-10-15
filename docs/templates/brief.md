# Brief: <short title>

- Branch: `feat/<slug>`
- Task: `<task-id>`
- Status: open | in progress | merged | dropped
- Written: YYYY-MM-DD, from [meeting YYYY-MM-DD](../meetings/YYYY-MM-DD.md)
- Depends on: <other briefs, or none>

## Goal

One or two sentences: what capability exists after this brief that did not
before.

## Context

- Links to PLAN, PROTOCOL, CONVENTIONS sections, and the code involved.
- Facts the implementer needs (current behavior, constraints, reference
  results).

## Scope

Files or modules that may be added or changed.

## Out of scope

Things that must not be changed or started in this brief.

## Acceptance

Exact commands and expected results. All must pass before merging.

1. `$PY -B -m pytest -q` passes.
2. ...

## Notes for the implementer

Optional design hints. The implementer may choose differently if the
acceptance criteria and conventions still hold; record the reason in the
merge commit body.
