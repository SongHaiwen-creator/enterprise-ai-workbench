# Feature 017 — Verification and Screenshots

Date: 2026-10-04 (Asia/Shanghai). Issue: [#39](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/39).
PR: [#41](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/41).
Implementation commit: `cc3e010`. Required verification passed; human-merged in PR #41 on 2026-10-04. Issue #39 is closed.
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
| PostgreSQL `pytest tests/integration -q` | 901 passed; no skips; 68 existing deprecation warnings |
| Full backend `pytest tests -q` | 1520 passed; no skips; 68 existing deprecation warnings |
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

## PostgreSQL Verification

Docker was restored on 2026-10-04. PostgreSQL integration verification passed: **901 tests, no skips**, using `enterprise_ai_workbench_test`, distinct from the runtime database `enterprise_ai_workbench`. Existing fixtures validate isolation before resetting the test schema and applying existing migrations; no runtime database or live provider was used.

The earlier Docker connection failure is resolved. A first retry with the separately created `enterprise_ai_workbench_ui_20261004_test` database reached 540 passing tests but failed the evaluation fixtures' hard-coded database-name assertions (2 failures, 359 setup errors). Verification was then rerun against the repository-required test database without changing tests or safety checks. The integration run emitted 68 existing Starlette/Alembic deprecation warnings.

The subsequent full backend run passed **1520 tests with no skips** and the same 68 deprecation warnings. Commands used workspace-local `--basetemp` directories. Required verification is complete; human merge completed in PR #41 on 2026-10-04.

## Review Notes and Limits

- No authentication, authorization, workspace isolation, schema or wire-format changes.
- Native modal dialogue supplies browser focus handling; feature interactions are buttons/links and do not trigger real operations.
- Platform state remains in memory, as before. Refreshing requires login. Returning to the public page leaves the platform session.
- PingFang renders on systems where installed; Windows uses the declared Chinese sans-serif fallback. No proprietary font file is bundled.
- Unknown API enum values and arbitrary resource names remain visible unchanged; known errors receive Chinese presentation while raw `ApiError.message` comparisons remain unchanged.
- Human merge completed in PR #41 on 2026-10-04. Bad Case Management is not included in this change.
