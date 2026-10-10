# Feature 019 - Knowledge Administration UI

Status: Phase B implemented and verified; PR #47 awaiting human merge
日期：2026-10-10（Asia/Shanghai）；Phase A 规格制定于 2026-10-09
Baseline: `origin/main` at `56b699ad2cd36d40df4e642404108fc7555c89ec`
Branch: `feat/knowledge-admin-ui`
Issue: [#46](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/46)
Milestone: 既有知识能力的管理界面补齐（后续 MVP 批次 A）
Risk: Normal；复用既有 API 和权限，重点回归文件上传、Provider 提示及工作空间隔离。

## 1. Goal

让当前工作空间的知识管理员和系统管理员通过中文界面完成知识库创建、编辑、
启停，以及文档上传、查看处理结果、显式索引/重新索引、启停。员工仍通过既有
知识问答和智能助手使用知识；管理操作完全由现有后端执行。

Phase A 在 `1c61fca` 制定规格、建立 Issue 并准备规格草稿 PR。
用户随后以“approve，实施”批准该规格，实施和验证结果记录于
`docs/features/019-knowledge-admin-ui-verification.md`。
实现通过验证仍须人工合并才完成交付。不启动 Feature 020 或其他后续功能。

## 2. 最新仓库规划与实现基线

已 fetch 远端并核验 HEAD 与 `origin/main` 同为上述提交，初始工作树干净。
Feature 018 已在 [PR #43](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/43)
合并；业务评测基线已在 [PR #45](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/45)
合并。Feature 017 的 [PR #41](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/41)
已合并，ROADMAP 中仍保留的待合并表述属于旧状态，不能据此重复实现。

Feature 019 的规划来源为尚未合并的
[PR #40](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/40)，
`origin/docs/mvp-delivery-plan` at `77acb1a` 的 `docs/MVP_DELIVERY_PLAN.md`。
用户本轮指定从 019 开始，采用其中 Knowledge Administration UI 的最小范围。
该规划不作为已合并基线，不在本分支复制整份计划、合并 PR #40 或修改其他
Feature 的交付记录。文档版本管理仍归规划 Feature 021。

已读取 AGENTS、PRODUCT_SPEC、ARCHITECTURE、DATABASE、ROADMAP，相关
Features 004、006–010，以及当前知识 API、服务、schemas、前端 shell、导航、
API client、测试和数据库 fixture。依赖 006–010 均已合并。

| 当前证据 | 对本功能的约束 |
|---|---|
| `backend/app/api/routes/knowledge_bases.py` 与 `schemas/knowledge_base.py` | 已有 list/detail/create/PATCH；名字不唯一；列表含禁用对象 |
| `api/routes/documents.py`、`schemas/document.py` 与 `services/documents.py` | 单文件同步解析；只返回元数据；201 可能为 failed；仅 ready/disabled 可互转 |
| `api/routes/retrieval.py`、`schemas/retrieval.py` 与 `services/retrieval.py` | 显式索引，原子替换 chunks；成功响应含本次 chunk_count/indexed_at；无索引状态 GET |
| `frontend/utils/api.ts::requestJson` | 当前为有 body 的请求设置 application/json，上传必须适配 FormData |
| `frontend/app/app/page.tsx` 与 `components/platform-navigation.tsx` | `/app` 共享 Workspace/角色和知识库列表；运营管理当前只对 Agent/System 管理员显示 |
| `backend/tests/integration/conftest.py` | PostgreSQL fixture 会重建专用测试库 public schema，必须明确授权并串行运行 |
| `backend/alembic/versions/0013_create_bad_cases.py` | 当前仓库 migration head 为 0013；不推断运行数据库 revision |

## 3. Scope

Phase B 限定为：

- 在 `/app` 的既有导航增加“知识管理”，仅当前 Workspace 的
  `knowledge_admin` / `system_admin` 可见并进入；使用 Feature 017 的蓝白样式和移动导航。
- 知识库列表、选择、详情及创建/编辑表单，包含名称、描述和启用/禁用操作。
- 选中知识库内的文档列表、元数据详情、单文件上传、手动刷新、索引/重新索引、
  启用/禁用及明确的失败恢复提示。
- 在前端增加已有 API 的类型和调用函数；适配 multipart 而不破坏 JSON 请求。
- 管理操作后刷新当前 Workspace 的共享知识库列表，供 Assistant 与知识问答使用。
- 增加前端 API、组件与 shell 回归测试，复用既有后端专项测试，完成浏览器验收。

不新增后端路由、响应字段、业务授权、持久化状态、migration、运行依赖或 AI 框架。
若实现需要改变这些边界，先修订具体规格并按 AGENTS 高风险规则请求批准。

## 4. Business Rules

### 4.1 角色、对象与会话

| 当前 Workspace 角色 | 知识管理入口/表单 | 现有知识元数据读取 API | 管理 API |
|---|---|---|---|
| employee | 不显示；不渲染管理区域 | 保留 | 后端拒绝 |
| knowledge_admin | 可用 | 保留 | 按既有规则允许 |
| agent_admin | 不显示；不渲染管理区域 | 保留 | 后端拒绝 |
| system_admin | 可用 | 保留 | 按既有规则允许 |

1. 导航为知识权限单独计算可见性，不复用 Agent 管理权限给知识管理员开放
   Execution Logs、Evaluation 或 Bad Cases，也不给 Agent 管理员开放知识管理。
2. 角色来自当前 Workspace，不能从用户在另一 Workspace 的身份推导。
   每个请求仍由后端验证当前 User、Workspace、Membership 和对象归属。
3. 只使用当前 Workspace 列表返回的知识库及其文档 ID 构造请求。
   401 清空内存会话；403 清除当前管理数据、阻止操作并显示权限不足。
   客户端缓存的管理员角色不能使已被撤权的后端请求通过。
4. token、File、草稿、管理数据和本次索引反馈只留内存，不写 localStorage、
   sessionStorage、URL 或前端日志。文件名、描述、错误作为普通文本渲染。

### 4.2 知识库管理

- 列表沿用 API 的 `name, id` 顺序，包含 active/disabled；无分页或新搜索 API。
  进入时可选择第一个知识库，包括禁用对象；空列表提供创建入口。
- 创建：trim 后 name 1–255 字符，description 可空、最多 5000 字符。
  默认 active，由后端设置 creator 等服务端字段。重复名称是合法情况。
- 编辑：初始值来自读取结果；只发送实际修改的 name/description，空描述发送 null；
  未修改不发送 PATCH。禁止发送 creator、workspace_id、时间戳等服务端字段。
  每次成功后采用服务端结果并刷新列表；后台无 revision/ETag，不宣称避免跨用户覆盖。
- 启停使用单独动作发送 `{status}`。禁用前确认，说明该知识库不再参与新的检索/问答；
  不删除知识库、文档或 chunks，不级联修改文档状态。启用不会自动上传或索引。
- 禁用知识库仍可查看/编辑元数据和文档、启停已有文档；上传和索引不可用。

### 4.3 上传与文档状态

1. 每次选择一个 `.pdf` / `.txt` / `.md` 文件，扩展名大小写不敏感；
   0 < size <= 10 * 1024 * 1024 bytes。TXT/Markdown 须为 UTF-8，PDF 须可提取文本。
   文件 input 的 accept 和大小校验只改善体验，后端校验最终有效。
2. 用 FormData 的 `file` 字段上传；禁止手动设置 multipart Content-Type/boundary。
   Bearer 和 Accept 仍由共享 client 加入。不得读出全文供浏览器处理或调用 Provider。
3. 上传和索引是两个显式动作。上传本身只在后端解析并保存提取文本；
   不上传后自动索引、不自动请求答案、不把文件发送到新增外部服务。
4. `201 + ready` 提示“上传并解析完成，可手动索引”；`201 + failed` 提示
   “文档已登记，解析失败”，显示服务端 processing_error 和恢复方法。
   二者均刷新列表，但 failed 不能显示成功可用提示。
5. 文档列表和详情显示文件名、类型、版本、处理状态、创建/更新时间和可用的
   processing_error；不显示 extracted_text、原始二进制或下载按钮。
   列表沿用 `file_name, version, id` 顺序，不以同名文件判断版本关系。

| status | 中文状态 | 可操作（管理角色） |
|---|---|---|
| uploaded | 已上传 | 详情、手动刷新 |
| processing | 解析中 | 详情、手动刷新；无百分比或进度任务 |
| ready | 解析完成 | 详情、禁用；父库 active 时索引/重新索引 |
| failed | 解析失败 | 详情、查看错误、提示修正后另行上传 |
| disabled | 已禁用 | 详情、启用（PATCH ready） |

仅 ready -> disabled / disabled -> ready 合法；不存在客户端“重解析 failed”动作。
原文件未保留，修正后需重新选文件上传，生成独立的新 Document、version=1，
保留失败记录。既有上传也没有去重保证，同名再次上传不会替换原文档。

### 4.4 索引与重新索引

- 只有 active 父库的 ready 文档提供“索引 / 重新索引”动作，二者调用同一无 body API。
  操作前用简短确认说明“文档文本将发送至已配置的 OpenAI 服务生成索引，可能产生费用；
  已有索引将在成功后替换”。确认是用户操作提示，不新增后端审批或授权策略。
- DocumentResponse 没有 chunk_count 或 index_status；ready 不等于已经索引。
  默认显示“当前索引状态未提供”，不能伪造“未索引”“已索引”或用文档更新时间推导。
  不通过隐式 search/answer 请求检测索引，不添加状态 GET 来扩张范围。
- 只有收到 200，才显示“本次索引成功”，附响应中的 chunk_count、indexed_at、
  embedding_model 和 embedding_dimensions。此反馈属于本次操作，刷新页面或
  重新进入管理区域后不当作持久索引状态；后续重试期间/失败后也不标为最新成功状态。
- indexing 是 UI pending 状态，不是文档新 status。失败不 PATCH 文档为 failed，
  不删除旧 chunks；后端保持既有完整索引（首次失败无部分索引）。
- 502/503 提示服务失败/未配置，用户可明确重试。无自动重试、后台任务、轮询或批量索引。
- 重新索引会替换 Chunk ID；本功能不承诺历史引用持久解析，不改写已有答案/评测。
  文档版本和旧引用追溯由 Feature 021 单独设计。

### 4.5 请求竞争、上下文切换与缓存

1. 同一管理区域一次只提交一个 mutation；pending 时禁用所有管理 mutation，
   包括双击、回车重复提交，不能依赖 React 下一次渲染才设置的 busy 状态。
   读取采用 request generation 或等效机制，较晚到达的旧响应不能覆盖新选择。
2. mutation 未结束时锁定 Workspace、产品区域和知识库选择，沿用 shell pending
   机制；退出登录仍可用。退出、token/Workspace 变更和卸载均使旧请求失效。
   浏览器取消/丢弃响应不等于服务端回滚，不宣称取消已提交的上传或索引。
3. 允许普通读取期间切换；切换 Workspace 立即清空选中知识库/文档、File、草稿、
   错误和索引反馈。A -> B -> A 的旧 A 响应也必须失效。切换知识库清空文档相关状态。
4. 知识库 mutation 成功后，刷新 shell 的当前 Workspace 共享列表，维持选中对象 ID；
   新建对象在管理区域选中。Assistant/问答下次进入必须取得更新后的名称和 active 状态，
   不能使用旧缓存仍启用提问。禁用文档不额外更新其父库状态。
5. mutation 成功、后续刷新失败时，显示“操作已完成，列表刷新失败”，提供 GET 刷新；
   不能把已完成的写入报告为失败或重新提交写入。404 清除失效对象选择；409 刷新
   对象/父库状态后重新计算动作，不自动再次提交。

### 4.6 错误与恢复

| 结果 | 界面及恢复 |
|---|---|
| 401 | 清会话并返回登录；丢弃文件、草稿和受保护数据 |
| 403 | 显示权限不足并阻止管理；不展示旧详情、不自动重试 |
| 404 | 对象不存在/不可用；清除相关选择并允许刷新父列表 |
| 409 | 库已禁用、文档不满足动作状态或状态竞争；刷新后由用户选择操作 |
| 413 | 文件超过 10 MiB；另选较小文件 |
| 415 | 格式不支持；另选 PDF/TXT/Markdown |
| 422 | 请求/文件不合法；显示安全提示并保留当前上下文中的可修正输入 |
| 502 | 索引服务失败；不改变文档状态，允许用户手动重试 |
| 503 | 索引服务未配置；提示联系管理员，不展示密钥输入框 |
| 网络中断/其他服务错误 | 安全兜底消息；mutation 提示结果未确认，先刷新再决定是否重试 |
| 201 failed | 已创建的解析失败记录，按 4.3 恢复；不按 HTTP 成功判断文档可用 |

网络中断不能证明上传未创建记录，刷新核对后再次上传仍可能重复；不得隐藏此限制。
错误使用现有 ApiError 与 displayMessage，不输出 raw validation input、stack、Provider
body 或文件内容。只有在当前仍有权限且上下文未变时保留修正用的草稿/File。

## 5. API / Data Contract

以下全部复用既有接口，统一前缀 `/api/workspaces/{workspace_id}`。
无 DELETE，无新增分页、过滤、幂等 key、index_status 或 revision 字段。

| Method | 后缀 | 请求 | 成功响应 |
|---|---|---|---|
| GET | `/knowledge-bases` | 无 | 200 KnowledgeBase[] |
| GET | `/knowledge-bases/{kb_id}` | 无 | 200 KnowledgeBase |
| POST | `/knowledge-bases` | `{name, description?}` | 201 KnowledgeBase |
| PATCH | `/knowledge-bases/{kb_id}` | `{name?, description?, status?}`，至少一个字段 | 200 KnowledgeBase |
| GET | `/knowledge-bases/{kb_id}/documents` | 无 | 200 Document[] |
| GET | `/knowledge-bases/{kb_id}/documents/{document_id}` | 无 | 200 Document |
| POST | `/knowledge-bases/{kb_id}/documents` | multipart/form-data，单个 `file` | 201 Document（ready 或 failed） |
| PATCH | `/knowledge-bases/{kb_id}/documents/{document_id}` | `{status: "ready" | "disabled"}` | 200 Document |
| POST | `/knowledge-bases/{kb_id}/documents/{document_id}/index` | 无 body | 200 DocumentIndexResponse |

- KnowledgeBase：现有 `id, workspace_id, name, description, status, created_by,
  created_at, updated_at`；status 为 active/disabled；description nullable。
  PATCH 省略保留，description null 清空，name/status 不可 null，额外字段被拒绝。
- Document：`id, workspace_id, knowledge_base_id, file_name, file_type, status,
  version, processing_error, created_by, created_at, updated_at`；file_type 为 pdf/txt/md，
  status 见 4.3；processing_error nullable；无全文、文件大小或索引属性。
- DocumentIndexResponse：`document_id, chunk_count, embedding_model,
  embedding_dimensions, indexed_at`。服务器当前使用 text-embedding-3-small / 1536。
  UI 展示返回值，不新增 Provider 配置或浏览器模型调用。
- API client 保留 Bearer、Accept、ApiError 及既有 JSON 路径；遇到 FormData 必须让
  浏览器设置 Content-Type。JSON body 仍设置 application/json，索引无 body。
  frontend 中的 TypeScript 类型不能被描述为新增后端验证。

数据模型、持久化契约与错误码以当前 backend schemas/services 为准。
安全数据流仍为浏览器 -> FastAPI -> PostgreSQL；显式索引时 FastAPI -> 既有
OpenAI embedding provider。无新数据接收方，无新增日志正文或索引审计表。

## 6. User Experience 与复用决策

在既有 `/app` 管理导航放“知识管理”，保持知识问答独立。桌面为知识库列表与
选中库的管理/文档区域，移动端堆叠，长文件名可换行；空列表、加载、权限不足、
失败与成功状态均有清晰中文文案。对象 ID 作为内部引用，不作为主要显示标题。
表单使用可见 label、字段错误、键盘提交和合适的焦点处理；状态通过 aria-live
通知，颜色之外有文字。确认框须可用键盘取消，不能只依赖图标表达启停。

建议文件边界：`frontend/app/components/knowledge-admin.tsx`，对应测试，
`frontend/utils/knowledge-admin.ts`（或现有 api.ts 中的窄函数），以及现有 shell、
导航、presentation 和 CSS 的必要改动。不扩张为独立后台路由或新设计系统。
共享 KnowledgeBase 类型与列表避免重复实现，保留现有其他 API 调用语义。

复用 React/Next.js、原生 FormData、现有 API/error client、Vitest/Testing Library
和现有 PostgreSQL/fake-provider 测试。功能是已交付 API 的界面接入，无实质新增
AI 基础设施；现有依赖足够，不需引入上传组件库、状态库、文档解析库或外部服务。

## 7. Acceptance Criteria

| ID | 可验收结果 |
|---|---|
| AC-001 | 两个 Workspace、四角色的入口与后端既有权限一致；知识管理员不获运营权限，Agent 管理员不获知识管理权限 |
| AC-002 | 创建/编辑知识库、同名允许、描述清空、启停确认、空列表与禁用库可读管理均按契约工作 |
| AC-003 | 正确提交单文件 multipart；三种有效文件可解析；上传不自动索引，201 failed 明确可见 |
| AC-004 | 文档元数据和全部状态正确；仅合法启停，禁用父库仍允许文档启停；无全文、下载或版本替换 |
| AC-005 | active 库/ready 文档可显式索引与重索引，有 Provider 提示和本次结果；ready 不标成已索引，刷新不伪造持久结果 |
| AC-006 | 解析失败指向新上传；索引失败提供手动重试、旧 chunks 保留，不改文档为 failed，无自动重试 |
| AC-007 | 重复提交被阻止；Workspace/知识库切换、登出、卸载及乱序响应不能混入其他上下文数据 |
| AC-008 | 管理后共享知识库列表更新，Assistant/问答使用最新 active 状态；刷新失败不重复写入 |
| AC-009 | 各错误码及网络结果未确认正确区分；401/403 清理受保护状态，404/409 可刷新恢复；文本按字面渲染 |
| AC-010 | 桌面与移动主流程、可访问性和既有页面回归通过，自动化测试无需联网 Provider |
| AC-011 | 无后端契约/权限/模型/migration/依赖变更；专项及全部必需验证通过，有 diff 自审、commit、push、PR，等待人工合并 |

## 8. Test Requirements

### 8.1 前端 API 测试（mock fetch）

- 每个调用的 method、Workspace/KB/Document 路径、Bearer、请求字段和响应类型。
- FormData `file` 为选定 File，不设置 Content-Type，浏览器可生成 boundary；
  现有 login、知识问答、评测等 JSON 请求仍为 application/json；索引 body 缺省。
- 201 failed 不作为可用成功，401/403/404/409/413/415/422/502/503 与网络异常传播。

### 8.2 组件及 shell 测试（fake API）

- 按 AC-001–009 覆盖：角色矩阵、两 Workspace 不同角色、空/禁用列表、创建后选择、
  trim/越界校验、清空描述、启停确认、三种上传、超限/空/不支持文件、failed 恢复、
  全部文档状态、索引提示/确认/返回值和状态未知、错误分支及手动刷新/重试。
- 延迟 Promise 验证双击与回车重复、pending 锁定上下文、读响应乱序、A -> B -> A、
  切换 KB、登出/卸载后完成、读取失败和 mutation 成功但刷新失败；不能重复 POST。
- 验证共享列表让 Assistant/问答取得新库/改名/禁用信息；已有导航权限保持一致。
- HTML/脚本形状的名称、描述、文件名与错误按纯文本显示；键盘、label 和状态通知。
  required tests 不通过跳过或仅测 helper 替代用户交互。

### 8.3 既有后端 PostgreSQL 专项回归

复用 `backend/tests/integration/test_knowledge_base_api.py`、`test_document_api.py`、
`test_retrieval_api.py`、`test_answer_api.py`，必要时补实际缺口，检查角色拒绝、
禁用 Workspace/Membership、跨 Workspace/错误父库、文档状态、上传结果、索引失败
保留旧 chunks 和禁用知识不可检索。无需编写重复后端实现的新测试或改业务代码。
仅使用 deterministic fake embedding/generation，不能联网 OpenAI 或触碰运行数据。

### 8.4 Phase B 验证顺序与证据

1. Feature 019 API/组件专项；上述后端专项（专用 PostgreSQL）。
2. 全量 pytest（含 PostgreSQL）、Ruff；全量前端测试、`pnpm lint`、`pnpm build`。
3. 浏览器验收：知识管理员创建库 -> 上传合成文档 -> 显式索引（fake provider）->
   员工在既有问答查看引用 -> 管理员禁用文档/库 -> 新检索不可见 -> 重新启用。
   补系统管理员、Agent 管理员拒绝、解析/索引失败恢复及窄屏操作。
   优先使用已有浏览器工具；如需新增测试依赖先解释并修订范围。
4. `git diff --check`、契约/权限与范围自审，记录实际命令、通过数、跳过数和环境。
   任一必需验证无法运行，不报告实现 PR-ready。

历史 Phase A 只进行了文档链接、契约一致性、格式与 diff 自审，没有运行应用测试
或数据库操作。随后批准的 Phase B 已完成以上必需验证，实际结果见验证记录。
PostgreSQL fixture 会 DROP/CREATE 专用测试库 schema；本次批准包含规格内该项
验证，执行前已核对 `enterprise_ai_workbench_test`、运行库不同及无其他测试会话。
不可把运行库或其他工作树的数据库用于测试。

## 9. Out of Scope

- Feature 020 Agent/Tool 管理、021 文档版本/替换、后续评测比较、会话与 Workflow。
- 新 API、索引状态/统计/历史 API、revision/ETag、上传去重、并发后端设计重写。
- 自动索引、自动重试、取消服务端任务、后台进度、轮询、批量上传/索引或删除。
- 原始文件保留/下载、全文预览/编辑、OCR、新格式、DLP 或扫描服务。
- 新 RBAC、细粒度文档权限、认证、租户隔离、Provider/模型或检索策略改变。
- 新日志记录器、审计表、migration、依赖、架构、部署、运行数据库升级、live API 冒烟。
- 修改历史评测基线、迁移 0001–0013，自动合并 main。

## 10. 风险、实施边界与交付

主要限制：现有 API 不返回持久索引状态；重新上传不去重/不替换；网络中断时
mutation 可能已在后端完成；跨用户编辑没有 revision 冲突保护；成功重索引替换
Chunk ID。界面必须如实显示这些边界，不能用乐观状态或新增数据模型掩盖。

按 AGENTS，此方案属普通 UI 接入，不包含必须预先批准的迁移、认证、RBAC、
安全策略或架构变更。已有授权检查的使用与回归不等于新增授权策略。
初始停止于 Phase A 是用户“先制定规格”的范围要求。
后续“approve，实施”授权了 `1c61fca` 范围的实现和规格中专用测试库验证。
若出现高风险变更，先提交具体可审阅方案，再按 AGENTS 申请批准。
独立审查对当前 normal-risk 范围可选；人工 merge 始终必需。

Phase B 继续使用同一专用分支和
[PR #47](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/47)，
交付本规格、实现、67 项前端专项和验证记录；没有修改后端或迁移。
完成 diff 自审、提交推送并更新 PR 后，AI 停于 PR-ready。
下一推荐任务是人工审阅/合并 Feature 019；合并后在新聊天启动规划 Feature 020，
重新核验当时的最新 main。本聊天不继续下一功能。
