# Feature 018 - Bad Case Management

状态：Phase A 规格提案，待人工审批；未实施。
日期：2026-10-04。
基线：最新 `origin/main` / HEAD `78ec01394b49d0f8b0ae508472500154d8e646db`。
分支：`feat/bad-case-management`。
风险：高；新增迁移、Workspace 隔离和保密人工记录。
Issue：[#42](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/42)。
PR：本分支的 Phase A 文档 PR；创建后的链接由交付说明提供。

## 1. Goal 与阶段边界

让同 Workspace 的 Agent/System 管理员把已有终态评测结果转为可追踪的问题，
记录人工分类、可能原因、处理过程和结论，同时保留不可变的原始评测证据。
问题管理不改变评测评分，不代表系统已证明根因或修复有效。

本轮只交付规格、Issue、文档提交和 Phase A PR。不创建迁移、应用代码或测试，
不修改数据库，不调用 Provider，不开始 Feature 019 或其他功能。
Phase B 须按第 12 节审批后才可实施；规格 PR 合并也不等于实施批准。

## 2. 规划来源与基线

- 已读取 `PRODUCT_SPEC.md`、`ARCHITECTURE.md`、`DATABASE.md`、`ROADMAP.md`，
  以及 Features 014–017、现有评测模型、评分器、路由与历史读取服务。
- `git fetch origin` 后 HEAD 与 `origin/main` 相同，工作树初始干净。
  Feature 016 PR #37 已交付；Feature 017 PR #41 于 2026-10-04 合并，Issue #39 关闭。
- 最新 MVP 规划位于尚未合并的 [PR #40](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/40)
  / [Issue #38](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/38)，
  其中 `docs/MVP_DELIVERY_PLAN.md` 将 018 定为 Bad Case Management，023 定为运行比较。
  本规格与该提案一致，但不将其未合并的全套文档变更复制到本分支。
- main 路线图同样把 Bad Case Management 列为下一未交付产品能力；没有现成 018。
  main 中部分 016/017 文档状态滞后，以上实际 GitHub 合并证据优先用于交付核验。
- 仓库已有 migration head `0012`。这不证明任何运行数据库已升级。
  Phase B 开始前再次核对 main、规划 PR、Issue、迁移 head 与本提案是否仍一致。

## 3. Scope 与复用

拟实施范围：

- 从已结束的 Evaluation Run 的终态 Run Case 人工建立问题；一个结果最多一个问题。
- 区分结构化 FAIL、运行 ERROR、人工复核；支持分类、可能原因、处理备注、状态与历史。
- Workspace 级问题列表、详情、编辑及只读变更历史；评测结果详情提供建立/查看入口。
- 复用 017 中文界面与样式；延用现有评测管理角色、服务事务和安全验证模式。
- 新增两张表及一条 additive migration；对应单元、PostgreSQL、前端测试和独立复审。

复用 SQLAlchemy、Pydantic strict models、FastAPI、PostgreSQL、既有分页及授权依赖。
本功能是领域问题记录，不建设 AI 执行基础设施；无需新库、外部缺陷平台、
评测框架或后台任务。不可用新抽象代替 Workspace、授权或原始 Run 证据。

## 4. Business Rules

### 4.1 来源与证据

1. 服务按 `(workspace_id, run_id, run_case_id)` 解析来源。请求中不能提供源结果、
   评分、Dataset/Agent/Case ID、Prompt 或实际行为；所有来源信息从数据库获取。
2. Run 必须为 `completed` 或 `failed`；Run Case 必须为 `passed`、`failed` 或 `error`。
   running Run（即便某 Case 已结束）与 pending Case 返回 `409`，不自动终止或协调 Run。
   若 Run 尚未完成，请通过现有评测历史接口刷新；018 不引入额外历史变更。
3. 服务派生不可变 `origin_kind`：failed -> `behavior_failure`，error -> `execution_error`，
   passed -> `manual_review`。人工复核必须填写问题描述，明确这是人工判断，
   不把原有 PASS 改成 FAIL。所有来源均须填写描述。
4. 人工发现的语义问题首版可关联一个 PASS 结果登记。不能直接从生产日志、聊天、
   Approval 或外部链接建立独立问题；现有 Run 未保存答案全文，也不在本功能补采。
5. 保存 Run Case 引用，读取其原始快照；不复制输入、Prompt、期待或 actual 到新表。
   禁用/编辑 Dataset、Case、Agent 后，证据仍来自历史，不重新执行或读取当前配置替代。
6. `(workspace_id, source_run_case_id)` 唯一，关闭后也不释放。并发/重试重复建立返回固定
   `409`；UI 刷新列表并打开已有问题，不自动创建另一个或合并不同 Run 的结果。
7. 不变更原始 Run、Run Case、评分器、指标或 ERROR 分母。Tool 标注 dry run，权限标注
   policy simulation；FAIL 不是语义错误证明，ERROR 不是回答质量评分，PASS 不是安全证明。

### 4.2 人工字段、状态与历史

分类枚举：`unclassified`、`routing`、`knowledge`、`tool_planning`、`permission`、
`refusal`、`runtime`、`other`。默认 `unclassified`；这是人工标签，可与来源类别不同。
可能原因始终标注“人工假设”，允许未知或修正，不自动诊断。

处理状态：`open`、`investigating`、`resolved`、`dismissed`，初始 `open`。
允许 open -> investigating/resolved/dismissed，investigating -> open/resolved/dismissed，
resolved/dismissed -> open。两个结束状态间须先重开。结束状态可改备注；仍须保留结论。
进入 resolved/dismissed 以及重开时必须有非空 `change_reason`；任意实际状态变化也必填。
resolved 表示人工确认已处理；dismissed 表示人工决定不处理，均不表示系统认证修复。
resolved/dismissed 必须保有非空 `resolution_note`；重开时清空该字段，旧结论留在历史。
没有自动关闭、自动复跑、复测关联或可比性判断；这些由 Feature 023 单独设计。

一次 PATCH 在锁定行上合并并验证完整状态；需 `expected_revision` 防止覆盖别人编辑。
revision 从 1 开始，每次实际变更加 1；陈旧 revision 返回 `409`，不写任何字段/历史。
与现值完全相同的合法请求返回现对象，不增加 revision 或历史。
创建和每次实际变更均在同一事务保存 append-only 历史；历史失败则整体回滚。
历史记录操作者、数据库时间、revision、事件、变更原因及人工字段前后值，不存源正文。
不存在历史编辑/删除接口；这是应用层不可变记录，不宣称数据库超级用户不可篡改。

## 5. API / Data Contract

所有路由以 `/api/workspaces/{workspace_id}` 为前缀。

| Method | 后缀 | 成功 | 用途 |
|---|---|---|---|
| POST | `/evaluation-runs/{run_id}/cases/{run_case_id}/bad-case` | 201 BadCaseDetail | 从来源建立 |
| GET | `/bad-cases` | 200 BadCaseList | Workspace 列表与过滤 |
| GET | `/bad-cases/{bad_case_id}` | 200 BadCaseDetail | 问题及历史源证据 |
| PATCH | `/bad-cases/{bad_case_id}` | 200 BadCaseDetail | 原子编辑/状态变更 |
| GET | `/bad-cases/{bad_case_id}/history` | 200 BadCaseHistoryList | 只读人工变更历史 |

Create body：`{title, description, category?, possible_cause?}`。
PATCH body：`{expected_revision, title?, description?, category?, possible_cause?,
handling_note?, status?, resolution_note?, change_reason?}`；至少一个可编辑字段。
禁止 server fields、额外字段、任意 JSON evidence、来源变更与 role/actor 参数。

- title：去两端空白，1–255 字符。description：去两端空白，1–5000 字符。
- possible_cause、handling_note、resolution_note：nullable，最多 5000 字符，空白转 null。
  change_reason：最多 1000 字符，按状态变更规则必填；其他编辑可选，空白转 null。
- 所有字符串拒绝 NUL，保留内部换行，作为普通文本处理。枚举 exact；revision 为 strict
  integer >= 1，拒绝 bool。PATCH 省略保留原值；null 仅清空上述 nullable 字段。
- List filters：status、category、origin_kind、source_run_id、source_run_case_id；精确枚举/UUID。
  supplied reference filters 先 scoped lookup；foreign 与 missing 都返回相同 `404`。
  无全文搜索、自由 SQL、模糊根因过滤或统计 Dashboard。
- 分页 `{items, limit, offset}`，limit 1–100/default 50，offset >= 0。
  列表 `(created_at DESC, id DESC)`；历史按 revision ASC。并发新增下 offset 分页不是快照。
- BadCaseSummary：id/workspace_id、source_run_case_id、source_run_id、source_case_id、
  dataset_id、agent_id、source_result、source_case_type、origin_kind、title、category、status、
  created_by、updated_by、created_at、updated_at、revision。来源字段通过 scoped join 派生，
  不暴露人工描述、原因、备注、Prompt、输入、期待或 actual。
- BadCaseDetail：Summary + description/possible_cause/handling_note/resolution_note +
  `source_evidence`（复用现有 RunCaseDetail 的严格序列化）；保留 null actual/checks/error
  语义。源 Run 详情链接使用现有授权 API，018 不额外返回整个 Agent/config Prompt。
- History item：id/bad_case_id/workspace_id、actor_id、revision、event (`created`/`updated`)、
  created_at、change_reason、before_values、after_values。before/after 只允许第 6 节人工字段；
  创建 before 为 null、after 为完整初始值；更新仅保存实际变化字段的前后值。

错误：既有 token `401`、Workspace/Membership/role `403`/`404` 不变。
资源 `404 {detail: "Bad case resource not found"}` 不回显 ID、名称或所有权。
`409` 固定 detail 分别为 `Bad case source is not terminal`、`Bad case already exists`、
`Bad case revision conflict`、`Bad case resource is busy`。
body/path/query/UTF-8/嵌套验证 `422 {detail: "Invalid bad case request"}`；持久化或响应验证
`500 {detail: "Bad case persistence unavailable"}`。沿用 EvaluationRoute 安全包装方式，
只用于新路由，不改变旧评测报错。不得返回或记录 validation input、SQL 参数、异常消息。

## 6. 拟议 Persistence Model（H1）

迁移暂定 `0013`，父 `0012`；实施时复核唯一 head。不修改 `0001`–`0012` 或已有表。
所有 FK `ON DELETE RESTRICT`；UUID/timestamps 使用现有数据库默认模式。

`bad_cases`：

| Column | 类型 / 约束 |
|---|---|
| id / workspace_id | UUID PK / FK workspaces.id；UNIQUE(id, workspace_id) |
| source_run_case_id | UUID NOT NULL；composite FK -> evaluation_run_cases(id, workspace_id)；UNIQUE(workspace_id, source_run_case_id) |
| origin_kind | VARCHAR(32)，第 4 节枚举；服务派生、不可修改 |
| title / description | VARCHAR(255) / TEXT；NOT NULL；trimmed/nonblank/长度 checks |
| category / status | VARCHAR(32) / VARCHAR(16)，NOT NULL，第 4 节枚举/default |
| possible_cause / handling_note / resolution_note | nullable TEXT；长度、非空白、NUL checks |
| revision | INTEGER >= 1，NOT NULL，default 1 |
| created_by / updated_by | UUID NOT NULL；各自 composite FK -> memberships(user_id, workspace_id) |
| created_at / updated_at | TIMESTAMPTZ NOT NULL，default now()；服务维护 updated_at |

CHECK 结束状态 iff resolution_note 非 null；所有存储文本拒绝 NUL。
索引 `(workspace_id, created_at, id)`、`(workspace_id, status, created_at, id)`、
source_run_case_id、created_by、updated_by。其他索引仅在实际查询证明必要时提出。
跨表 source terminal 与 origin/result 一致性由 scoped 服务验证；FK 不宣称校验状态。

`bad_case_history`：id UUID PK、workspace_id UUID FK、bad_case_id UUID composite FK
-> bad_cases(id, workspace_id)、actor_id UUID composite FK -> memberships(user_id, workspace_id)、
revision INTEGER >= 1、event VARCHAR(16)、change_reason nullable VARCHAR(1000)、
before_values nullable JSONB、after_values JSONB NOT NULL、created_at TIMESTAMPTZ default now()。
UNIQUE(bad_case_id, revision)，索引 `(workspace_id, bad_case_id, revision)` 与 actor_id。
CHECK created iff revision=1/before_values IS NULL，updated iff revision>1/before_values
为非空 object；after_values 为非空 object；event/文本限长；使用 `IS TRUE` 防 SQL NULL 绕过。
Pydantic/服务严格校验人工字段 allowlist：title、description、category、possible_cause、
handling_note、status、resolution_note；JSON 不接受源快照、secret、任意扩展字段。
数据库 checks 仅证明结构，不代替完整字段/前后值契约。

创建 source lookup、问题和第一条历史原子提交；唯一冲突捕获后 rollback 再返回 409。
PATCH 用 scoped `SELECT FOR UPDATE`、5 秒 lock timeout，获取最新行后校验 revision，
合并状态、更新 revision/updated_by/time，写历史，一次 commit。异常全部 rollback。
当前权限在处理开始及提交/保密读返回前复核；不新建长期锁定授权主体的架构，
仍有最终授权读取后发生撤权的既有短暂竞争窗口。外部调用不存在。

## 7. Authorization / Isolation（H2）

所有操作复用 CurrentUser 与 AgentAdministratorMembership：active User、active Workspace、
active Membership 且 role 为 agent_admin/system_admin。employee/knowledge_admin 拒绝。
不新增角色、不扩大 KB/Approval 权限；管理员可编辑同 Workspace 所有问题，不限创建人。
新增管理面须审批，不把“复用依赖”当作隔离自动成立的证明。

授权先于来源/问题查询。每个查询、join、filter、history 与 source 都约束 route Workspace；
Run Case 还校验所属 Run。foreign/missing、同 Workspace 错配父路径均相同 404。
历史 actor Membership 后续禁用不改写记录，但当前读者必须仍有权限。
不能信任请求中的 created_by/updated_by/workspace_id，不能以 source UUID 当访问凭证。
不新增 RLS、鉴权设计或可执行业务权限。

## 8. Confidentiality（H3）

标题、描述、人工原因/备注与历史是 Workspace-confidential 明文，沿用数据库/备份控制。
首版只允许合成/脱敏问题描述；UI 明示不得粘贴生产 PII、凭据、完整生产问答、
Tool 参数/结果或 Provider payload。无自动 DLP 或加密/删除保证。
列表标题同样要求脱敏；正文和前后历史仅详情/历史 API 返回给当前合格管理员。
历史保留旧值，编辑清空不能删除旧敏感内容；没有保留期、purge、导出或附件。
新表仅引用已有 Run 内容，不把它复制进历史或 Feature 014 metadata-only 日志。
新增 CRUD 不接入执行日志 recorder，变更审计来自原子 history。
任何操作都不调用 Provider/Tool adapter、不创建 Approval/Mock 写入、不外传问题或评测数据。

## 9. Frontend（H4）

- 运营分组增加“问题案例”，仅现有 Agent/System 管理员可见；后端独立强制授权。
- 终态 Run Case 详情显示“登记问题”；FAIL、ERROR、PASS 人工复核入口分别说明来源，
  pending/running 不允许提交。重复登记提示刷新/查看原问题，不自动覆盖。
- 列表分页、固定过滤；详情展示历史源输入/期待/actual/checks、ERROR 分类、dry-run/
  simulation 标签；不虚构答案正文或把 ERROR 展示为错误答案。
- 表单支持分类、人工可能原因、处理备注、状态及人工结论。结论/重开有变更理由。
  revision 冲突提示重新读取、手动协调，不能自动重提或默默覆盖输入。
- 历史展示时间、actor ID、变更理由与人工字段前后值；“已处理”明确为人工判断。
- 所有内容 literal escaped text；加载、空、失败、提交锁、重复操作及长文本可用。
  Workspace/logout 清空保密状态，late response guard；ambiguous timeout 先刷新核查。
  复用 017 中文组件/样式，不新建完整 Dashboard、设计系统或公共示例数据。

## 10. Acceptance Criteria

1. 终态 FAIL/ERROR/PASS 可建立对应问题；源 running/pending 被拒绝且无写入。
2. 不同 Run 中同一 Case 可建立不同问题，同一 Run Case（含已结束问题）最多一条。
3. 原始输入/期待/结果不变；源定义禁用/修改后仍展示 captured evidence。
4. 人工分类、原因、状态与结论遵守第 4 节规则；不宣称自动诊断/质量评分/复测通过。
5. revision 防覆盖；原子且连续 history；失败、冲突、无变更不会留下部分写入。
6. 所有 endpoints/filters/history/source 满足角色与 Workspace 隔离、固定安全报错。
7. 中文 UI 可完成登记、筛选、查看、编辑、结束、重开；保密状态与 XSS 防护有效。
8. 不调用模型、执行 adapter、创建 Approval、改写 Run/metrics 或泄露正文到日志。
9. Phase B 必需验证无跳过、diff 已自审、独立复审无阻塞、commit/push/PR 更新完成。
   人工合并后才称 Feature 018 交付。

## 11. Test Requirements 与本轮 Verification

Phase B 先专项后回归：

- 单元：所有来源与状态组合、严格字段/null/长度/空 PATCH/revision、人工历史 allowlist。
- 真实 PostgreSQL HTTP：四角色及无/禁用 Membership/User/Workspace，foreign/missing
  与错配 Run、过滤/分页、禁用源仍可读、secret sentinel 的 validation/persistence 报错。
- 独立 Sessions：重复创建、陈旧 revision、并发编辑/状态、锁超时、历史失败全回滚。
  history 与 revision 连续；无变更不写；真实撤权场景覆盖复核点。
- 迁移 `0012 -> 0013`、downgrade/re-upgrade、唯一 head、metadata parity、旧迁移字节不变、
  composite FK/check/unique/SQL NULL 负例，仅经安全检查的 `enterprise_ai_workbench_test`。
  集成 fixture 会重置 public schema，测试库使用须串行，不接触运行/生产数据库。
- fail-on-call spies 验证 Provider/adapter/Approval/Mock/执行日志无新增；源快照及指标逐值不变。
- 前端：来源标签、角色、过滤/分页、history、冲突恢复、必填状态理由、XSS、重复提交、
  ambiguous timeout、Workspace 切换/logout/迟到响应、移动/桌面布局。
- 完整 backend pytest（含 PostgreSQL，无必需 skips）、Ruff；完整 frontend tests、
  `pnpm lint`、`pnpm build`；浏览器 QA；`git diff --check`；自审及独立安全/迁移复审。

本轮 Phase A 只核验 GitHub 基线、文档与现有契约一致性、链接、冲突标记、whitespace 和
scope diff。应用测试/数据库迁移未运行；历史 Feature 测试数量不作为本轮证据。

## 12. 实施前审批项与风险

| Gate | 待批准的具体范围 |
|---|---|
| H1 数据模型 | 第 6 节两表与 additive 0013；仅指定专用测试数据库 migration 验证；原始表/迁移不改 |
| H2 管理面及隔离 | 第 5/7 节五个接口与既有 admin policy 复用、scoped joins/composite FK、权限复核及独立复审 |
| H3 内容与历史 | 脱敏人工文本明文及 append-only 前后值历史；只引用原始评测、不外传，无自动删除/DLP |
| H4 产品与 UI | 第 4/9 节来源约束、人工状态、revision 冲突、中文界面；不执行、不自动关闭或比较版本 |

`AGENTS.md` 的 High-Risk Changes 明确要求在新增迁移和安全敏感变更实施前人工审批。
批准须引用本提案 commit 及 H1–H4；只授权该规格的实现与专用测试数据库验证。
不授权运行/生产迁移、生产敏感内容、授权政策扩大、外部写入、新依赖/架构或合并 main。
Phase B 独立复审按 AGENTS 高风险 Review Policy 执行。

已知限制：人工原因/结论可能不准确；历史永久保留旧人工文本；没有源外证据；
无跨 Run 聚类、可比性/复测证明、语义评分、完整数据库防篡改或撤权零竞争窗口保证。
PR #40 仍未合并，实施前须核对其最终范围。

## 13. Out of Scope / 后续

Feature 023 的 Run/Agent 版本比较与复测关联、Feature 022 配置版本、019/020 管理 UI、
生产日志转 Case、独立无来源问题、答案全文采集、自动根因/LLM judge、自动修改 Prompt、
运行重试/调度、真实工具、Workflow、通知/指派/SLA、附件、全文搜索、导入导出、
保留期/purge、新框架、部署、运行数据库迁移与自动合并，均不属于 018。

本轮规格 PR 仅关联实现 Issue，不用 `Closes` 提前关闭它；Phase B 经验证的实现 PR
才使用 `Closes #<issue>`。本轮停止在规格可审阅，批准后仍只实施 018。
