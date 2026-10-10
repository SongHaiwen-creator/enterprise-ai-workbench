# Feature 019 - Implementation and Verification

日期：2026-10-10（Asia/Shanghai）。状态：实施与验证完成，待人工合并。
基线：`origin/main` `56b699ad2cd36d40df4e642404108fc7555c89ec`。
批准：用户在本聊天以“approve，实施”批准 proposal commit `1c61fca`，随后要求继续。
规格：[019-knowledge-admin-ui.md](019-knowledge-admin-ui.md)。
Issue：[46](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/46)。
PR：[47](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/47)。

## 实施范围

- `/app` 增加中文知识管理区域、独立的知识权限导航及桌面/移动布局。
- 对接九个既有知识库/文档/索引接口，无新增后端能力。
- 知识库创建、字段差异编辑、描述清空、确认禁用、启用；管理后共享列表更新。
- 单文件 PDF/TXT/Markdown 上传、10 MiB 校验、浏览器 multipart boundary、元数据详情。
- 201 failed 明确展示解析失败，修正后另行上传，不自动索引或替换旧文档。
- 显式索引/重索引、原生确认框、Provider 提示和本次成功结果；不伪造持久索引状态。
- 文档合法启停、禁用父库下的管理行为、手动刷新与错误恢复。
- mutation 防重复、导航锁定、Workspace/session/role 重挂载、乱序读取与退出后结果隔离。
- 401/403 清理受保护状态，404/409 GET 刷新，无自动写入重试；成功写入与刷新失败分开。
- 67 项前端专项：14 API client、45 管理组件、8 整页 shell 测试。

没有新增依赖、后端 API/契约、权限策略、数据模型、迁移、日志正文、生产 Provider 请求、
运行数据库操作、部署或后续 Feature。文档版本仍留给 021。

## 验证结果

| 检查 | 实际结果 |
|---|---|
| Feature 019 前端专项 | 67 passed；无 skips；三个测试文件 |
| 既有知识 API PostgreSQL 专项 | 158 passed；无 skips；Knowledge Base、Document、Retrieval、Answer |
| 完整 backend pytest | 1633 passed；无 skips；74 个既有类别 deprecation warnings；83.41 秒 |
| Ruff `check backend benchmarks` | passed |
| 完整 frontend `pnpm test` | 9 Node API + 177 Vitest tests passed；无 skips；新增 67 项包含在 177 内 |
| `pnpm lint` | passed |
| `pnpm build` | passed，包含 `/`、`/app`；TypeScript 与静态页面生成通过 |
| 浏览器验收 | 1440×1000、390×844；65 次合成 API 请求；无 pageerror、无页面横向溢出 |
| diff 自审 | API/权限/范围/竞争状态检查完成；仅 Feature 019 前端及文档 |
| `git diff --check` | passed |

专项先于全量回归运行。对自审发现的读取状态问题进行了修复和对应回归，然后重跑
前端专项、全量、lint 和 build。后端未改动，后端全量结果未冒充 live 模型质量测量。
早期失败不计入通过结果：jsdom 缺少原生 dialog 方法、测试选择器不匹配及 initial
effect 的同步状态更新 lint 错误，均在最终验证前修正，没有跳过测试或削弱后端规则。

## PostgreSQL 环境与命令

使用已有 Python venv，`PYTHONPATH` 明确指向本工作树 backend。只读取原项目本地
配置中的两个数据库连接用于测试；不复制 `.env` 或密钥到 Git。测试进程使用临时 JWT
测试 secret，移除 OpenAI key，模型全部注入 fake providers。

执行前检查 `TEST_DATABASE_URL` 与运行库不同、精确数据库名为
`enterprise_ai_workbench_test`、同一本地 PostgreSQL、无其他测试会话；持有测试运行
advisory lock。PostgreSQL 专项与全量串行执行，fixture 重建和迁移只发生在专用测试库。
没有执行运行库迁移或写入；仓库 migration head 0013 不被描述为运行库状态证明。

pytest 的实际选项为：

```text
# 在本工作树 backend 目录；本地 runner 先完成上述配置/安全检查
tests/integration/test_knowledge_base_api.py tests/integration/test_document_api.py
tests/integration/test_retrieval_api.py tests/integration/test_answer_api.py
-q -x -p no:cacheprovider --basetemp=../.cache/feature019/backend-focused

tests -q -x -p no:cacheprovider --basetemp=../.cache/feature019/backend-complete
```

前端实际命令：

```text
pnpm install --frozen-lockfile
pnpm exec vitest run --configLoader native tests/knowledge-admin-api.test.tsx tests/knowledge-admin.test.tsx tests/knowledge-admin-shell.test.tsx
pnpm test
pnpm lint
pnpm build
```

所有包均来自既有 lockfile，未修改依赖清单或 lockfile。Next dev 自动生成的本地
AGENTS/CLAUDE 文件与开发态 next-env 路径不作为 Feature 019 变更提交。

## 浏览器证据与实际边界

使用现有 Playwright 和已安装 headless Chromium；浏览器首次默认 executable revision
不在本机，随后指定已有 Chromium 1187，未安装新浏览器或依赖。
通过 localhost:3019 启动前端，并拦截全部 API 为合成响应；无实际 Provider 或运行库调用。
这是界面集成验收，后端权限/隔离/状态/索引原子性由上述真实 PostgreSQL 测试独立验证。

流程包括：创建库 -> 验证真实 multipart boundary -> 上传但不自动索引 -> 确认框 Escape
取消 -> 索引 502 后显式重试 -> 本次结果 -> 问答显示引用 -> 文档禁用后资料不足 ->
文档启用 -> 知识库禁用后问答不可提交 -> 重新启用 -> 201 failed 可见。
窄屏验证抽屉、Workspace 角色切换和退出；验证 employee/agent_admin 没有知识管理入口，
system_admin 能进入。截图经过视觉检查；本地日志、截图和脚本留在忽略的 `.cache/feature019`。

## 自审修正与已知限制

- 读取 generation 独立约束知识库、文档列表、文档详情；旧列表的 403 不再清空新选择。
- 选择知识库时结束被取消的列表 loading，防止保留禁用表单；增加实际交互回归。
- 文档切换清空上一次索引结果；权限失败关闭确认框并清空草稿/File。
- 网络结果不明先刷新；mutation 成功但 GET 刷新失败显示已完成，避免再次 POST。
- 修改后的知识库列表同步到 shell，读失败时清空共享缓存并阻止问答使用旧状态。

既有 API 无持久索引状态、上传去重和版本替换，也无跨用户编辑 revision 防覆盖。
重新索引替换 Chunk ID；本功能不新增历史引用解析承诺。上述限制已在界面和规格说明。
normal-risk 范围按 AGENTS 完成实现测试、回归与自审；未派生独立审查代理。
PR-ready 不表示已交付，最终合并由人工执行。合并后在新聊天核验下一规划功能。
