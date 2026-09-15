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

## Feature Delivery Lifecycle

The project is developed one feature at a time.

Use the following lifecycle:

1. Inspect the latest `main` branch.
2. Identify the next unfinished roadmap feature.
3. Create one dedicated feature branch.
4. Create or update the Feature Spec.
5. Create the corresponding GitHub Issue.
6. Implement only that feature.
7. Run feature tests and regression verification.
8. Perform self-review.
9. Commit and push the feature branch.
10. Create a Pull Request targeting `main`.
11. Stop when the feature is PR-ready.

Do not begin the next roadmap feature in the same development thread.

A feature is considered complete only after its Pull Request has been
merged into `main`.

The next feature should start from the latest updated `main` branch
in a new development thread.

## Pull Request and Merge Policy

AI agents may:

- create feature branches
- create and update Feature Specs
- create GitHub Issues
- implement code
- run tests
- review diffs
- commit
- push
- create and update Pull Requests

AI agents must NOT merge Pull Requests into `main`.

Final merge into `main` requires human approval.

After a PR is merged:

1. the related Issue should be closed
2. local `main` should be updated
3. the feature is considered complete
4. the development thread for that feature ends
5. the next feature starts in a new thread

## Review Policy

### Normal-risk features

Examples:

- UI changes
- read-only endpoints
- ordinary product behavior
- non-security-sensitive frontend work

Required:

- implementation tests
- regression verification
- agent self-review
- human merge

An independent review agent is optional.

### High-risk features

Examples:

- authentication
- authorization / RBAC
- tenant / workspace isolation
- database migrations
- destructive database operations
- security-sensitive APIs
- external write-capable tools
- human approval policies

Required:

- human approval before implementation when required by this file
- implementation tests
- regression verification
- independent review before merge
- human merge

## Open Source Reuse Policy

Before implementing substantial AI infrastructure, first evaluate
mature open-source libraries, SDKs, or services.

Prefer, in order:

1. existing project dependency
2. official SDK/API integration
3. small well-scoped open-source component
4. custom implementation

Compare candidates by:

- functional fit
- license
- maintenance/activity
- stack compatibility
- deployment complexity
- integration cost

Do not reimplement commodity infrastructure without justification.

Large external platforms must not replace the Workbench's ownership of:

- Workspace
- Authentication
- RBAC
- tenant isolation
- product configuration
- approval policy