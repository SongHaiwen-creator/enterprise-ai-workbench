# 完整 MVP 交付计划

日期：2026-10-03。状态：后续 MVP 项目规划；本计划未实施后续功能。
规划分支：`docs/mvp-delivery-plan`。
跟踪：[Issue #38](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/38)。

依据：PRODUCT_SPEC、ARCHITECTURE、DATABASE、ROADMAP，以及 Features 001–016。
本计划把现有规格中的能力拆成可在工作树中交付的最小版本；新增功能的
详细 API、数据约束、权限及迁移，仍由各自 Feature Spec 定义。
规划不等于批准未来数据库迁移、授权策略或架构变更。

## 1. 基线与目标

已核验远端 `main` 为 `746fbeb9580fed6719abd9d7014297151aaa55f8`。
Feature 016 的 PR #37 于 2026-10-03 合并，Issue #36 已关闭。
Features 001–016 已交付，但数据库运行环境是否已升级不能由 Git 状态推断。
本次规划不运行数据库迁移或应用测试，不改变应用代码。

最终核验时，[Issue #39](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/39)
已在另一个工作树启动 **Feature 017 Chinese UI Refresh**，分支
`feat/chinese-ui-refresh`，尚未合并。它负责中文首页、`/app` 入口与现有界面
统一样式，不增加知识/Agent/Tool 管理、Workflow 或 Bad Case 能力。
本计划因此顺延为 018–029；等待 017 人工合并后，018 从更新后的 main 开始。
后续 UI 功能复用 017 的导航、中文标签和样式，不重复另做首页或设计系统。

完整 MVP 的目标是让四类用户通过界面完成日常工作：员工提问、查询 Mock
业务数据、提交和追踪申请；知识管理员维护知识及版本；Agent 管理员配置
Agent、Tool、Workflow 并分析评测；系统管理员管理 Workspace、成员和审批。

保留当前 MVP 边界：单体后端、现有 PostgreSQL/pgvector、已有 OpenAI 协议、
本地 Mock 业务系统。复杂多 Agent、训练、微调、Kubernetes、高并发、完整
SSO、真实 ERP 和真实金融交易仍不属于 MVP。现有 API 与安全规则继续有效。

## 2. 能力覆盖与缺口

| 规格能力 | 当前证据/状态 | 完整 MVP 需要补齐 | 对应计划 |
|---|---|---|---|
| User、登录、基本资料 | 003 登录和 `/auth/me`；受控账户创建工具 | 可见个人资料、受控账户准备说明；不要求公共注册或新认证体系 | 028、029 |
| Workspace、成员、角色 | 001–005；创建 Workspace API、选择和成员管理 UI | 创建 Workspace 的界面入口及完整操作体验 | 028 |
| Knowledge Base 管理 | 006 API 已有 | 创建、编辑、启停管理 UI | 019 |
| Document 上传、解析、索引、状态 | 007–008 API 已有 | 管理 UI；逻辑文档与版本切换 | 019、021 |
| RAG 与 Citation | 008–010 已有检索、生成及问答 UI | 新文档版本替换后的检索隔离和旧引用可追溯 | 021、029 |
| Agent 配置、Intent Routing | 011 API 与 Assistant 已有；配置管理 UI 未交付 | 管理 UI、不可变配置版本 | 020、022 |
| Tool 配置、分配及 Mock 执行 | 012 API/Assistant 已有；管理和分配 UI 未交付 | 管理 UI；继续仅使用注册能力与后端验证 | 020 |
| Human Approval | 013 读写 API、审批 UI、Mock 写入已交付 | 员工申请追踪；Workflow 中复用既有审批边界 | 025、027 |
| Workflow 配置与执行 | 产品/数据库规格有规划；无模型和执行 API | 有限步骤配置、校验、运行历史、审批等待和安全恢复 | 024、025 |
| Conversation | 数据库规格有规划；Assistant 无持久会话 | 自有会话历史、有限参数补全、敏感操作确认 | 026 |
| 员工业务请求状态 | 013 有审批与 Mock 记录；缺统一员工入口 | “我的申请”列表与详情、决策/执行状态 | 027 |
| Execution Logs | 014 元数据日志与管理 UI 已交付 | 新功能接入同等可追溯边界；不能把正文塞进既有日志 | 025–029 |
| AI Evaluation | 015–016 定义、执行、结构化评分与 UI 已交付 | Bad Case 闭环、配置版本追溯及运行比较 | 018、022、023 |
| Bad Case Management | 路线图有规划；未实现 | 人工分类、原因、处理和复测证据 | 018、023 |
| 可使用、可验证、可交付 | 现有单元/集成/组件测试；无浏览器 E2E 或 CI 目录；README 简略 | 四角色完整流程验收、CI、受控发布和操作说明 | 029 |

API 已交付不代表管理 UI 已存在。既有 Feature Spec 明确保留为 API-only 的
能力，在新 Feature 中增加界面，不追溯修改它们当时的交付范围。

## 3. 开发顺序与最小范围

以下编号是建议的规划编号。每项开始时重新检查最新 main、Issue 与规格；
若届时已有同编号功能，应调整编号，不能覆盖其他工作。

| 顺序 | Feature / 分支 | 最小范围与主要验收 | 依赖 | 工作量/风险 |
|---|---|---|---|---|
| 018 | Bad Case Management / `feat/bad-case-management` | 从终态 Run Case 人工建立问题；区分行为 FAIL、运行 ERROR 和人工复核；分类、原因、处理状态、历史；关联源结果并防重复；旧评测不可被编辑 | 016 | 中；迁移、隔离、保密内容 |
| 019 | Knowledge Administration UI / `feat/knowledge-admin-ui` | 知识库创建/编辑/启停，文档上传、状态、索引/重索引和启停；失败可恢复，引用已存在 API；knowledge_admin/system_admin 可管理，员工不可管理 | 006–010 | 中；已有权限回归 |
| 020 | Agent & Tool Administration UI / `feat/agent-tool-admin-ui` | Agent 创建/编辑/状态，注册 Tool 配置、分配/解除；只读展示注册能力限制；agent_admin/system_admin 可管理；不新增执行权限 | 011–013 | 中；已有权限回归 |
| 021 | Document Version Management / `feat/document-version-management` | 逻辑文档与不可变版本；上传替代版本并显式激活；解析/索引失败保持旧版本可用；新检索只使用当前有效版本，历史引用保留可追溯信息 | 019 | 大；迁移、检索隔离、原子切换 |
| 022 | Agent Configuration Versions / `feat/agent-configuration-versions` | 保存不可变配置版本、查看差异、显式激活；版本记录 Prompt 和 Tool 分配配置；旧评测/审批不改写；权限或 Tool 变化仍按当前授权/漂移规则处理 | 020、016 | 大；迁移、配置/授权一致性 |
| 023 | Evaluation Run Comparison / `feat/evaluation-run-comparison` | 比较同 Workspace、同 Dataset 的两次 Run；展示配置差异、指标分母、Case 结果变化；内容/期待变化标记不可直接比较；Bad Case 关联复测，不凭一次 PASS 自动关闭问题 | 018、022；完整知识版本标识依赖 021 | 中；保密读取、可比性 |
| 024 | Workflow Definition / `feat/workflow-definition` | 表单式配置固定线性流程和有限类型步骤；校验输入输出及同 Workspace 引用；草稿/激活/禁用、不可变已发布版本；尚不执行 | 020、022 | 大；迁移、架构、配置权限 |
| 025 | Workflow Execution / `feat/workflow-execution` | 员工可运行被授权流程；逐步执行、持久状态/步骤历史；敏感步骤进入已有 Approval；审批完成后显式继续并重查权限；重复继续不得重复写入 | 024、013–014 | 大；执行架构、审批、幂等与恢复 |
| 026 | Conversation & Parameter Collection / `feat/conversation-parameter-collection` | 本人会话创建/列表/详情/关闭，刷新可恢复；按注册 schema 补齐缺失字段并确认；重新检查当前权限；不把整个历史自动发送给模型，不从历史继承执行授权 | 025 | 大；迁移、内容保密、Provider egress |
| 027 | My Requests / `feat/my-requests` | 员工只看本人申请/流程；待审、拒绝、失效、执行成功/失败分别展示；支持既有策略下的本人取消；通过源记录读状态，不伪造另一个审批真相 | 025、026 | 中；对象级读取授权 |
| 028 | Workspace & Profile UX / `feat/workspace-profile-ux` | 对接现有 Workspace 创建 API、创建后选择、当前资料展示、现有成员管理体验；受控账户创建的入口/说明；不新增公共注册、密码重置或 RBAC 策略 | 005、027 | 小至中；已有权限回归 |
| 029 | MVP Acceptance & Delivery / `feat/mvp-acceptance-delivery` | 四角色、两个 Workspace、三业务场景及评测闭环 E2E；CI、启动/迁移/备份恢复说明、脱敏示例、受控本地或单机部署验收 | 018–028 | 中至大；测试依赖、部署审批 |

工作量为相对大小，不是日期承诺。UI 功能通常较小；版本、会话和 Workflow
涉及跨事务状态及保密边界，不能按普通 CRUD 估算。每个 Feature 的 Phase A
确认后再估计实现、验证、复审及人工合并所需时间；当前不设固定截止日期。

批次验收：

- A：018–020。管理员可在界面维护知识/能力，失败评测可进入人工处理。
- B：021–023。知识与 Agent 有版本，评测能比较，问题有可追溯复测证据。
- C：024–027。流程可配置、审批等待可恢复，员工可补参数并追踪本人申请。
- D：028–029。四角色全流程可用，操作说明和发布验收齐全。

当前先完成已经启动的 **017 界面改版**；其人工合并后，下一项是
**018 Bad Case Phase A**，而不是一次性开始 018–029。

## 4. 关键设计边界

### Bad Case 与质量比较

FAIL 是结构化期待不匹配；ERROR 是未能形成可评分结果；两者不能混成
“回答质量差”。人工原因是管理员判断，不是系统已证明的根因。问题记录
关联不可变源结果，不复制生产日志正文到评测。允许记录人工发现的问题，
但证据的保存、脱敏和权限必须在 018 规格中约定。

022 首版只要求“按当前激活配置发起 Run，Run 记录版本”。不默认增加按
任意历史版本执行的能力。023 可以比较历史 Run，并须校验 Case 输入、期待、
类别、Scorer、知识版本等；不同版本的 Dataset/Case 不能凭 ID 相同就声称
效果提升。ERROR、pending 和不同分母须保留原有意义。

现有自动指标仍为可验证的结构化指标。语义回答正确性、引用内容正确性和
检索相关性若要评分，先定义人工标注 ground truth 与审查协议；本计划不把
LLM-as-a-Judge 或未定义的准确率塞入 MVP。可以展示人工复核结果，明确其来源。

### Workflow

首版使用表单、线性步骤和应用注册能力；不做画布、任意代码/HTTP 节点、
循环、并行 DAG、跨 Workspace、队列/定时器或自动重试。建议首版节点为
输入校验、现有知识查询、注册 Mock Tool、结果展示；是否支持多于一个写步骤
以及执行预算，由 025 Phase A 明确，不能直接沿用评测预算。

“敏感 Tool”不能成为绕过审批的节点。当前 Approval 决策服务已负责 Mock
写入；Workflow 只观察这次执行事实，不能在恢复时再次调用写 adapter。
等待审批期间不持有请求线程或数据库事务；仅持久化等待状态。首版用用户
显式继续恢复，重新检查主体、Workflow/Agent/Tool 状态和快照，不引入 Worker。
自动恢复如确有必要，另作架构决策。

Workflow 运行不能单纯复用 Agent 路由反复猜测下一步。024–025 Phase A
需按 AGENTS 的开源复用政策评估已有依赖/组件与小规模确定性执行方案，
列明许可、维护、兼容、部署和成本后再选择；本规划未选择或安装执行框架。

### 会话、参数与请求追踪

会话历史默认限本人、同 Workspace；管理员日志权限不自动获得读聊天正文的
权限。参数来源区分用户输入、模型建议和后端身份；不能用会话中的姓名或 ID
冒充运行主体。收集完整参数后再次验证，并为敏感提交提供确认动作；已有
Human Approval 决策仍由原策略控制。补参数是有限表单/提示，不要求开放式
长期记忆或多 Agent 对话。

027 优先聚合现有 Approval、Mock 请求和 Workflow Run，不重复创建另一套
审批状态机。取消不会回滚已完成的业务写入。Conversation 与 Execution Log
分别存内容和元数据，新功能不能扩大 014 日志的内容边界。

### 用户与发布

首版账户继续采用受控预创建；现有 `/auth/me` 满足只读基本资料，028 补 UI。
自助注册、邀请邮件、密码重置、SSO、刷新令牌均不是隐含任务。以后要做这些
能力，应另起认证设计规格和审批。

发布首版优先现有栈的本地/单机可重复运行。新增容器文件、CI 或 E2E 工具
先说明依赖和验证环境；生产数据库迁移、联网 Provider 冒烟和部署需单独
具体授权。运行环境迁移不与“生成迁移文件、专用测试 DB 验证”混为一项批准。

## 5. 每个 Feature 的交付包

每项独立一套 Spec、Issue、分支和 PR；一张 PR 包含该能力的后端、前端和
测试，不把未经合并的接口当下一功能的稳定依赖。

Phase A 要定义：目标、明确范围/非范围、角色与对象级权限、状态机、API/
数据契约、同 Workspace 引用、并发/重复请求、保密/egress、异常恢复、验收、
测试矩阵、复用决策、迁移/架构等高风险审批点。API 路径和迁移 revision
在该阶段最终确定，本计划不提前分配 0013 之后的迁移号。

Phase B 才实施已批准内容。新增状态一般要给出非法转换、竞争请求、权限
撤销、跨租户、输入越界和失败事务的测试。先 Feature 测试，再全量 pytest
含 PostgreSQL、Ruff、前端测试/lint/build；有 UI 主流程时再做浏览器验收。
必须无必需测试跳过。高风险项需要独立复审；AI 停于 PR-ready，人工合并。

每次合并更新当前 Spec、ROADMAP 与交付记录；旧设计/历史验证日期保留。
下一个功能在新聊天里从合并后的最新 main 开始。

## 6. 工作树安排

工作树用于隔离分支和环境。当前 AGENTS 规定一次交付一个 Feature；采用
“一项 Feature、一棵实现工作树、一个新聊天、一张 PR，合并后开始下一项”。
可以把当前 Feature 的后端、UI、测试、复审拆成任务，但不同时实施两个
不同编号的 Feature。此计划保留这条规则，不以工作树可并存作为并行授权。

建议命名：

| 用途 | 分支 | 示例目录 |
|---|---|---|
| 本项目规划 | `docs/mvp-delivery-plan` | 当前 1452 工作树 |
| 当前 Feature 实现 | 如 `feat/bad-case-management` | `D:\Projects\worktrees\eaw-018` |
| 当前 Feature 复审 | 指向该 Feature 精确提交的 detached worktree | `D:\Projects\worktrees\eaw-018-review` |

后续启动示例，仅为说明，本次不执行：

```powershell
git fetch origin main
git worktree add -b feat/bad-case-management 'D:\Projects\worktrees\eaw-018' origin/main
```

每次复制启动指令时，先确认功能编号、目录尚未被占用和 main 已包含前置 PR。
现有 dirty 工作树的 next-env、个人 AGENTS/CLAUDE、备份目录不随新功能提交。
依赖包、缓存和本地 `.env` 在每棵实现工作树中单独准备，不提交机密。

环境资源需要单独管理：

- 不同开发服务器用不同端口；统一配置 UI 对应的后端地址，不混用浏览器会话。
- **PostgreSQL 集成测试串行执行。** 当前 fixture 会重建测试库 public schema；
  不能让两个工作树同时操作同一个 TEST_DATABASE_URL。当前部分测试明确检查
  `enterprise_ai_workbench_test` 名称，不能只换库名就声称支持并行。
- 若以后确需多套独立测试库，先改造硬编码测试约束和安全检查，再单独批准
  测试环境创建/清理；不可把 `_test` 后缀当唯一生产安全保证。
- 不同工作树共享 Git 主仓库，不在两个地方 checkout 同一普通分支；迁移号
  由当前 Feature 单独编写，合并时确认单一 Alembic head；不修改旧迁移。
- 复审只读指定提交；运行集成测试同样遵守测试库排他使用。开发/测试数据库
 以及对应迁移动作必须明确分开。

## 7. 可复制的 Feature 启动指令

替换编号和名称，并在新的工作树/聊天使用：

> 从最新 origin/main 开始 Feature NNN：名称。先读 AGENTS、四个来源文档、
> MVP_DELIVERY_PLAN 和相关 Feature Spec；核验所有依赖已人工合并。
> 本轮先完成 Phase A：范围、规则、API/数据、验收、测试、风险和审批点；
> 建立对应 Issue、分支和 Spec，提交推送并准备 PR。
> 对迁移、授权、安全或架构变更，列出具体审批项和 proposal commit 后等待
> 批准，不实施未批准 Phase B，不运行非测试数据库迁移，不自动合并。
> 一次只处理这一项 Feature，不开始后续功能，保留无关本地文件。

Phase B 批准模板：

> 批准 Feature NNN 的 proposal commit <SHA> 中明确列出的 H1–Hx。
> 仅授权该 Spec 范围的实现与指定专用测试数据库验证。
> 不授权运行/生产迁移、生产敏感内容、新权限、额外基础设施或自动合并。
> 完成专项与回归验证、独立复审、提交推送并更新 PR；停在 PR-ready。

## 8. 完整 MVP 最终验收

以脱敏数据、四种角色和至少两个 Workspace 完成下列流程：

| 场景 | 验收证据 |
|---|---|
| 系统准备 | 受控账户登录、创建/选择 Workspace、配置成员；错误角色和另一个 Workspace 均被后端拒绝 |
| 知识问答 | 管理员上传、索引、替换文档版本；员工得到当前版本证据与引用；旧/禁用版本不进入新检索 |
| 业务查询 | 员工调用三个注册 Mock 能力中的读能力，返回受授权的模拟结果；不能枚举他人信息或使用未知 Tool |
| 敏感申请 | 补齐参数、确认提交、进入审批；本人不能自批；其他合格审批人批准后仅一次 Mock 写入；员工可见决策与执行结果 |
| Workflow | 管理员配置并激活流程；员工运行；待审可跨刷新恢复；撤销权限/配置漂移阻止继续；重复继续不重复业务写入 |
| Conversation | 本人历史恢复和关闭；不同用户/Workspace 不可读；历史不会给予额外执行授权 |
| 评测闭环 | Dataset/Case -> Run -> FAIL/ERROR -> Bad Case -> 人工修改配置 -> 新 Run -> 可比性检查 -> 人工处理结论；旧结果和版本不可覆盖 |
| 运维与交付 | 新环境按说明可启动；CI 必需检查通过；错误无机密泄露；备份/恢复在指定非生产环境验证；部署与迁移按独立授权执行 |

完成标准：所有计划内 Feature 人工合并；每项验收有证据；无必需测试跳过；
MVP 文档明确已知限制；未解决缺陷由维护者明确接受。测试基线使用每次
交付的实际结果，不把 Feature 016 的历史 1520/98 项结果冒充未来验证。
