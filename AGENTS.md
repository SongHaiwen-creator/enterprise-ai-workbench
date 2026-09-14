# AGENTS.md - Enterprise AI Workbench

## Mission

Build Enterprise AI Workbench incrementally according to the
repository specifications.

The AI agent may plan, document, implement, test and prepare GitHub
changes autonomously, but must respect the rules below.

---

## Source of Truth

Before starting any task, read:

- docs/PRODUCT_SPEC.md
- docs/ARCHITECTURE.md
- docs/DATABASE.md
- docs/ROADMAP.md

Then read all relevant documents under:

- docs/features/

Do not invent requirements that conflict with these documents.

---

## Development Workflow

For every new feature:

1. Inspect repository state.
2. Identify the next unfinished roadmap item.
3. Check whether a Feature Spec already exists.
4. If not, create:
   docs/features/NNN-feature-name.md
5. Define:
   - Goal
   - Scope
   - Business Rules
   - API/Data Contract
   - Acceptance Criteria
   - Test Requirements
   - Out of Scope
6. Create a GitHub Issue.
7. Create or switch to the appropriate feature branch.
8. Implement only the approved scope.
9. Add or update tests.
10. Run verification.
11. Review the diff.
12. Commit using conventional commits.
13. Push the branch.
14. Create or update the Pull Request.
15. Summarize:
    - what changed
    - tests
    - unresolved risks
    - next recommended task

---

## GitHub Rules

Use GitHub CLI (`gh`) when available.

Issues should contain:

- Goal
- Scope
- Acceptance Criteria
- Out of Scope

Pull Requests should contain:

- Summary
- Files / modules changed
- Verification results
- Risks
- Related Issue

Use:

Closes #<issue>

when the PR should close an Issue after merge.

Never push directly to main.

Never merge main automatically.

---

## Branch Naming

Documentation:

docs/<topic>

Features:

feat/<feature-name>

Fixes:

fix/<issue-name>

---

## Commit Convention

Use:

docs:
chore:
feat:
fix:
test:
refactor:

Each commit should represent one coherent change.

---

## Scope Control

Do not implement future roadmap functionality early.

Do not add abstractions unless required by the current feature.

Do not introduce new dependencies without explaining why.

Do not rewrite existing Alembic migrations that have already been
committed and used.

---

## Security

Never commit:

- .env
- API keys
- passwords
- JWT secrets
- database credentials beyond safe local examples

Do not weaken authentication, authorization or tenant isolation
to make tests pass.

---

## Verification

Backend:

- PostgreSQL integration tests
- pytest
- Ruff

Frontend:

- pnpm lint
- pnpm build

Run feature-specific tests before the full suite.

Do not report a feature as complete if required tests are skipped.

---

## High-Risk Changes

STOP and request human approval before:

- database-destructive operations
- new database migrations
- authentication design changes
- RBAC / authorization policy changes
- security-sensitive changes
- architecture changes
- deleting existing APIs
- major dependencies
- merging into main

For ordinary feature implementation, proceed autonomously.

---

## Completion Standard

A task is complete only when:

- Spec exists
- Issue exists
- Implementation matches Spec
- Tests pass
- Diff has been reviewed
- Commit exists
- Branch is pushed
- Pull Request is created or updated
