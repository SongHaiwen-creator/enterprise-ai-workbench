# Feature 021 - Implementation and Verification

日期：2026-10-11（Asia/Shanghai）。状态：实现与必需验证通过；PR #51 待人工审阅/合并。
基线：`origin/main` `2508d67f0551a3112c80eb78438c9f7b166e0b5b`。
批准：用户以“approve”批准 proposal `1c435300cd36912804539b4fea263d180e852385` 的 H1–H4。
规格：[021-document-version-management.md](021-document-version-management.md)。
Issue：[50](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/50)。
PR：[51](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/51)。

## 实现范围

- 新增逻辑文档 Family；保留 Document UUID 作为具体版本身份。五条新版本 API，
  原 Document 上传/列表/详情/状态/索引路径与既有字段保留。
- 首版兼容当前指针、替代版本显式激活/历史回退、Family revision 冲突检测、
  原子版本号分配、解析/索引失败不切换当前指针。
- 文本 SHA-256 与首次成功完整索引冻结；重复索引复用已有结果，不初始化 SDK，
  也不要求提供 API key。Provider/解析阶段无 KB/Family/Document 行锁。
- KB -> Family -> Document 一致锁序、五秒锁超时安全 409、最终发布前重新鉴权。
  KB 状态写入共用该事务边界，禁用当前版本不自动回退。
- current+ready+完整同模型索引的公共 SQL 条件，供 search、答案、Agent 知识路径
  和新评测语料捕获复用。语料在单一流式 SQL 快照捕获，不混合切换前后版本。
- 新知识 context 的 snapshot_version=2，Run 外层 envelope 仍为 v1；旧 context
  可读且旧终态结果/指标/哈希不改写。激活期间的 Run 仍按原漂移规则失败。
- 中文 Family/版本列表、替代上传、持久索引状态与激活确认；旧/新文件名与版本均
  可确认。引用保持原摘录，可显式查询原版本的现有元数据，未新增历史全文权限/API。
- 0014 单条回填 Family，保留原 Document/Chunk 内容、IDs、状态和时间；不按同名归并。
  新 Family 或已有版本管理写入后拒绝危险降级。旧迁移不修改，无新运行依赖。

## 验证结果

| 检查 | 实际结果 |
|---|---|
| 最初 Feature 021 PostgreSQL API 专项 | 16 passed，无 skips |
| 知识/版本/评测/模型/迁移/业务基线专项选集 | 225 passed，无 skips |
| 追加并发/迁移/评测漂移与历史专项选集 | 45 passed，无 skips |
| 既有 Evaluation/Bad Case 历史迁移回归 | 65 passed，无 skips |
| 最终完整 backend pytest（含 PostgreSQL） | **1684 passed，无 skips**；89 条既有 Starlette/Alembic deprecation warnings；97.73 秒 |
| Ruff `check backend benchmarks` | passed |
| 前端既有知识管理专项 | 67 passed，无 skips |
| 新版本 API/组件/引用元数据专项 | 17 passed，无 skips |
| 完整前端测试 | **9 Node API + 261 Vitest passed**，22 个 Vitest 文件，无 skips |
| `pnpm lint` | passed，无 errors/warnings |
| `pnpm build` | passed，TypeScript 与 `/`、`/app` 静态生成通过 |
| 0014 / schema 验证 | 单一 head、完整 Base metadata parity、SQL NULL/复合 FK 负例、回填/降级/再升级与不安全降级拒绝通过 |
| 旧迁移保留 | 新增 0001–0013 Git-normalized byte 对照测试通过；Git diff 未修改旧迁移 |
| 浏览器验收 | 1440×1000、390×844；四角色、两个 Workspace，128 次合成 API 请求，0 pageerror，无横向溢出 |
| 独立高风险复审 | 两项阻断修复并复核；最终无剩余阻断 |

不同专项选集存在重叠，计数不相加。最终完整套件已包含最新全部测试，包括两种
降级拒绝 guard、迟到首版竞争和新的 schema 样例；历史测试数不作为本次证据。
提交前完成 git diff / staged whitespace / 范围自审；实际提交与推送以 PR head 为准。

## 命令与环境

后端复用 `D:/Projects/enterprise-ai-workbench/backend/.venv/Scripts/python.exe`，
PYTHONPATH 指向本工作树 backend。验证 runner 仅从已有本地配置读取数据库连接，
不复制 `.env`、不打印连接凭据；环境移除 OPENAI_API_KEY，使用临时随机 JWT secret。
所有模型均使用 fake providers。完整套件命令为：

```text
# runner 在启动 pytest 前完成下面的测试库隔离/排他检查
python -m pytest tests -q -x --tb=short -p no:cacheprovider --basetemp=<本聊天可写目录中的独立 Feature021 临时路径>
# cwd: repository root
python -m ruff check backend benchmarks
git diff --check
# cwd: frontend
pnpm install --frozen-lockfile
pnpm exec vitest run --configLoader native tests/document-versions-api.test.tsx tests/document-versions.test.tsx tests/citation-version.test.tsx
pnpm test
pnpm lint
pnpm build
```

测试库精确为 localhost:5432 `enterprise_ai_workbench_test`，与运行库不同。
每次 DB 选集先验证 current_database、无其他 client backend 会话，再持有 advisory lock
串行执行。pytest fixture 重建该专用库 public schema，并应用仓库迁移。
授权来源是规格 H1，明确包含这个库的数据清除/迁移/降级测试；没有再次隐式扩大范围。
容器仍为既有 pgvector PostgreSQL 17，没有重建容器/卷或改用 SQLite。
专用库内的独立 Session/线程用于证明竞争、原子性和锁超时；没有其他工作树并发验证。

初次回归的差异包括新增 family_id、已批准的 re-index 冻结规则、旧 head=0013
假设和旧 Document schema 样例。已更新测试 fixture/历史 schema 对照；没有更改
权限、降低断言或跳过测试。新 ready-content CHECK 由独立 SQL NULL/内容负例验证，
不再构造非法 ready/null 内容来测试索引。
历史迁移 helper 对照旧 Document schema；0014 仍对完整当前 Base 做严格无漂移检查。
另一次沙箱内独立辅助非 DB pytest 长期等待，已清理该辅助进程；完整套件已覆盖
全部非 DB 测试并通过，辅助进程不作为通过证据。

## 自审与独立复审

独立代理只读检查 migration/model/归属、冻结索引、鉴权与锁序、所有知识路径、
评测单 SQL 捕获/旧历史读取、安全错误和前端异步状态；未执行 DB、Provider 或修改文件。

发现并修复：

1. 首版锁外解析迟到，可能覆盖另一个管理员已显式激活的 v2。最终发布只在 current
   仍为空时填充首版指针；独立 Session 的慢首版/快替代激活测试覆盖。
2. KB 状态写入新行锁的超时缺少一致错误处理。改用共享 write_boundary，五秒超时
   rollback 并返回安全 409；独立 Session 的争锁测试覆盖。

最终复核确认上述修复、懒初始化索引 provider、旧文件名确认与历史 metadata helper
无剩余阻断。迁移字节对照的新增证据位于
`test_document_version_migration.py::test_revisions_0001_through_0013_remain_unchanged`，
不声称既有 APPLIED_MIGRATION_SHA256 常量已扩展。

## 浏览器证据与保留限制

使用已有 Playwright 和 Chromium headless shell 1187，在本地生产构建上验收。
所有 `/api/**` 均拦截为合成响应，未实际登录、访问数据库、调用 Provider 或企业系统。
前端 mock 不作为后端授权/隔离证据；它们由上述 PostgreSQL 验证独立证明。

流程包括替代解析→索引失败/重试→取消激活→revision 冲突→明确激活→历史回退，
解析失败保留当前版本、持久冻结索引、禁用/启用、禁库、移动导航和 Workspace
清空，以及 Agent 管理/审批/日志/评测/问题案例/成员/Assistant 页面回归。
员工页面保留切换前已返回的原摘录；另一个管理页面切换 current 后，员工显式
读取原版本元数据显示历史状态，新提问展示当前版本。此场景不代表会话持久化。

截图已视觉检查：[桌面版本详情](../screenshots/document-versions/desktop.png)、
[历史引用](../screenshots/document-versions/historical-citation.png)、
[移动版本列表](../screenshots/document-versions/mobile-list.png)、
[移动冻结索引](../screenshots/document-versions/mobile.png)。
本地 runner、browser 脚本与合成日志留在忽略的 `.cache/feature021`。
验收服务已清理，不留下新运行环境或部署。

保留限制：历史内容/向量增加存储，无 purge；迁移前已删除的 Chunk 无法恢复；
中断可能留下 uploaded/processing；未知上传结果先核对，重复上传仍可能登记重复版本；
在途答案可继续使用已捕获的旧证据。未执行运行/生产迁移或真实 Provider 冒烟。
只有人工合并后才称 Feature 已交付，不启动 Feature 022。
