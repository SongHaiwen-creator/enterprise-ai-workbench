# Feature 021 - Document Version Management

Status: Phase A proposal；等待明确批准，尚未实施
日期：2026-10-11（Asia/Shanghai）
Baseline: `origin/main` at `2508d67f0551a3112c80eb78438c9f7b166e0b5b`
Branch: `feat/document-version-management`
Issue: [#50](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/50)
Milestone: 后续 MVP 批次 B，知识版本与引用追溯
Risk: High；新增迁移、检索隔离、索引冻结、并发切换与历史保留。

## 1. Goal

让知识管理员和系统管理员维护同一逻辑文档的多个不可变内容版本，上传、解析、
索引替代版本后显式激活。准备失败时旧版本继续可用；激活成功后的新检索只使用
当前有效版本；旧引用始终指向原版本和原 Chunk，不被静默改指到新内容。

本轮仅交付 Phase A：规格、Issue、专用分支、文档验证、commit、push 和草稿 PR。
不编写 migration 或应用实现，不操作数据库，不运行联网 Provider，不自动合并。

## 2. 最新规划与基线证据

已 fetch 并核验 HEAD / `origin/main` 为上述提交，开始时工作树干净。
Feature 019 的 [PR #47](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/47)
和 Feature 020 的 [PR #49](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/49)
均已人工合并；ROADMAP 的 020 待合并表述需要据此更新。
Features 004、006–010、016、017、019 已在 main，021 没有现成规格或开放 Issue。

Feature 021 来源为尚未合并的
[规划 PR #40](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/40)，
`origin/docs/mvp-delivery-plan` at `77acb1a17d09f87f13dc8b15d7028f2ce815ff76`
中的 `docs/MVP_DELIVERY_PLAN.md`。采用用户本轮指定的 Document Version Management
最小范围，不复制或合并整份规划，不批准后续 022/023/026–029。

已读取 AGENTS、PRODUCT_SPEC、ARCHITECTURE、DATABASE、ROADMAP 及相关知识、
授权、评测和管理 UI 规格，并核对当前 models、schemas、routes、services 与测试 fixture。

| 已有实现 | 对本功能的约束 |
|---|---|
| `documents` / Feature 007 | Document 是一次上传；独立 UUID；version 默认 1；保留提取文本、不保留原文件 |
| `services/retrieval.py` / Feature 008 | 目前按 ready Document 检索；重新索引删除并重建 Chunk，需要明确修改这一行为 |
| `services/answers.py` / Feature 009 | 引用已有 document_id、document_version、chunk_id、chunk_index、file_name、excerpt；不持久化答案 |
| Feature 010 / Assistant | 引用摘录来自响应；不能把本功能当作会话历史交付 |
| `services/evaluation_snapshot.py` / Feature 016 | 当前捕获所有 ready Document / Chunk；必须和运行时有效版本规则同步 |
| Feature 019 | 管理 UI 已有；本次在其区域内增加版本列表与动作，不另建后台 |
| Alembic | 仓库 head 为 0013；不代表任何运行数据库已升级 |
| 集成 fixture | 清空重建专用测试库 public schema，须具体授权并与其他工作树串行执行 |

## 3. Scope

Phase B 拟实施：

- 新增逻辑文档 `document_families`；现有 `documents` 继续保存具体版本。
- 保留现有上传新文档、Document list/detail/status/index 路径与已有响应字段。
- 新增 Family 列表/详情、版本列表、上传替代版本、显式激活五个接口。
- 解析后冻结内容；首次完整索引成功后冻结 Chunk，持久化可读取的索引元数据。
- 当前版本指针原子切换、revision 冲突检测、按 Family 加锁分配版本号。
- 同步 search、知识问答、Agent 知识路径和 Evaluation 新 Run 的有效语料筛选。
- 扩展知识管理界面与引用版本显示；保留旧版本元数据和已有摘录的追溯能力。
- 新增 migration 0014（实施前重新核对 head）、后端/前端/浏览器验收与独立复审。

不新增运行依赖、后台任务、对象存储、AI 编排框架或评测指标。

## 4. Business Rules

### BR-001 - 身份、归属与权限

逻辑文档固定属于一个 Workspace 和一个 Knowledge Base，不能迁移归属。
版本固定属于一个 Family。所有查询按 workspace_id、knowledge_base_id 和目标 ID
限定；嵌套版本还须核对 family_id。错误父对象或跨 Workspace ID 返回 404。

| 操作 | employee / agent_admin | knowledge_admin / system_admin |
|---|---|---|
| Family、版本及历史 Document 元数据读取 | 允许 | 允许 |
| 上传新文档 / 替代版本、索引、启停、激活 | 拒绝 | 允许 |
| active 知识库当前有效版本检索 / 问答 | 沿用既有规则 | 沿用既有规则 |

复用当前 User、Workspace、Membership 和知识管理依赖，不增加角色、读正文权限、
审批策略或管理员代执行。disabled Workspace、非活跃 Membership 和失效 User 继续拒绝。
禁用 Knowledge Base 仍可读取元数据和启停已有版本，不能上传、索引或激活。

### BR-002 - 稳定身份与版本号

- `family_id` 表示逻辑文档；`document_id` 永远表示一次上传的具体版本。
- 新建文档仍用原 POST：创建新 Family 和 version=1；同名上传是另一个 Family。
- 替代版本必须通过明确的 Family 路径上传；文件名和格式允许改变，不推断同名关系。
- Family 行锁下取 next_version，再递增；唯一约束防止重复。已登记的失败/处理中版本
  占用编号，编号不复用；顺序表示登记先后，不保证完成先后。文件重复内容不自动去重。
- family_id、version、原文件名/类型、creator、创建时间不可编辑。禁止覆盖旧版本全文。
- Family 名称取首个文件名作为不可变 display_name；不提供重命名或合并/拆分文档。

### BR-003 - 初始上传与替代上传

沿用 PDF / UTF-8 TXT / UTF-8 Markdown、10 MiB、文件名规范化、同步提取和安全错误。
上传不调用 Provider，不自动索引。原文件仍不保存、不提供下载。

初始 version=1 成功 ready 时设为 current_document_id，即使尚未索引；这是原上传
使用路径的兼容规则，未索引时没有检索结果。初始解析失败 current=null。
替代上传永远不自动改变 current，即使当前没有版本；必须完成索引后显式激活。

上传先在短事务登记版本，再在锁外解析，最后短事务写入 ready / failed：
uploaded -> processing -> ready | failed。解析结果与 content_sha256 一次提交；
之后文本和哈希冻结。failed 无文本/哈希；修正后再次上传，保留失败版本。
校验在登记前失败不创建 Family/版本；登记后的解析失败返回 201 + failed。

进程中断可能留下 uploaded/processing；它们不能索引或激活，不代表可用。
本功能不恢复/重解析这些记录、不设置自动超时状态；管理员可登记下一个版本。
最终保存前重新检查当前身份、Membership、Workspace 和 KB；若已无权或父库禁用，
不发布 ready 内容，返回安全的 403/409，登记记录可能仍待处理。不要声称请求整体回滚。

### BR-004 - 索引冻结与明确的兼容变化

解析 ready 和索引成功是独立条件。Document 元数据新增持久索引结果；没有结果
表示未成功索引，不从 status 或 updated_at 猜测。

1. 只有 active KB 下 ready 且非空文本的版本可索引；非当前版本也可准备索引。
2. 复用当前 splitter、EmbeddingProvider、OpenAI SDK、模型和 1536 维契约。
   在锁外生成/验证所有向量；没有完整成功就不写入部分 Chunk。
3. 写入前重新鉴权和核对 KB、版本状态、内容哈希。锁住 KB、Family、Document，
   一次提交全部 Chunk 和 indexed_at/model/dimensions/count。事务失败均不留下部分结果。
4. 同版本只有一个完整 Chunk 集合。一旦成功，Chunk ID、正文、顺序、模型、向量和
   首次 indexed_at 不再修改或删除。两个首次索引竞争时，后来者返回已提交的同配置结果；
   即使生成了额外向量也不得覆盖胜者。未经提交的向量不留历史。
5. 相同索引配置重复调用原 `/index` 返回 200 和已有结果，不调用 Provider、不重建 Chunk。
   不兼容配置返回 409；模型/维数迁移仍不属于本功能。
6. 内容、分块或索引要更新时上传新的版本（允许相同文件内容），索引后激活。
   修改 Feature 019 的“重新索引”说明/测试，不能继续承诺原地替换现有 Chunk。

索引失败仅返回安全错误，索引字段仍为空；不把解析 ready 改成 failed。
不持久化 Provider 原文、不增加 index_failed/indexing 状态或后台重试。

### BR-005 - 显式激活与并发

激活请求 `{document_id, expected_revision}`；expected_revision 为严格正整数，
必须来自最新 Family 读取。目标须是本 Family 的 ready、完整索引且配置兼容版本。
可以选择曾使用过的历史版本，作为显式回退；不复制内容、不生成新的版本号。

短事务按 KB -> Family -> Document（多个版本按 UUID 排序）加锁：重新鉴权、核对
active KB、revision、目标资格，再改变唯一 current_document_id 和递增 revision。
不修改其他版本 status、不删旧 Chunk。比较失败或写入失败时当前指针不变。
同 revision 的竞争激活仅一个能成功，另一个 409，不能最后写入静默覆盖。

先检查 expected_revision；匹配且目标已是 current 时返回 200，revision 不变。
过期 revision 即使目标恰好已是 current 也返回 409。未知结果先 GET 核对，再由人决定。
没有自动重试、自动择优、定时发布、latest(version) 隐式激活或失败自动回退。

Family revision 是版本管理状态的乐观并发标记：登记版本、解析完成、首次索引完成、
版本状态变化、current 指针变化每次提交递增一次；纯读取/索引复用不递增。
它不表示内容版本号，也不是配置质量。Family updated_at 随真实变化更新。
行锁等待最多 5 秒，锁超时/死锁使用安全 409，rollback 后不发布部分写入。
所有涉及版本的写入使用一致锁序；修改当前 KB 状态的服务也使用 KB 行锁，
使禁库与激活/索引最终提交有明确先后。Provider/解析期间不持有这些锁。

### BR-006 - 启停与有效版本

保留原 PATCH `{status: ready | disabled}` 和 ready <-> disabled 转换。
禁用 current 保留指针且立即排除后续检索；不自动选择旧版本。重新启用 current
恢复其原有完整索引的参与资格；重新启用历史版本不会激活它。
failed/uploaded/processing 不能启停；重复相同 status 仍按原契约返回 409。

检索候选须同时满足：当前请求有权访问 active Workspace / KB，Chunk 与 Document /
Family 属于 route Workspace / KB，Document.id = Family.current_document_id，
Document.status=ready，完整索引元数据存在且模型兼容。先过滤，再距离排序和 limit；
不能检索全部版本后用前端过滤。排名与限额沿用 Feature 008，不改变准确率定义。

检索 SQL 在一次语句快照内读取完整指针/资格，KB active 也进入 SQL 条件。
激活事务提交后开始的检索使用新版本；已在提交前捕获证据的请求可以完成原答案，
引用原版本。不持锁跨越生成 API，不承诺撤回已发送模型的证据或修改已返回答案。

### BR-007 - 历史引用与评测

引用保持 document_id 指向具体版本，document_version、file_name、chunk_id、
chunk_index、excerpt 原义不变；新 search / citation 响应附加 family_id。
版本切换/禁用不重写先前答案、Evaluation Run/Run Case/Bad Case 或 Execution Log。
不按 Family.current 解析旧 document_id，旧 Chunk 保留并能内部核对摘录。

引用卡显示版本号；已返回的历史摘录仍按文本展示，支持读原 Document 元数据并说明
“当前版本 / 历史版本 / 已禁用”。元数据 GET 不能包含全文或新的历史内容读取接口。
本功能不持久化问答、不保证刷新后找回答案；追溯以调用方已保存的引用为前提。
迁移前已被重新索引删除的 Chunk 无法恢复，旧引用只保留其已返回摘录/版本信息，
不能声称迁移补回原 Chunk。新保证从迁移时保留的集合和此后首次索引开始。

新 Evaluation Run 语料清单只捕获上述有效版本与 Chunk，加入 family_id、版本号、
content_sha256、已冻结索引标识（由文档/Chunk 集合可确定），保留既有限额。
语料捕获需在同一数据库快照内完成，不能把切换前 Document 与切换后 Chunk 混合。
保留 current-config drift 检查：准备/执行过程中激活、禁用、首次索引等改变有效语料时，
受影响 Run 按 Feature 016 的现有漂移语义失败，不继续偷偷使用新版或重写旧终态结果。
新增快照格式使用新的 snapshot_version；保留旧快照读取，不能原地修改旧 JSON / SHA。
不改变 scorer、指标分母、Tool dry run 或运行限额，不实现 Feature 023 比较功能。

### BR-008 - 保密与外发

历史提取文本、Chunk 和向量留在原 PostgreSQL/pgvector，按既有数据库/备份控制；
保留会增加存储量，禁用不等于删除。内容冻结是应用层约束，不宣称 DBA 防篡改。
没有自动 DLP、保留期限、清除 API、原文件归档或内容导出。

仅显式索引将文本发往已有 OpenAI embeddings；查询和生成仍遵守 Features 008/009
的外发契约，不增加 Family ID、文件名、身份或哈希到模型输入。管理上传/激活/启停/
历史元数据读取不调用 Provider。测试使用 synthetic/redacted 数据与 fake providers。
错误不回显 file body、全文、raw validation input、SQL、Provider body 或秘密。
新/触及的版本管理路由采用固定安全 validation/persistence 错误边界。
沿用 Feature 014 日志白名单，不把文档正文、历史摘录或文件名写入执行日志。

## 5. Database / Migration Contract（H1）

计划增加 `0014`，down_revision=`0013`。不重写已提交迁移，保持单一 head。
只创建 document_families，并扩展 documents 的关联/索引元数据及必要约束；
不新增版本内容表、不重建 chunks、不修改历史评测表内容。

### 5.1 document_families

| 字段 | 类型与约束 |
|---|---|
| id | UUID，主键，数据库生成 |
| workspace_id / knowledge_base_id | UUID nonnull；父 KB composite FK，RESTRICT |
| display_name | VARCHAR(255)，非空规范化首文件名，不可变 |
| current_document_id | UUID nullable；仅指向本 Family / Workspace / KB 的具体版本 |
| next_version | INTEGER nonnull，>0，初始 2（原上传已登记 v1） |
| revision | INTEGER nonnull，>0，初始 1 |
| legacy_backfill | BOOLEAN nonnull，默认 false；仅迁移回填为 true，内部降级安全标记，不接受 API 写入 |
| created_by | UUID nonnull，FK users，沿用 Document creator 身份契约，RESTRICT |
| created_at / updated_at | TIMESTAMPTZ nonnull；数据库默认，真实修改更新 updated_at |

唯一键 `(id,workspace_id,knowledge_base_id)`；列表索引
`(workspace_id,knowledge_base_id,display_name,id)`，creator 索引。
current FK：`(current_document_id,id,workspace_id,knowledge_base_id)` ->
documents `(id,family_id,workspace_id,knowledge_base_id)`，RESTRICT；允许 null 指针。
先创建无 current 的 Family，再插入 Document，再更新指针，处理循环建表顺序。
DB FK 保证成员归属；ready/完整索引/active KB 的可激活条件仍由服务在锁下验证。

### 5.2 documents 新增字段

| 字段 | 类型与约束 |
|---|---|
| family_id | UUID nonnull；composite FK `(family_id,workspace_id,knowledge_base_id)` -> Family，RESTRICT |
| content_sha256 | CHAR(64) nullable；规范化提取文本 UTF-8 bytes 的 SHA-256，非原文件哈希 |
| indexed_at | TIMESTAMPTZ nullable；首次完整集合中最大 Chunk.created_at |
| indexed_model | VARCHAR(100) nullable；本功能支持 text-embedding-3-small |
| indexed_dimensions | INTEGER nullable；本功能支持 1536 |
| indexed_chunk_count | INTEGER nullable；成功后 >0 |

唯一 `(family_id,version)`、上文 current FK 的四列唯一键与
`(workspace_id,knowledge_base_id,family_id,version,id)` 列表索引。
保留原字段、UUID、FK 和正 version / status / file_type 检查；版本内容完成后不更新。
新增 CHECK：索引四字段全部 NULL 或全部非 NULL，model 非空、dimensions=1536、
count>0、content_sha256 非 NULL；哈希为小写 64 位十六进制。ready/disabled 必须有
非空文本及哈希；failed 无文本/哈希/索引。uploaded/processing 不得有完整索引。
CHECK 明确处理 SQL NULL，不能借三值逻辑绕过。Chunk 数量与一致性在事务内验证，
不假称 CHECK 能跨表校验数量。已有 Chunk composite FK 保留。

### 5.3 回填与降级

在单一迁移事务中，一条原 Document 建一条 Family；可使用原 Document UUID 作为
新表的 Family UUID，不更改 Document ID。同名也不自动归并。保留 version（即便
非 1）、status、全文、error、creator、时间和所有 Chunk；next_version=原 version+1。
ready/disabled 的 current 指向原 Document，其他 current=null；revision=1，legacy_backfill=true。
从现有规范化文本计算内容哈希，从完整现有 Chunk 回填索引统计并冻结该集合。
无 Chunk 则索引四字段全空。历史 processing_error 不复制 Provider 详情。

迁移前校验父归属、状态/文本一致性、分块编号连续性、模型/维数、版本号溢出及
现有约束；不合法则中止/rollback，不静默删除、改正文或补向量。迁移不调用 Provider。
校验所有旧表 row counts、Document/Chunk 内容和 ID 保留，旧迁移字节不变。

在仅迁移回填、没有新版本管理写入时，可 downgrade：移除新增约束/列/Family，
旧行、Chunk、status、version 原样保留。出现任何 legacy_backfill=false 的新 Family，
或回填 Family revision>1 时，downgrade 必须安全拒绝；涵盖初始上传登记后尚未完成
解析的情况，不能降级后让多个历史 ready 版本同时进入旧检索。
只测试这种拒绝，不做强制降级。
真正运行库升级、备份恢复和回滚运维须独立授权；0014 文件与测试验证不代表部署。

## 6. API / Data Contract（H4）

统一前缀 `B=/api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}`。
所有接口 Bearer 认证；UUID、严格正 revision 和未知字段校验；正文不接受服务器字段。

| Method / 路径 | 请求 | 成功 |
|---|---|---|
| GET `B/document-families`（新） | 无 | 200 Family[]，display_name/id 升序 |
| GET `B/document-families/{family_id}`（新） | 无 | 200 Family |
| GET `B/document-families/{family_id}/versions`（新） | 无 | 200 Document[]，version 降序，再 id |
| POST `B/document-families/{family_id}/versions`（新） | multipart 单个 file | 201 Document，ready 或 failed；不自动激活 |
| POST `B/document-families/{family_id}/activate`（新） | `{document_id,expected_revision}` | 200 Family；指针/revision 原子结果 |
| POST `B/documents`（保留） | multipart 单个 file | 201 Document；登记新 Family 的首版本 |
| GET `B/documents`、`B/documents/{document_id}`（保留） | 无 | 200 具体版本元数据；旧 list 仍返回所有版本，原排序不变 |
| PATCH `B/documents/{document_id}`（保留） | `{status:ready\|disabled}` | 200 Document；禁止编辑版本内容 |
| POST `B/documents/{document_id}/index`（保留） | 无 body | 200 原 DocumentIndexResponse；成功后重复复用 |

Family：`id,workspace_id,knowledge_base_id,display_name,current_document_id,
revision,created_by,created_at,updated_at`，current_document_id nullable。
next_version 是服务器内部字段，不返回；不新增 Family PATCH / DELETE / 分页。

Document 保留原字段并新增：`family_id,is_current,content_sha256,indexing`。
is_current 来自当前数据库指针，非持久副本；indexing 为 null 或
`{chunk_count,embedding_model,embedding_dimensions,indexed_at}`，均以冻结结果为准。
任何列表/详情都不返回 extracted_text、向量、原文件、完整 Chunk 正文。
is_current=true 且 disabled / indexing=null 仍不表示可检索。

search result / GroundedCitation 增加 `family_id`；原 document_id、version 和 excerpt
字段不变。同步 Python schemas、Agent 的知识响应和 TypeScript 类型；旧历史快照
无 family_id 时可读取，不把未知字段缺失当作历史数据损坏。

### 错误与结果未知

| HTTP | 处理 |
|---|---|
| 401 / 403 | 沿用身份/Workspace/知识管理员拒绝；UI 清空受保护状态 |
| 404 | 安全的 Family / Document / KB not found，涵盖错父对象/跨 Workspace |
| 409 | revision 过期、disabled KB、目标未 ready/未索引/模型不兼容、非法启停或锁竞争；刷新核对 |
| 413 / 415 / 422 | 沿用超大小/格式/文件校验；新请求与触及路由的 schema 校验使用固定安全 detail |
| 502 / 503 | 既有索引 Provider 失败/配置缺失；未提交索引，不改变当前版本 |
| 201 + failed | 登记解析失败版本成功，不能提示激活或可用；修正后上传下一个版本 |
| 网络中断 / 5xx / 响应解析失败 | 写入结果未确认，先 GET 核对；不能证明未创建版本，禁止自动重新上传/激活 |

409 detail 使用固定原因短句，例如 `Document family revision conflict`、
`Document version is not eligible for activation`、`Document version operation conflict`；
不带 UUID、字段输入、SQL 或 Provider body。新路由固定 422 `Invalid document version request`；
触及旧路由保留已列举文件错误，去掉通用 validation input 回显，不全局重写其他 API。
无通用幂等键或上传去重保证；索引重复安全不等于上传重复安全。

## 7. User Experience

复用 Feature 019 的知识管理区域。KB 内按 Family 展示逻辑文档，详情列出版本、
文件名、解析状态、持久索引结果、当前/历史标识；failed/处理中版本也可看元数据。
“上传新文档”和“上传替代版本”明确分开，不用文件名推断目标。

替代版本流程：选择文件 -> 上传并解析 -> 显式索引 -> 显式激活。
每一步独立成功/失败反馈；失败时说明当前版本未切换，旧版是否仍可检索按服务器状态显示。
激活确认显示原/目标版本与文件名、影响新的检索，可选择已索引 ready 历史版本回退。
无索引按钮的成功版本显示冻结索引详情；提供“上传新版本以更新索引”的说明。
初始文档 ready 未索引时提示索引，不能用“当前版本”标识替代可用性。

启停当前版本提示不自动回退；父库 disabled 时禁用上传/索引/激活动作。
409 不自动刷新 revision 后代用户重试；让用户核对并再次确认目标。
成功写入后刷新失败提示“操作已完成，刷新失败”；结果未知则先读取核对。

沿用同步 mutation 锁和 shell pending，写入期间锁定 Workspace / KB / Family 选择，
登出始终可用。上下文、token、角色或选择变化立即丢弃 File、草稿、确认与旧详情。
generation guard 覆盖 A-B-A 与迟到响应；网络取消不等于数据库回滚。
引用旧 metadata 请求失败时仍保留已有摘录并安全说明“当前状态未确认”，不伪造激活状态。
不存正文/token 到浏览器持久缓存，不渲染用户 HTML；具备 labels、键盘确认、焦点、
aria-live、窄屏与长文件名换行。产品界面不展示迁移号或数据库实现。

## 8. Reuse / 实施模块边界

复用已批准的 SQLAlchemy/PostgreSQL/pgvector、Pydantic、python-multipart/pypdf、
现有 splitter / EmbeddingProvider / SDK、Next.js/React、Vitest/Testing Library 与 pytest。
这是现有摄取流程的版本边界，未新增实质 AI 基础设施；不引入外部文档平台或重写 SDK。
许可证/部署边界沿用现有依赖，不作未核验的最新维护性声明，不增加供应商或服务。

预期修改：models/document + 新 Family model；schemas/document/retrieval/answer；
documents/retrieval routes 与服务；知识库状态写入的行锁；answers/Agent citation 映射；
evaluation_snapshot 的有效语料捕获/快照版本兼容；0014；现有 frontend api、knowledge-admin、
knowledge-qa / Assistant 引用显示；相应测试。避免通用版本引擎、仓储层或额外路由架构。
Phase B 再更新 DATABASE / ARCHITECTURE 的实现记录；此规格不能被当成已建表证据。

## 9. Acceptance Criteria

| ID | 可验收结果 |
|---|---|
| AC-001 | 0013 -> 0014 保留原 Document/Chunk 内容、ID、状态、行数；每条独立回填，不按同名归并；单一 head |
| AC-002 | 初始上传契约保留；替代版本按 Family 分配唯一递增编号，ready/failed 均不自动激活 |
| AC-003 | 文本/哈希/版本身份完成后冻结；首次完整索引原子保存，失败不留部分 Chunk，重复索引不替换 Chunk ID |
| AC-004 | 只有 ready、完整同配置索引、同父对象版本可激活；无 current 的 Family 同样要求显式激活替代版本 |
| AC-005 | expected_revision 与行锁防丢更新；竞争激活一胜一冲突；同目标 fresh/no-op 与 stale/409 符合规则 |
| AC-006 | 新检索、知识答案、Agent 知识路径仅包含 current+ready+索引版本；旧/候选/禁用版本不进入 top-k |
| AC-007 | 当前禁用无隐式回退，历史重新启用不激活；active KB 与写入竞争有一致先后；失败保持旧指针 |
| AC-008 | 引用保留具体版本和冻结 Chunk；新引用附 family_id/版本显示；旧引用元数据可读，迁移前已删 Chunk 的限制明确 |
| AC-009 | 新 Evaluation 语料与实际有效版本一致且捕获无混代；漂移失败符合旧契约；历史快照/结果/Bad Case 不重写 |
| AC-010 | 四角色、两 Workspace、错 KB / Family / Document、禁用身份与处理中撤权均不能绕过后端检查 |
| AC-011 | 完整中文上传→索引→激活/回退流程、失败恢复、持久索引、键盘/移动与乱序/双击防护通过；无隐式 Provider 调用 |
| AC-012 | 安全错误/保密边界无扩大；downgrade 仅无后续写入时允许，新版本状态下拒绝危险降级 |
| AC-013 | 专项/全量必需测试无跳过，自审及独立高风险复审完成，commit/push/PR 就绪；人工合并后才称 Feature 交付 |

## 10. Test Requirements

### 10.1 PostgreSQL migration / persistence

专用测试库覆盖空库和已有 ready/disabled/failed/uploaded/processing、同名文件、非 1
版本号、已索引与未索引数据回填；校验全文/Chunk byte 与 IDs/旧时间/旧迁移保留。
约束负例涵盖错误 Workspace / KB / Family/current 指针、重复版本、非法哈希、索引
字段部分 NULL、维数/count/status/text 组合；错误旧数据必须 rollback，不自动修复。
升级、无后续写入降级/再升级、revision>1 降级拒绝、单一 head、metadata parity。

### 10.2 API / 状态 / 并发

PDF/TXT/MD 和越界/编码/解析错误、失败编号保留、同文件非去重、无父 KB 上传、
disabled 父 KB、首次失败/处理中 Family 后续替代版本准备、显式激活；原 API 字段/
路径/排序与状态转换保留，content 不从元数据泄露。

真实独立 Session + barrier 覆盖并发版本号分配、两次激活、fresh/stale 同目标、
并发首次索引（freeze 胜者/安全复用）、索引时禁用/撤权、禁库 vs 激活/索引、
上传最终发布前撤权、锁超时、持久化故障 rollback；不以串行 mock 证明数据库原子性。
Provider 请求在锁外；非法激活/权限失败/重复成功索引不调用 Provider。

检索用控制向量让历史/候选版本距离更近，仍不进入结果；current switch/回退/
disable/re-enable、KB disable、跨 Workspace / KB / Family 必须先过滤。
答案/Agent 引用绑定实际版本，查询 SQL 快照前后可控切换，不混代。

### 10.3 评测 / 历史

新语料只含有效版本；单快照捕获测试在两次读取间竞争激活，不混旧 Document 与新 Chunk；
准备/执行间的切换/禁用/首次索引触发已有漂移错误，重复索引不触发伪漂移。
旧 snapshot_version 可读取；终态 Runs/Cases/Bad Cases/metrics/原 hashes 不变。
旧返回 excerpt 与冻结原 Chunk 可核对；迁移前缺失 Chunk 不捏造来源。

### 10.4 前端 / 回归 / 验证

API tests 验证五条新调用、FormData boundary、Bearer、revision/body 白名单、
Document 新元数据及 citation 兼容；mock errors 含恶意输入时不泄露。
组件/shell 覆盖完整主流程、empty/failed/processing/current/historical/disabled/未索引，
409 人工重新确认、成功后刷新失败、结果未知先核对、双击/回车、A-B-A、登出/
角色撤销/迟到读取与写入响应，回归知识管理/Assistant/问答/Agent 管理/审批/评测/问题案例。

先跑 Feature 021 专项，再串行执行完整 PostgreSQL 集成测试和 pytest、Ruff，前端
pnpm test、pnpm lint、pnpm build，migration/head/schema checks、git diff --check。
四角色/两 Workspace 在桌面和窄屏完成浏览器主流程，使用 fake providers 和受控数据。
不以 SQLite 替代，不跳过必需测试，不用历史 Feature 测试数充当本次验证。
记录实际命令、环境、结果、截图和独立复审到
`docs/features/021-document-version-management-verification.md`（Phase B 才创建）。

Phase A 只做来源/链接/Markdown/差异检查，不运行应用 suite、数据库或 Provider；
独立高风险实现复审在 Phase B 完成后、人工合并前执行。

## 11. Out of Scope

Feature 022 Agent 配置版本、023 Run 比较/复测链接、026 会话、后续申请/资料/交付、
Workflow；文档合并拆分/移动/重命名、正文差异编辑、原文件存储/下载、历史正文读取
新权限/API、硬删除/清理/保留期、模型或维数更换、向量索引平台、分支版本、定时发布、
自动激活/回退、未完成上传恢复、批处理/后台调度、幂等键、公共分享、OCR、新 RBAC、
真实企业连接、生产敏感内容/联网验收、运行/生产 migration、部署或自动合并。

## 12. 风险与实施审批

| 限制 | 对策 / 实际边界 |
|---|---|
| 历史文本/向量永久保留增加存储 | 明确不含 purge；MVP 小规模，后续保留策略另设功能 |
| 原 re-index 会删除引用来源 | 批准后改为索引冻结/安全复用；更新 UI、测试和说明 |
| 旧已删除 Chunk 无法恢复 | 保留已有 excerpt，不承诺迁移恢复来源 |
| 首版/旧未索引 current 仍不可检索 | UI 区分解析/索引/current；替代激活严格要求完整索引 |
| 进程中断/网络中断可能留记录或重复上传 | 不自动重试；列表核对，失败版本保留且不激活 |
| 多管理员和长 Provider 请求 | Family revision、统一锁序、提交前重新校验；锁外 Provider |
| 在途问答使用切换前证据 | 允许完成并标记原版本，不改已有结果；新 SQL 使用新 current |
| 添加版本后降级不安全 | 只允许纯回填状态降级，检测后续写入并拒绝危险回滚 |

按照 [AGENTS.md](../../AGENTS.md) 的明确要求
“STOP and request human approval before:”及所列的“new database migrations”、
“security-sensitive changes”和“architecture changes”，Phase B 必须等待下列具体批准。
本提案不修改认证/RBAC/审批政策，但属于迁移与检索隔离的高风险工作。

| Gate | 待批准的具体事项 |
|---|---|
| H1 - Schema / 测试环境 | 创建 0014 与上述 Family/Document 扩展和逐条回填；仅在核实的 localhost:5432 `enterprise_ai_workbench_test` 做 schema 重建、迁移/降级/约束验证，清除该专用测试库数据；与运行库不同且无并发测试 |
| H2 - 生命周期 / 兼容 | 批准初始 current 兼容例外、替代显式激活、历史回退、内容/Chunk 冻结、重复索引复用、revision/锁序与安全降级限制 |
| H3 - 检索 / 历史边界 | 批准所有知识路径与新评测的 current-only 语料规则、单快照捕获和既有漂移行为、历史文本/Chunk 保留及引用保证起点；保留当前权限/外发白名单，无历史正文新 API |
| H4 - API / UI | 批准五个新接口、已有响应附加字段、触及路由的安全错误和知识管理版本/引用界面；要求完整回归和独立高风险复审 |

批准应引用本提案 commit 与 H1–H4，仅授权该规格实现和上述指定测试库验证。
运行/生产库升级、真实 Provider 冒烟、生产数据、额外依赖/权限或自动合并不在批准内。
Phase A 草稿 PR 不使用 Closes 关闭功能 Issue；Phase B 验证后更新同一 PR 才可
使用 Closes。人工合并前停在 PR-ready，不开始 Feature 022。

## 13. Phase A 验证记录

2026-10-11：已核验远端 main、规划 PR #40、前置 PR #49 的合并及 Issue #48 关闭，
建立 Feature 021 Issue #50。规格必需章节、AC-001–013、H1–H4、五条新增 API、
基线/Issue 引用、本地 Markdown 链接与冲突标记检查通过。仅规格和 ROADMAP 改动。
自审覆盖首次上传兼容、索引冻结、错父对象、并发指针切换、旧引用限制、评测快照
一致性和安全降级；补充 legacy_backfill 标记，覆盖新上传登记后尚未完成解析的降级拒绝。
提交前执行 staged diff / whitespace 检查；交付状态以实际 commit、push 和草稿 PR 为准。

未运行应用测试、数据库迁移/重建或 Provider 请求。尚无 Phase B 实现或测试证据，
独立高风险实现复审待实施后完成；不能据此宣称 Feature 已实现/验证/交付。
