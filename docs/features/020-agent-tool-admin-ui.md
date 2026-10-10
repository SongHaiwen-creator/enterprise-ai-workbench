# Feature 020 - Agent & Tool Administration UI

Status: Phase B implemented and verified; PR #49 awaiting human review and merge
日期：2026-10-10（Asia/Shanghai）
Baseline: `origin/main` at `2222e90ce4375c243b810376bb47a5f235e4b8d0`
Branch: `feat/agent-tool-admin-ui`
Issue: [#48](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/48)
Milestone: 既有 Agent / Tool 能力的管理界面补齐（后续 MVP 批次 A）
Risk: Normal；复用已有管理权限与执行边界，重点回归对象隔离和审批漂移行为。

## 1. Goal

让当前 Workspace 的 Agent 管理员和系统管理员通过中文界面创建、编辑和启停
Agent，配置三个已注册 Mock Tool，并为 Agent 分配或解除工具。管理员能看清
配置状态、分配状态与执行限制，员工继续通过既有智能助手使用有效能力。

Phase A 在 proposal commit `6cc4278` 完成规格、Issue、专用分支和草稿 PR。
用户随后以“approve”批准规格实施，并在专用测试库授权问题中要求“重试”，随后
要求“继续”。Phase B 已实现，前端、浏览器、PostgreSQL 专项与完整后端回归均已
通过，PR #49 已准备供人工审阅；须人工合并才完成交付。
证据见 `docs/features/020-agent-tool-admin-ui-verification.md`。

## 2. 最新规划与实现基线

已 fetch 并核验 HEAD 与 `origin/main` 同为上述提交，初始工作树干净。
Feature 019 已通过 [PR #47](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/47)
于 2026-10-10 人工合并；依赖 Features 011–013、界面基础 017 均已在 main。
ROADMAP 与部分历史规格保留的“awaiting human merge”不代表当前 GitHub 状态。

Feature 020 的后续规划来自尚未合并的
[PR #40](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/40)，
`origin/docs/mvp-delivery-plan` at `77acb1a17d09f87f13dc8b15d7028f2ce815ff76`
中的 `docs/MVP_DELIVERY_PLAN.md`。用户本轮指定从 020 开始，采用其中 Agent &
Tool Administration UI 的最小范围；不复制整份规划、不合并 PR #40，也不视为
批准 Features 021–029。Workflow 在该规划中已延期。

已读取 AGENTS、PRODUCT_SPEC、ARCHITECTURE、DATABASE、ROADMAP，相关
Features 004、011–013、019，核对 017 导航基础及当前 API、schemas、服务和前端。

| 已有证据 | 对本功能的约束 |
|---|---|
| `backend/app/api/routes/agents.py`、`schemas/agent.py` | 管理列表须 `include_inactive=true`；列表不含 Prompt，管理详情才返回；创建为 draft |
| `backend/app/api/routes/tools.py`、`schemas/tool.py` | 已有配置 CRUD（无对象删除）、分配 GET/PUT/DELETE；解除为 204；创建为 disabled |
| `backend/app/services/tools.py` | Workspace 内 tool_key 唯一；允许配置未激活对象的分配；PUT/DELETE 关系操作幂等 |
| `backend/app/services/tool_registry.py`、`schemas/tool_calling.py` | 恰好三个注册能力；风险、参数、执行器及审批策略由后端代码固定 |
| `docs/features/013-human-approval.md` Sections 15–16 | 审批时检查当前权限与快照漂移；解除后重加的同一关系无 revision，是已有已知限制 |
| `frontend/utils/api.ts::requestJson` | 已有 AgentSummary 与 active-only listAgents；成功路径始终解析 JSON，需兼容 204 |
| `frontend/app/app/page.tsx`、`components/platform-navigation.tsx` | shell 共享 active Agent 列表、当前 Workspace/角色和 mutation pending；管理列表不能替换员工列表 |
| `backend/tests/integration/conftest.py` | 集成测试重建专用测试库 public schema，Phase B 须具体授权且串行执行 |

## 3. Scope

Phase B 的拟定范围：

- 在 `/app` 运营管理导航增加“Agent 与工具”，仅当前 Workspace 的
  `agent_admin` / `system_admin` 可见和进入，复用现有中文、蓝白样式和移动导航。
- 一个管理区域内提供 Agent 列表/详情、创建/编辑、独立状态操作和工具分配区域。
- Tool 配置列表/详情、从固定注册能力选择创建、编辑名称/说明、启用/禁用。
- 只读能力说明，清楚区分注册限制、Workspace 配置、Agent 分配及运行时授权。
- 为既有接口增加 TypeScript 类型与调用函数，兼容成功无 body 的 204 响应。
- 管理后同步 shell 的 active Agent 列表；增加 API、组件、shell 回归及浏览器验收。

无新增后端 API、数据库字段、migration、权限策略、Provider 调用、执行通道或依赖。
若实现发现现有契约不足，先修订规格，不把补接口或安全策略变更视为隐含授权。

## 4. Business Rules

### 4.1 角色、对象和保密

| 当前 Workspace 角色 | 管理入口、完整 Agent 配置、Tool 配置/分配 | 既有 active Agent 摘要与使用 |
|---|---|---|
| employee | 无；后端管理请求拒绝 | 保留 |
| knowledge_admin | 无；后端管理请求拒绝 | 保留 |
| agent_admin | 有；按既有策略管理 | 保留 |
| system_admin | 有；按既有策略管理 | 保留 |

1. 角色来自当前 Workspace 的 Membership，不能从其他 Workspace 推导。
   导航可见性只改善体验；每个 API 仍由后端校验 active User/Workspace/Membership。
2. 管理 ID 仅来自当前 Workspace 的列表/详情；Agent 与 Tool 必须同 Workspace。
   外 Workspace 与不存在的对象按既有 scoped 404 处理。
3. 未授权角色不挂载管理组件、不读取 Prompt 或 Tool 配置。401 清会话；403 清除
   受保护管理状态并阻止操作。撤权后即使客户端还显示旧角色，后端也必须拒绝。
4. Prompt、草稿、配置数据与 token 仅留内存，不放入 URL、浏览器存储、日志或遥测。
   名称、说明、Prompt、错误按普通文本渲染，不执行 HTML/Markdown。
5. 表单提示 Prompt 不得包含密钥、凭据或敏感业务记录；不宣称提供自动脱敏/DLP。
   保存配置仅走已有 FastAPI/PostgreSQL；之后使用 Agent 时 Prompt 仍按现有路由/
   Tool selector 边界发送至已配置 Provider，保存本身不触发模型调用或收费测试。

### 4.2 Agent 管理与状态

- 管理列表使用 `include_inactive=true`，显示 draft/active/disabled，沿用 `name,id`
  排序。员工 Assistant 继续使用默认 active-only 列表，不得共享完整 Prompt 类型。
- 创建只发送 name、description、system_prompt；服务端默认 draft。名称、Prompt
  trim 后分别为 1–255、1–8000 字符；description 可空，最多 5000 字符。同名合法。
  creator、Workspace、时间和 status 不进入创建请求。
- 详情通过管理 GET 获取 Prompt；创建/编辑使用可见 label 和多行 Prompt 输入。
  明示 Prompt 控制路由范围/工具选择，不声称会修改现有 grounded-answer 生成提示。
- 编辑从最新读取的详情初始化，只 PATCH 实际修改字段；空描述规范为 null，
  name/system_prompt/status 不可 null。无变化不发送空 PATCH，取消不写入。
- 状态操作与内容保存分开，状态 PATCH 只发送 `{status}`。现有后端允许三个枚举
  之间任意转换；UI 支持切换到其他两个状态，不发同状态请求，不创造新发布规则。

| status | 中文 | 既有行为 |
|---|---|---|
| draft | 草稿 | 可编辑及分配，不能用于新的 Agent 请求 |
| active | 已启用 | 可被当前 Workspace 成员选择；运行时仍检查工具及授权 |
| disabled | 已禁用 | 保留配置/分配，不能用于新的 Agent 请求 |

任何实际状态切换前确认。激活说明会开放给当前 Workspace 成员；从 active 改为
draft/disabled 说明新请求不可用，并可能影响尚待审批的申请。确认框为操作体验，
不新增后端 Human Approval。禁用不删除、级联禁用 Tool 或重写历史结果。

### 4.3 Tool 配置

1. Workspace Tool 列表包含 active/disabled，沿用 `name,id` 排序；无分页、新搜索
   或注册目录 API。创建从固定三个 tool_key 中选，不允许自由输入能力 key。
2. 创建请求仅 `{tool_key,name,description}`，后端默认 disabled；name、description
   均必填，trim 后分别 1–255、1–5000 字符。description 不能 null 或空白。
3. 一个 Workspace 对每个 tool_key 只有一份配置。已存在的能力不能再次选择创建；
   三份齐全时显示“所有注册能力均已配置”。客户端判断仅改善体验，并发创建仍可能
   返回 409。收到 409 刷新列表、指向已有配置，不自动替换、启用或重发创建。
4. 编辑只 PATCH 实际修改的 name/description；status 独立操作。tool_key、
   operation_type、risk_level、参数 schema、审批策略只读，无 URL、密钥、代码、
   HTTP 方法、模型或执行器字段。名称/说明是显示文案，不改变 Tool selector 指令。
5. 启用/禁用前确认：启用只使满足当前 Agent 分配等条件的能力可被选择；禁用影响
   所有分配此 Tool 的 Agent，保留关系，且可能使待审批申请在审批检查时失效。
   不声称已立即取消所有 pending Approval，不扫描或更新 Approval 表。

### 4.4 注册能力的只读说明

当前没有未配置能力的注册目录 GET。前端维护窄的中文说明常量，仅覆盖基线的
三个 key；说明是帮助文本，不是运行时授权或 schema。已配置对象的类型/风险
展示服务端返回值，不用本地常量覆盖。增加契约一致性测试检测说明与后端漂移；
未知 key 或异常配置不提供创建/分配快捷动作，显示不可用并联系管理员。

| tool_key / 中文能力 | 类型 / 风险 | 只读限制 |
|---|---|---|
| `get_reimbursement_status` / 查询本人报销状态 | read_only / low | 本地 Mock；参数为空；后端身份决定本人，不能传他人或报销单 ID |
| `get_employee_information` / 查询本人资料 | read_only / low | 本地 Mock；固定 subject=self，拒绝查询他人 |
| `create_it_access_request` / 提交 IT 权限申请 | write_sensitive / high | 仅创建待审批申请；审批合格后才有本地 Mock 写入，不授予真实权限 |

IT 申请参数说明：system 为 production_database / analytics_warehouse /
source_control；access_level 为 read_only / standard；production_database 仅允许
read_only；business_justification 为 trim 后 10–500 字符且无控制字符；
duration_days 为整数 1–90。这里只读展示，不提供参数填充、试运行或直接执行。
审批继续由同 Workspace、非申请人的 system_admin 决策，TTL 72 小时；不提供
审批人、免审批、风险级别或 TTL 编辑。本功能不修改 Feature 013 的任何规则。

### 4.5 Agent 与 Tool 分配

- 选中 Agent 时读取其已分配 Tool 列表，并与当前 Workspace Tool 列表按 ID 合并，
  显示“已分配/未分配”及独立的 Tool/Agent 状态。读取失败不能当空分配显示。
- 允许在 draft/disabled Agent、disabled Tool 上配置分配；标注“已分配，当前未生效”。
  active Agent + active Tool + 关系存在才是候选能力，仍不代表获得运行/审批授权。
- 每个关系使用单独“分配”/“解除”动作，PUT/DELETE 无 body。无批量保存，
  不在状态切换时隐式创建/删除关系，不为新 Agent 默认分配全部能力。
- 分配前确认即将开放的能力及限制；解除前确认新的请求不可选该能力，并可能
  影响待审批申请。成功以服务端响应和重新读取的关系为准，不乐观伪造结果。
- PUT 已有关系仍为 200；DELETE 已无关系仍为 204，只删除关联，不删除 Tool。
  不能把 204 空 body 的 JSON 解析失败报告成“解除失败”。
- 现有审批会检查当前配置/关系；不重写审批快照，不刷新成可继续执行的新快照。
  解除后重加同一关系没有历史 revision，不能保证检测短暂撤销；沿用 Feature 013
  的已知 Mock 限制，不以 UI 防重复承诺消除此缺口。配置版本由 Feature 022 设计。

### 4.6 并发、上下文与共享状态

1. 一个管理区域同一时间仅一个 mutation，同步锁阻止双击/回车重复提交；pending
   时锁定 Workspace、产品区域、Agent/Tool 选择及其他写入，沿用 shell pending。
   退出登录始终可用；放弃请求不能被描述为服务端回滚。
2. 读取采用 request generation 或等效机制。Workspace A -> B -> A、选择切换、
   token 变更、登出和卸载后，旧响应和旧回调都不能污染新上下文或触发写入。
   Workspace/角色变更立即清空 Prompt、草稿、详情、分配、错误和确认状态。
3. Agent/Tool 切换时清理对应编辑草稿；存在未保存修改时确认放弃，取消保持当前
   选择。普通读取可被切换打断，迟到响应不覆盖当前详情。
4. Agent 创建/编辑/状态成功后同步当前 Workspace 的 shell active-only Agent 列表；
   保留仍有效的 Assistant 选择，移除失效选择；新 draft 不可出现在员工选择器。
   Tool/分配变化刷新管理数据；返回 Assistant 使用原有后端检查，不加隐式试请求。
5. 接口没有 revision/ETag；跨管理员更新存在后写覆盖。本功能不承诺冲突检测、
   原子保存 Agent+Tool+分配、多接口回滚或配置历史，显示以最后服务端结果为准。
6. 写入成功后刷新失败提示“操作已完成，列表刷新失败”，提供 GET 刷新。网络中断
   或成功响应解析异常时提示“结果未确认，先刷新核对”，禁止自动重试写入。
   Agent 创建无去重保证；核对前重发可能创建同名的第二个 Agent。

### 4.7 错误与恢复

| 结果 | 行为 |
|---|---|
| 401 | 清会话、Prompt/草稿/配置，返回登录 |
| 403 | 清受保护管理数据、阻止操作，提示当前 Workspace 权限不足 |
| 404 | 清失效对象及分配选择，允许刷新当前 Workspace 列表 |
| 409 | Tool 已配置或冲突；刷新核对，不自动重新写入 |
| 422 | 安全字段/请求提示，保留当前仍有权限且上下文未变的可修正输入 |
| 503 | 注册配置不可用；停止相关分配/状态操作，提示联系管理员；不提供绕过设置 |
| 网络中断、其他服务错误 | 安全兜底；读取可手动重试，写入结果未确认时先读取核对 |
| 204 | 解除成功；不尝试 JSON 解析 |

复用 ApiError/displayMessage，不呈现 raw validation input、stack、SQL/Provider
错误正文。管理请求不应调用 Provider；502 等其他错误不得暗示工具已执行。
Tool 写入响应在提交后仍会经过注册表序列化；极端配置漂移下的 503 也不能证明
没有写入。此时停止操作、联系管理员核对，不自动重发或假定事务回滚。

## 5. API / Data Contract

统一前缀 `/api/workspaces/{workspace_id}`，以下均为已合并接口。

| Method | 后缀 | 请求 | 成功响应 |
|---|---|---|---|
| GET | `/agents?include_inactive=true` | 无 | 200 AgentSummary[]；管理权限 |
| GET | `/agents/{agent_id}` | 无 | 200 AgentConfiguration |
| POST | `/agents` | `{name,description?,system_prompt}` | 201 AgentConfiguration，draft |
| PATCH | `/agents/{agent_id}` | `{name?,description?,system_prompt?,status?}` | 200 AgentConfiguration |
| GET | `/tools` | 无 | 200 ToolConfiguration[] |
| GET | `/tools/{tool_id}` | 无 | 200 ToolConfiguration |
| POST | `/tools` | `{tool_key,name,description}` | 201 ToolConfiguration，disabled |
| PATCH | `/tools/{tool_id}` | `{name?,description?,status?}` | 200 ToolConfiguration |
| GET | `/agents/{agent_id}/tools` | 无 | 200 ToolConfiguration[]（含禁用的已分配对象） |
| PUT | `/agents/{agent_id}/tools/{tool_id}` | 无 body | 200 ToolConfiguration |
| DELETE | `/agents/{agent_id}/tools/{tool_id}` | 无 body | 204，无响应 body |

- AgentSummary：`id,workspace_id,name,description,status,created_by,created_at,updated_at`；
  description nullable，status 为 draft/active/disabled。AgentConfiguration 仅多
  `system_prompt`；完整配置不注入员工列表或传给未授权页面。
- ToolConfiguration：`id,workspace_id,tool_key,name,description,operation_type,risk_level,
  status,created_by,created_at,updated_at`；status 为 active/disabled，description 必填。
  operation_type 为 read_only/write_sensitive，risk_level 为 low/medium/high，
  由后端注册表校验/派生；本次注册能力实际只有 low/high。
- PATCH 至少一个合法字段，省略为保留；Agent description null 为清空，其他字段
  按既有 schema 不可 null。额外字段拒绝，字段限制见 4.2/4.3。
- 沿用 Bearer、Accept、JSON body Content-Type 与现有错误解析；PUT/DELETE 不发送
  body。可用窄的 void 请求 helper 或类型明确的 204 分支，保留所有 JSON 调用语义。
  现有 listAgents 默认路径不变，另加管理函数/显式参数，不能默认为 include_inactive。
- 无分页、注册目录、reverse assignment、配置 revision、直接执行接口或新数据表。
  不调用 `/agents/{agent_id}/route`、Approval 决策或评测 Run 来验证管理操作。

## 6. User Experience 与复用决策

入口“Agent 与工具”复用运营管理可见性。区域内分 Agent/工具两页签，桌面列表+
详情，移动端堆叠。Agent 详情含基础配置、独立状态操作和工具分配；工具页含配置
列表、创建、详情编辑与只读能力说明。空列表、正在读取、失败、权限不足、成功
和未保存草稿均有中文提示。名称长时换行，状态/风险使用文字，不只用颜色。

表单具备可见 label、字段错误、键盘提交、可取消确认框和合理焦点；结果 aria-live。
不在产品界面暴露内部迁移号、文件路径或 registry 实现细节。技术 key 可作为能力
识别的次级只读信息，不能代替中文标题。

建议修改边界：新增 `frontend/app/components/agent-tool-admin.tsx`、对应测试和
`frontend/utils/agent-tool-admin.ts`，必要时拆分窄的 Agent/Tool 表单；调整现有
api、shell、navigation、presentation/CSS。避免独立后台路由、通用表单引擎或新状态库。

复用现有 React/Next.js、API/error client、Vitest/Testing Library、Node API tests
及 pytest/PostgreSQL/fake-provider 测试。此功能是已有 API 接入，不新增实质 AI
基础设施；不需引入 SDK、Agent 框架、插件平台或第三方组件。说明常量一致性
测试只读取已注册公开契约，不能导出执行器、凭据或改变后端注册表。

## 7. Acceptance Criteria

| ID | 可验收结果 |
|---|---|
| AC-001 | 两 Workspace/四角色入口、完整配置和管理 API 与既有权限一致；角色撤销后无法继续管理 |
| AC-002 | Agent 全状态管理列表与员工 active-only 列表独立，列表不泄露 Prompt，详情按需读取 |
| AC-003 | Agent 创建 draft、编辑校验/描述清空、同名允许、无变化不写入、三状态转换及确认符合契约 |
| AC-004 | 三注册能力可分别创建为 disabled；已配置能力不重复创建，并发 409 可核对；Tool 说明必填 |
| AC-005 | Tool 仅编辑名称/说明/状态；类型、风险、参数与审批限制只读且与注册表一致，无执行入口 |
| AC-006 | 分配/解除覆盖活跃和非活跃对象；关系与生效条件分开显示；重复 PUT/DELETE 安全，204 正确处理 |
| AC-007 | 启停/分配确认说明能力及待审批影响，现有审批快照/漂移/非自批规则保持；不重写旧结果 |
| AC-008 | 同步阻止重复提交；Workspace/对象/角色切换、登出、卸载、A-B-A 乱序响应不混数据 |
| AC-009 | Agent 修改同步 shell active-only 列表，失效选择清除；成功后刷新失败不重发写入 |
| AC-010 | 各错误与结果未确认正确区分，401/403 清理、404/409 刷新、503 关闭受影响动作，文本安全渲染 |
| AC-011 | 桌面、移动、键盘主流程及既有页面回归通过；自动化不依赖联网 Provider |
| AC-012 | 无后端契约/权限/schema/migration/依赖扩张；必需验证无跳过，完成自审、commit、push、PR，人工合并后才交付 |

## 8. Test Requirements

### 8.1 API 与契约测试

- mock fetch 验证全部 11 个管理调用的路径、method、Bearer、body 白名单及响应。
  管理 list 包含 include_inactive=true，原 listAgents 默认调用保持 active-only。
- PATCH 只包含修改字段、描述清空/null 区别；PUT/DELETE 无 body；204 不调用 JSON
  parser，200/201 正常解析。现有登录、问答、上传、审批/评测 client 回归不受影响。
- 401/403/404/409/422/503、非法响应和网络失败传播安全错误，不回显输入。
- 三 key 的帮助描述、类型/风险、参数约束及审批限制与基线注册表/schema 对照。
  若添加 Python 契约检查，只读静态说明，不能扩大或注册能力。

### 8.2 组件与 shell 测试

- 覆盖 AC-001–010，包括未授权不请求详情、管理空/失败列表、全状态、Prompt
  内容/长度/安全文本、Tool 三份齐全、创建竞争、禁用仍可分配、无默认全量分配。
- 分配 GET 失败不按空集合展示；成功/失败不乐观伪造；PUT/DELETE 重复及 204。
- deferred promises 覆盖快速双击、回车、mutation 期间选择锁定、登出、卸载、
  token/角色切换、Workspace A-B-A、旧详情/列表/刷新响应和未保存草稿取消。
- 创建 draft 不进 Assistant，激活进入、改回 draft/disabled 清除无效选择，名称同步；
  后续读取失败不把写入成功改成失败或自动重发。伪成功/未知配置不能显示可执行。

### 8.3 后端专项回归（既有测试优先）

先运行 `test_agent_schemas.py`、`test_agent_authorization.py`、`test_tool_calling.py`
及 PostgreSQL `test_agent_api.py`、`test_tool_persistence.py`、
`test_approval_api.py`、`test_approval_execution_authorization.py`，检查四角色、
跨 Workspace、全状态、未知 key、风险不可写、唯一配置、幂等分配、禁用不可执行、
权限撤销、审批漂移和自批拒绝。缺少本功能必要断言时补窄的回归测试，不改策略。
以 fake providers 验证管理 API 不调用模型/adapter，不产生 Approval 或业务写入。

### 8.4 全量与浏览器验收

Phase B：专项测试后串行执行全部 PostgreSQL 集成测试与 pytest、Ruff，前端
`pnpm test`、`pnpm lint`、`pnpm build`，最后 `git diff --check` 和自审。
桌面/窄屏按两个 Workspace、四角色完成 Agent 创建→编辑→激活、Tool 创建→
启用→分配→解除→禁用，以及错误恢复、键盘和移动导航；回归 Assistant、知识管理、
审批、日志、评测、问题案例、成员管理。浏览器使用受控脱敏数据及 fake providers，
真实 Provider 调用需另行具体授权，不用未批准的敏感写入作为 UI 冒烟。

记录命令、环境、结果与截图至 `docs/features/020-agent-tool-admin-ui-verification.md`。
无必需测试跳过才可称实现验证通过；未合并只能称 PR-ready。
Phase A 文档验证不运行上述实现测试，不冒用 Feature 019 的历史测试结果。

## 9. Out of Scope

Feature 021 文档版本、022 Agent 配置版本/差异/激活历史、023 Run 比较、026 会话/
参数补全、027 我的申请、Workflow；直接 Tool 试运行、评测快捷运行、真实企业
连接、任意 HTTP/代码/插件注册、凭据管理、免审批/审批策略编辑、对象硬删除、
批量操作、配置审计新表、revision/幂等键、后台任务、新权限/架构/依赖。

## 10. 风险、实施边界与下一步

| 已知限制 | 处理及边界 |
|---|---|
| 配置可以即时影响员工候选能力及待审申请 | 独立确认与中文影响说明，继续由现有后端做执行授权/漂移检查 |
| 跨管理员后写覆盖、Agent 创建响应丢失可能重复 | 不承诺 revision/去重；未知结果先核对，不自动重试 |
| 分配解除后重加无历史 revision | 如实保留 Feature 013 的 Mock 限制，不宣称 UI 修复 |
| 本地能力说明可能漂移 | 三 key 窄常量+契约一致性验证；运行权威仍为后端 |
| 配置历史、逆向分配列表未提供 | 不伪造历史或“全部受影响 Agent”枚举；留给后续独立设计 |

本提案没有新增 migration、认证/RBAC、审批、安全执行或架构变更审批项。
操作现有 Agent/Tool 配置不等于修改授权策略；界面确认也不是新增审批政策。
用户已以“approve”批准 `6cc4278` 的实施范围，沿用同一分支与
[PR #49](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/49)。

PostgreSQL fixture 会清空重建专用测试库 schema，属于破坏性测试环境操作。
Phase B 执行前须依据 [AGENTS.md](../../AGENTS.md) 的
“STOP and request human approval before: database-destructive operations”
确认已具体授权使用 `enterprise_ai_workbench_test`，且没有其他工作树并发测试。
最初自动审批审查要求对具体测试库重建补充授权；用户在含目标、数据清除与验证
范围的问题中回复“刚刚打开了docker app，重试”，后续再次要求“继续”。已恢复并
核验现有 pgvector 容器，逐次确认 localhost:5432、测试库名、与运行库不同、无其他
测试会话，再持有验证锁串行执行。schema 重建与已有迁移验证仅发生在专用测试库；
不操作运行库，不部署，不自动合并。初始审批服务用量限制已解除，未绕过审批。
若 Phase B 需要高风险范围变更，先准备修订后的具体提案，再按 AGENTS 请求批准。

下一推荐任务：人工审阅并合并 PR #49；Feature 020 人工合并后，
才在新聊天从最新 main 制定下一 Feature。
