# 员工服务业务基准 v1

记录日期：2026-10-05（Asia/Shanghai）。本报告仅执行了24题离线策略模拟。
正常产品登录凭据缺失，RAG检索、真实回答与Agent运行未执行；108题尚未导入运行库。

数据：原创合成制度与任务；标准答案待业务负责人复核。
结果仅代表本基准，不能推断真实业务准确率或节省工时。

| 分组 | 类别 | 通过 / 未通过 / 错误 / 待评测 | 非错误通过率 | 通过/计划 |
|---|---|---|---|---|---|
| development | knowledge_qa | 0 / 0 / 0 / 32 | 未测 | 0.0% (0/32) |
| development | permission_boundary | 18 / 0 / 0 / 0 | 100.0% (18/18) | 100.0% (18/18) |
| development | refusal_behavior | 0 / 0 / 0 / 8 | 未测 | 0.0% (0/8) |
| development | tool_calling | 0 / 0 / 0 / 16 | 未测 | 0.0% (0/16) |
| holdout | knowledge_qa | 0 / 0 / 0 / 16 | 未测 | 0.0% (0/16) |
| holdout | permission_boundary | 6 / 0 / 0 / 0 | 100.0% (6/6) | 100.0% (6/6) |
| holdout | refusal_behavior | 0 / 0 / 0 / 4 | 未测 | 0.0% (0/4) |
| holdout | tool_calling | 0 / 0 / 0 / 8 | 未测 | 0.0% (0/8) |

development 检索 Recall@5：未评测；成功问题 0/32。失败和未测按未命中计；未测不能作为召回质量结论。

holdout 检索 Recall@5：未评测；成功问题 0/16。失败和未测按未命中计；未测不能作为召回质量结论。

答案正确性需有署名复核；未复核不计正确。工具结果为 dry run，权限结果为策略模拟。

机器可读指标见 [policy summary](business-baseline-v1-policy-summary.json)。
本地逐题证据位于 `benchmarks/business_baseline/output-policy-v1/state.json`（不提交Git）。
正常登录后复跑步骤见 [runner README](../../benchmarks/business_baseline/README.md)。
