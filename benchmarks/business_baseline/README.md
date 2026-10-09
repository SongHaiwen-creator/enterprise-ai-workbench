# 员工服务业务基准 v1

这是现有产品的评测数据与本地工具，不增加产品 API、不更改评分器和权限策略。
12 份原创合成制度，108 个问题：48 知识、24 工具规划、24 权限策略、12 拒绝。
开发集 74 题，保留集 34 题；整组场景不跨集合。保留集在测量前冻结，但仍由同一
代理编写，不等同于独立业务专家或真实流量样本。标准答案需要业务负责人复核。

## 数据与评测口径

`data/manifest.json`、`data/cases.json` 和 `data/docs/` 是事实源。
每道知识题含目的、标准答案要点、来源与逐字证据；不会把正确答案发给被测模型。
`build_data.py` 保留原始编写记录；测量后不能修改 v1 来迎合结果。

- Agent 结果复用 Feature 016 的结构化评分；非错误通过率同时显示通过/计划、覆盖与错误。
- RAG 使用现有 search/answer API；前 5 个**片段**映射文档，算 Hit@3/5、宏平均 Document Recall@5。
- 回答全文、引用及模型元数据存于本地，用逐条事实 rubric 复核。
- 答案正确性不由关键词或“有引用”推断。`reviews` 的 `correct`、`fact_supported`、
  `reviewer` 由署名复核填写；未复核显示未复核，不计正确。失败或缺失的答案不能算已复核。
- 工具仅 dry run，不执行 adapter、不创建 Approval 或 IT 业务记录。
- 权限为既有策略函数模拟；不是额外安全渗透测评。`policy` 可完全离线执行这 24 题。
- 实际业务工时、成本与满意度尚未采集，不发布 ROI 或真实业务质量结论。

## 执行

在仓库根目录，用已有 backend venv；若当前 worktree 没有 venv，使用主仓库已有 Python，
同时把 `PYTHONPATH` 设为当前 worktree 的 backend（不安装新依赖）。

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'backend'
$benchmarkPython = 'D:\Projects\enterprise-ai-workbench\backend\.venv\Scripts\python.exe'
& $benchmarkPython -m benchmarks.business_baseline.runner validate
& $benchmarkPython -m benchmarks.business_baseline.runner policy --output-dir benchmarks/business_baseline/output-policy-v1
```

真实测量需要运行最新已合并的后端（localhost:8000，数据库已是 0013）。在本地 `.env`
配置 `WORKBENCH_EMAIL` 与 `WORKBENCH_PASSWORD`，或 `WORKBENCH_ACCESS_TOKEN`。
使用已有的正常管理员登录，不要把凭据发到聊天、提交 Git 或放在 CLI 参数里。
有多个 Workspace 时额外指定 `--workspace-id`。知识库创建/上传/索引需要
`system_admin`；仅 `agent_admin` 不具备准备语料的权限，不会更改它的角色。

```powershell
& $benchmarkPython -m benchmarks.business_baseline.runner all `
  --env-file D:\Projects\enterprise-ai-workbench\.env `
  --output-dir benchmarks/business_baseline/output-live-v1 `
  --acknowledge-egress
```

`--acknowledge-egress` 确认这批合成语料和问题可经现有配置发送给 OpenAI；使用既有
embedding/routing/selector/generation 设置与预算，不添加 judge。一次完整运行包含
12 份文档索引、56 次检索、56 次答案请求和 26 个 Agent 批次（共108题）。实际模型
调用数取决于路由与拒绝结果；权限24题不调模型。不自动重复成功请求；第一次服务配置、
契约或 RAG 请求错误就停止诊断，不用大量付费请求反复尝试。需看波动时另建一次
输出目录，在相同 v1 语料和配置下测量，不宣称一次运行证明稳定性。

每个测量阶段前，额外运行一批不调模型的权限用例来捕获现有 API 的配置快照；
不计入108题结果。Provider、指令/输出schema哈希、策略及工具配置冻结，变化则停。
答案返回的模型/提示/预算元数据逐题比较。Search API 不暴露查询embedding的元数据，
Index API不暴露chunking实现哈希，因而不能证明探针与请求之间服务器重启或代码更改
绝对不存在；测量时须保持同一后端构建，不在测量过程中升级服务。

本机 HTTP 客户端禁用环境代理和重定向，登录凭据不会经配置的外部代理转发。

也可分阶段运行 `prepare`、`retrieval`、`answers`、`agent`，每阶段正常登录。
这可避免长时间运行导致30分钟访问令牌到期。`all` 不在令牌到期时自动重试写操作；
若发生错误须先核对 checkpoint 和服务端实际结果。阶段复跑不会重复已记录的成功测量。

## 资源和失败恢复

新建专用 Knowledge Base 与 Agent。Tool 按既有注册键复用；只激活本次新建的 Tool，
不会启用用户已有的禁用 Tool。只为专用 Agent 分配它们；不改原 Agent。
按类别/集合分成26个小数据集，满足既有每次最多5题限制。原用户数据不被改写。
复跑先对照本地指纹、Workspace、题目、专用 Agent、文档集合及版本，变更就停。

`state.json` 是资源ID映射、逐题证据和测量 checkpoint。每次写 API 前保存
`pending_write`，包括付费search/answer请求，收到并持久化结果后清除；
响应丢失或进程中断时不自动重发。
由管理员对照其中操作路径检查服务端结果，补入正确资源映射或确认未写入后，
再清除标记继续。不要直接删标记或反复运行 POST。失败的 RAG 请求先诊断，不自动重试。
输出目录仅供本地使用，已忽略 Git；不含登录凭据，但答案和引用仍须受控。

如果已经诊断了模型契约问题，需要收齐本轮的**首次尝试**，可为 `agent` 或 `answers`
显式传入 `--continue-diagnosed-errors '诊断依据与继续原因'`。理由写入 checkpoint。
Agent 仅继续 `provider_contract` 类别；答案仅继续响应正文明确为
`Generation provider request failed` 的 HTTP 502。后者不暴露具体根因，不能把所有
502 都归为已诊断的引用缺陷。已失败和已成功的题目均不重试，原失败保留在分母；
其他错误、配置漂移或丢失响应仍停止。旧版未分类的失败须先核对并记录分类依据。
此选项用于测量已知不稳定配置的现状，不代表问题已修复或允许进入生产。

`summary.json` 为机器指标，`report.md` 为中文概览。署名复核后运行：

```powershell
& $benchmarkPython -m benchmarks.business_baseline.runner report `
  --output-dir benchmarks/business_baseline/output-live-v1
```

规格见 `docs/evaluation/business-baseline-spec.md`，业务试点设计见
`docs/evaluation/employee-service-pilot.md`。
