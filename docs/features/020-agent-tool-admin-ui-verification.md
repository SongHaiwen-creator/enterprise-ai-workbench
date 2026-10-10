# Feature 020 - Implementation and Verification

日期：2026-10-10（Asia/Shanghai）。状态：已实现并通过全部必需验证；PR #49 待人工审阅/合并。
基线：`origin/main` `2222e90ce4375c243b810376bb47a5f235e4b8d0`。
批准：用户以“approve”批准 proposal commit `6cc4278` 的规格实施。
规格：[020-agent-tool-admin-ui.md](020-agent-tool-admin-ui.md)。
Issue：[48](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/48)。
PR：[49](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/49)。

## 已实现范围

- `/app` 增加“Agent 与工具”管理区，沿用当前 Workspace 的 Agent/System 管理权限。
- 接入 11 个既有 API；管理列表含全部状态，员工 Assistant 仍为 active-only 摘要。
- Agent 默认草稿创建、差异编辑、描述清空、三状态独立确认；工具默认禁用创建、
  名称/说明编辑和启停。服务端字段、能力类型、风险、参数、审批政策不可编辑。
- 三个注册 Mock 能力的中文只读说明，附窄的 JSON 帮助数据和后端契约一致性测试。
- 工具分配/解除，区分关系存在、未生效和候选状态；不提供执行/试运行入口。
- 204 成功不解析空 JSON，PUT/DELETE 无 body；重复关系操作沿用既有后端幂等规则。
- 同步提交锁、导航锁定、原生可取消确认框、未保存草稿确认、内存保密状态和安全错误。
- Workspace/token/role 重挂载、独立列表/详情/共享 Agent 请求失效保护；登出后旧结果不回写。
- Agent 改动同步 shell，保留仍有效的 Assistant 选择；失效选择移除、共享读取失败禁用旧列表。
- 401/403 清理、404/409 读取恢复、未知结果先核对、成功写入与刷新失败明确区分。

无新增后端路由、业务契约、权限/审批规则、数据库对象、迁移、依赖或后续 Feature。
应用界面不触发 Tool adapter，不改写运行审批/评测历史。测试仍验证已有 Mock
执行路径；没有真实 Provider/企业系统调用、运行库迁移或部署。

## 已完成验证

| 检查 | 实际结果 |
|---|---|
| Feature 020 前端专项 | 67 passed；13 API、43 组件、11 shell；无 skips |
| 完整前端测试 | 9 Node API + 244 Vitest passed；19 Vitest 文件；无 skips |
| `pnpm lint` | passed，无 errors/warnings |
| `pnpm build` | passed，TypeScript、`/` 与 `/app` 静态生成通过 |
| 后端非数据库专项 | 34 passed；含 5 项注册帮助契约测试 |
| 后端全部非集成测试 | 686 passed；无 skips；1 项既有 Starlette deprecation warning |
| Ruff `check backend benchmarks` | passed |
| 浏览器验收 | 1440×1000、390×844，四角色、两个 Workspace，155 次合成 API 请求，0 pageerror，无横向溢出 |
| `git diff --check` 与自审 | passed；范围、契约、角色、共享状态、异步竞争已核对 |
| Feature 020 后端专项（含 PostgreSQL） | 166 passed；无 skips；2 项既有 deprecation warnings |
| 完整 backend pytest（含 PostgreSQL） | 1638 passed；无 skips；74 项既有 deprecation warnings；84.84 秒 |

全部必需验证已通过；PR-ready 不等于功能已交付，最终合并由人工执行。
此前 Feature 019 的测试数不作为本功能证据。
最初三项组件测试失败涉及 jsdom cancel 事件、读取时机与 deferred mock 尚未启动，
已修正真实事件/等待条件并通过专项。单元回归首次运行遇到系统 temp 目录权限，
改用工作树内明确 basetemp 后 686 项通过；没有跳过用例或削弱后端权限。
Ruff 从仓库根运行，未修改既有 benchmark import 布局来适配其他 cwd 的推断差异。

## 实际命令与环境

前端使用 lockfile 中原有依赖，清单/lockfile 无变更：

```text
pnpm install --frozen-lockfile
pnpm exec vitest run --configLoader native tests/agent-tool-admin-api.test.tsx tests/agent-tool-admin.test.tsx tests/agent-tool-admin-shell.test.tsx
pnpm test
pnpm lint
pnpm build
```

后端使用已有 `D:/Projects/enterprise-ai-workbench/backend/.venv/Scripts/python.exe`，
`PYTHONPATH` 指向本工作树 backend；不复制 `.env` 或凭据到 Git。

```text
# cwd: backend
python -m pytest tests/test_registered_tool_help.py tests/test_agent_schemas.py tests/test_agent_authorization.py tests/test_tool_calling.py -q -p no:cacheprovider
python -m pytest tests --ignore=tests/integration -q -x --tb=short -p no:cacheprovider --basetemp=../.cache/feature020/backend-unit
# cwd: repository root
python -m ruff check backend benchmarks
git diff --check
```

浏览器用已有 Playwright 和 Chromium headless shell 1187，生产构建仅在 localhost:3020
运行。全部 `/api/**` 被拦截为合成响应，没有实际登录、模型、数据库或企业系统调用。
UI mock 不证明后端授权/隔离；角色、隔离和审批由上述真实 PostgreSQL 专项独立验证。
流程包含草稿创建→员工不可选→取消/确认激活→三个工具创建并启用→逐个分配→
204 解除与重新分配→422 保留输入→修正保存→Assistant 名称同步→回归既有页面→
禁用/激活→窄屏工具禁用→已分配未生效→切换员工 Workspace→四角色入口检查。

截图已视觉检查：[桌面表单](../screenshots/agent-tool-admin/desktop.png)、
[桌面分配](../screenshots/agent-tool-admin/desktop-assignments.png)、
[移动列表](../screenshots/agent-tool-admin/mobile.png)、
[移动能力限制](../screenshots/agent-tool-admin/mobile-help.png)。
本地验收脚本、日志/临时产物保留在忽略的 `.cache/feature020`。

## PostgreSQL 环境与审批来源

专用验证脚本逐次读取已有本地连接配置；确认数据库精确为
`enterprise_ai_workbench_test`、本地地址、与运行库不同、无其他会话；持有验证
advisory lock；串行执行规格中的 PostgreSQL 专项及全量 pytest。既有 fixture 将
DROP/CREATE 该测试库的 public schema 并应用已有迁移，会清除测试数据。
不创建新迁移、不触及运行库/生产库。

[AGENTS.md](../../AGENTS.md) 明确要求：
“STOP and request human approval before: database-destructive operations”。
初始自动审批审查要求补充该具体目标的授权；用户在含目标、数据清除和验证范围
的问题中回复“刚刚打开了docker app，重试”，随后再次要求“继续”。初始审批服务
用量限制解除后重试通过，没有绕过审批。各次测试已执行独占会话检查与 advisory
lock，并严格限制在专用测试库。

本地服务已恢复；核验既有 `enterprise-ai-workbench-postgres_pgvector-1` 使用
`pgvector/pgvector:0.8.6-pg17-trixie` 和原有 `enterprise-ai-workbench_postgres_pgvector_data`
持久卷，没有重建容器/卷或启动旧 PostgreSQL 容器。真实测试仅使用
`enterprise_ai_workbench_test`（localhost:5432），运行库连接只用于隔离校验。
环境变量仅保留需要的数据库配置和随机临时 JWT secret，移除 OpenAI key，模型全部
为 fake providers。没有运行库 SQL 写入、迁移或实际 Provider 请求。

PostgreSQL 专项命令包含规格 8.3 中的七个既有测试文件和新增注册帮助契约文件，
结果 166 passed；随后独立复核既有业务基线 PostgreSQL 测试 2 passed。原测试用例
和权限断言未修改。全量在工作树 basetemp 遇到 Windows checkpoint 临时 JSON
替换拒绝，因而把最终全量临时产物移至本聊天明确可写的独立目录：

```text
# cwd: backend；本地 runner 先完成隔离和排他检查
python -m pytest tests -q -x -p no:cacheprovider --basetemp=C:/Users/shwdm/.codex/visualizations/2026/10/10/01a1246b-1978-79c3-825f-61fdb950cd1b/feature020-pytest
```

此环境调整不跳过、改写或重排测试，不修改应用的文件保存逻辑；历史失败不算通过。
repository migration head 不作为任何运行环境已升级的证明。

## 自审与保留限制

自审修正了旧共享列表覆盖后续保存的竞态，并用独立请求代数和 deferred promise
验证；保留有效 Assistant 选择；确认框复用原生 modal 样式并支持 Escape；选中配置
有文字与可访问状态。Prompt 仅管理详情读取，不放进员工摘要、浏览器存储或日志。

现有跨管理员后写覆盖、Agent 创建无去重、解除后重加关联无 revision、无配置
历史/逆向分配 API 均保留。风险/权限与审批权威仍在后端，帮助数据不授予执行权限。
normal-risk 范围未派生独立审查代理；已完成专项、回归、自审、提交推送和 PR 更新，
停在 PR-ready，最终合并由人工执行。后续 Feature 留到合并后的新聊天。
