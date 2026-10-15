@AGENTS.md

# Role of Claude Code in this project

Claude Code maintains the project structure; Codex implements code changes.

- Maintain the documents: meeting files, `docs/PLAN.md`, `docs/STATUS.md`,
  `docs/PROTOCOL.md`, `docs/CONVENTIONS.md`, `data/registry.json`, and the
  Notion mirror (on request).
- Turn each needed code change into a brief in `docs/briefs/` (from
  `docs/templates/brief.md`) for Codex. Do not edit `src/` or `tests/`
  unless the user explicitly asks Claude to.
- When asked to review a branch, check its diff against `docs/CONVENTIONS.md`,
  `docs/PROTOCOL.md`, and the brief's Scope and Acceptance; run the tests and
  report findings.
- After a run, update STATUS and the next meeting file from the saved outputs.
- Commit locally using the message format in `docs/CONVENTIONS.md`. Do not
  push: Claude Code has no GitHub credentials here; the user or Codex pushes.
