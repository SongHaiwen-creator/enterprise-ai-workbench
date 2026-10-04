# Feature 017 - Chinese UI Refresh

Status: Approved implementation in progress
Baseline: main at `746fbeb9580fed6719abd9d7014297151aaa55f8`
Branch: `feat/chinese-ui-refresh`
Risk: Normal - presentation changes only

## Goal

Implement the user-approved blue/white Chinese prototypes as a usable long
product landing page and a consistent enterprise application. This is a
user-directed UI feature; Bad Case Management remains the next unfinished
product capability and is not implemented here.

## Scope

- Public `/` with abstract hero artwork, six module introductions, usage guide,
  keyboard-operable illustrative interactions, and links to `/app`.
- Move the existing login/application to `/app`; default to Assistant.
- Group navigation into daily use, operations, and Workspace; add an accessible
  mobile navigation drawer and independently scrolling application content.
- Simplified Chinese UI, role/status labels, dates, accessible labels and safe
  error presentation. User-entered names/content and provider answers are not
  translated or rewritten.
- Shared blue/white CSS tokens, PingFang SC-first system font fallback, consistent
  type scale, controls, tables, panels and reduced-motion support.
- Preserve and restyle Feature 016 Run forms, consent, results and history inside
  Evaluation Datasets. Landing copy describes structured metrics, not semantic
  answer correctness or real Tool execution during evaluation.

## Business Rules

- The existing memory-only Bearer session, backend authorization, roles,
  Workspace resets, pending locks, stale-response guards and API contracts remain.
- Public demonstrations use labeled synthetic content and never call APIs,
  submit requests, authenticate, or run evaluations.
- Sensitive-operation illustrations show the existing mock IT access request.
  Decision and execution statuses are separate. No new approval policy.
- Evaluation egress acknowledgement is never preselected, removed, shortened to
  conceal meaning, or inferred from navigation. Ambiguous submissions continue
  to require inspecting history before another run.
- Chinese presentation maps known enums/messages without mutating wire values
  or the raw ApiError used for programmatic contract comparisons.
- No token/content persistence, public signup, new management capability,
  live model call, real external integration or runtime database migration.

## API / Data Contract

No backend endpoints, request/response types, enums or database schema change.
Browser entry changes from the original root application to `/app`. The public
root is a standalone product page; `/app` retains the existing login gate.
Root document language and metadata become Chinese. Shared presentation helpers
provide translated enums, safe UI messages and zh-CN date formatting.

## Acceptance Criteria

1. Public page presents six accurate feature sections and a working platform
   entry; content remains readable without animation.
2. Login reaches Assistant by default; all existing areas and authorized
   actions remain usable and Chinese presentation does not change payloads.
3. Desktop sidebar/content scrolling and mobile drawer work without page-wide
   horizontal overflow; drawer supports focus return, Escape and dismissal.
4. Chinese text hierarchy, consistent controls, empty/loading/error states and
   long literal content render coherently on mobile and desktop.
5. Citations, tool outcomes, separate approval/execution states, log pagination,
   Dataset/Case editing, evaluation consent/history/metrics retain behavior.
6. Existing confidentiality, authorization and stale-response regression tests
   pass; no required test is skipped.
7. Browser QA screenshots, reviewed diff, conventional commit, pushed branch,
   and PR targeting main exist. Human merge remains the final delivery gate.

## Test Requirements

- Feature tests for landing links, module switching, Chinese labels/date/enum
  presentation, login default and mobile drawer keyboard behavior.
- Update existing UI queries for translated accessible labels while retaining
  API payload, role, pending, stale-response and evaluation consent assertions.
- Run targeted UI tests before full frontend API/UI tests, lint and build.
- Run backend pytest including dedicated PostgreSQL integration and Ruff as
  required by AGENTS.md. Never reset/migrate the runtime database.
- Browser check desktop/mobile landing, login, all existing application areas
  with intercepted synthetic API responses, reduced motion and console errors.

## Out of Scope

Authentication/RBAC changes, migrations, new runtime UI frameworks, production
deployment, conversation history/streaming, workflow builder, Bad Case
Management, new Agent/Tool/Knowledge Base administration pages, semantic scoring,
and merging the PR.

## Approval and Tracking

The user approved both visual prototypes and explicitly requested the complete
implementation plan in this chat. No additional design approval is required.
GitHub Issue: [#39](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/39).
Implementation branch: `feat/chinese-ui-refresh`.
Verification and screenshots: [017-chinese-ui-refresh-verification.md](017-chinese-ui-refresh-verification.md).
Status: implemented; PostgreSQL regression and human merge pending.
