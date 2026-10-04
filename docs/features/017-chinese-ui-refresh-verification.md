# Feature 017 — Verification and Screenshots

Date: 2026-10-04 (Asia/Shanghai). Issue: [#39](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/39).
Baseline: merged PR #37, main commit `746fbeb9580fed6719abd9d7014297151aaa55f8`.

## Implementation

- Public product introduction at `/`, existing platform/login at `/app`; login defaults to Assistant.
- Six native HTML/React module illustrations with synthetic, explicitly labelled interactive examples. The blue abstract hero is a separate generated PNG; the page itself remains selectable HTML.
- PingFang SC preferred, Microsoft YaHei/system fallbacks. Shared CSS variables define type sizes, colors, spacing, surfaces, form controls and status feedback. No added application dependencies or UI framework.
- Grouped navigation, native workspace selector, independently scrolling content, mobile modal drawer, visible focus and reduced-motion support.
- Chinese application copy, enum labels and date presentation with explicit Beijing time. User-entered resource names, model answers, literal content and API contracts are preserved.
- Existing Feature 016 evaluation consent, ambiguous-submission recovery, permission fixture and dry-run limits retained. Approval demonstration uses IT access requests with separate decision/execution states.

## Checks Completed

| Check | Result |
| --- | --- |
| Frontend `pnpm test` | 9 API + 94 UI tests passed; no skips |
| Feature follow-up tests after negative-query self-review | 52 passed |
| Frontend `pnpm lint` | Passed |
| Frontend `pnpm build` | Passed; `/` and `/app` generated |
| Backend `pytest tests --ignore=tests/integration -q` | 619 passed; 1 existing Starlette deprecation warning |
| Backend `ruff check .` | Passed |
| Browser | Passed in local headless Edge at 1440px, 390px and 320px; no page or console errors |
| Diff self-review | API clients/backend/migrations unchanged; raw error matching, permission gates and pending locks preserved |

Python verification used the existing project virtual environment. Pytest temporary files were placed in a unique workspace cache directory because the system temporary directory denied access. The browser tooling was installed only in ignored `.cache/browser`; it is not an application dependency.

## Browser Acceptance

All browser API responses were intercepted synthetic fixtures. No production request, real approval, live provider execution or runtime database migration was part of this check.

- Public page, separate decoded hero image, six module anchors, citation expansion and Assistant example switches.
- Login and default Assistant; starter prompts fill the request without sending it; explicit submission displays answer and citations.
- Knowledge Q&A input, answer and source inspector.
- IT request details, decision submission, separate approval/execution results.
- Log expansion and recorded details.
- Evaluation Agent selection, unchecked consent by default, disabled submission before acknowledgement, run history and result presentation.
- Workspace changes, member presentation and removal of administrative navigation for an employee.
- Mobile drawer modal focus containment, Escape dismissal, restored trigger focus and module selection.
- No horizontal overflow at narrow widths; reduced-motion disables the hero animation.

## Screenshots

These images are actual browser captures with synthetic data, not design mockups.

- [Full Chinese landing page](../screenshots/chinese-ui-refresh/home-desktop.png)
- [Assistant and grouped sidebar](../screenshots/chinese-ui-refresh/assistant-desktop.png)
- [Mobile drawer](../screenshots/chinese-ui-refresh/navigation-mobile.png)

## Outstanding Verification

PostgreSQL integration verification is **blocked**, not passed or skipped. The dedicated target is `enterprise_ai_workbench_ui_20261004_test`, distinct from the runtime database. The full backend invocation (`pytest tests -q --maxfail=1`) stopped at the first integration fixture with a connection timeout to `127.0.0.1:5432` because Docker Desktop could not start its Linux engine after a stale runtime socket error. No integration fixture reached a database reset or migration. No backend completion claim is made.

Non-destructive service recovery was attempted; persistent Docker data, volumes and runtime databases were not deleted or reset. The user has been asked to restore Docker Desktop to Running. Once available, create the dedicated test database, run Feature 016/related PostgreSQL tests and the full backend suite, then update this record and mark the PR ready. The feature must not be reported complete until required regression passes and the human merges the PR.

## Review Notes and Limits

- No authentication, authorization, workspace isolation, schema or wire-format changes.
- Native modal dialogue supplies browser focus handling; feature interactions are buttons/links and do not trigger real operations.
- Platform state remains in memory, as before. Refreshing requires login. Returning to the public page leaves the platform session.
- PingFang renders on systems where installed; Windows uses the declared Chinese sans-serif fallback. No proprietary font file is bundled.
- Unknown API enum values and arbitrary resource names remain visible unchanged; known errors receive Chinese presentation while raw `ApiError.message` comparisons remain unchanged.
- Human merge remains required. Bad Case Management is not included in this change.
