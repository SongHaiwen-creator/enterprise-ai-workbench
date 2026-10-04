"use client";

import { useEffect, useRef, useState } from "react";

import { AgentSummary, ApiError } from "@/utils/api";
import { EvaluationCaseSummary, EvaluationDataset } from "@/utils/evaluation";
import {
  activeRunCases, createEvaluationRun, EvaluationRun, getEvaluationRun, getRunCase,
  listEvaluationRuns, listRunCases, Rate, RunCase, RunCaseDetail,
} from "@/utils/evaluation-runs";
import { displayMessage, formatEnumLabel, formatTimestamp } from "@/utils/presentation";
import { RegisterBadCase } from "./bad-cases";

type Props = { workspaceId: string; accessToken: string; dataset: EvaluationDataset;
  agents: AgentSummary[]; onUnauthorized: () => void };

export function EvaluationRuns(props: Props) {
  return <WorkspaceRuns key={`${props.workspaceId}:${props.accessToken}:${props.dataset.id}:${props.dataset.updated_at}`} {...props} />;
}
function fraction(rate: Rate) {
  return rate.value === null ? "未评测" : `${(rate.value * 100).toFixed(1)}% (${rate.matched}/${rate.eligible})`;
}
function WorkspaceRuns({ workspaceId, accessToken, dataset, agents, onUnauthorized }: Props) {
  const [activeCases, setActiveCases] = useState<EvaluationCaseSummary[] | null>(null);
  const [agent, setAgent] = useState("");
  const [consent, setConsent] = useState(false);
  const [history, setHistory] = useState<EvaluationRun[]>([]);
  const [more, setMore] = useState(false);
  const [selected, setSelected] = useState<EvaluationRun | null>(null);
  const [cases, setCases] = useState<RunCase[]>([]);
  const [detail, setDetail] = useState<RunCaseDetail | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const live = useRef(true);
  const pending = useRef(false);
  const needsConsent = activeCases?.some(c => c.case_type !== "permission_boundary") ?? true;

  async function historyPage(offset = 0) {
    const response = await listEvaluationRuns(workspaceId, dataset.id, offset, accessToken);
    if (!live.current) return;
    setHistory(old => offset ? [...old, ...response.items] : response.items);
    setMore(response.items.length === 50);
  }
  async function refresh() {
    await Promise.all([historyPage(), activeRunCases(workspaceId, dataset.id, accessToken).then(items => {
      if (live.current) setActiveCases(items);
    })]);
  }
  function failure(reason: unknown, submission = false) {
    if (!live.current) return;
    if (reason instanceof ApiError && reason.status === 401) { onUnauthorized(); return; }
    setError(reason instanceof ApiError && !(submission && (reason.status === 0 || reason.status >= 500)) ? displayMessage(reason.message, reason.status) : submission
      ? "未收到评测响应，服务端可能已保存本次运行。请先刷新运行记录，再决定是否发起新评测。"
      : "评测运行暂不可用，请刷新后重试。");
  }
  async function operation(action: () => Promise<void>, submission = false) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try { await action(); } catch (reason) { failure(reason, submission); }
    finally { pending.current = false; if (live.current) setBusy(false); }
  }
  useEffect(() => {
    live.current = true; pending.current = true;
    void refresh().catch(failure).finally(() => { pending.current = false; if (live.current) setBusy(false); });
    return () => { live.current = false; };
    // Workspace/session/Dataset changes remount all confidential state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openRun(runId: string) {
    const [run, results] = await Promise.all([getEvaluationRun(workspaceId, runId, accessToken), listRunCases(workspaceId, runId, accessToken)]);
    if (!live.current) return;
    setSelected(run); setCases(results.items); setDetail(null);
  }
  const count = activeCases?.length;
  const canRun = !busy && dataset.status === "active" && count !== undefined && count >= 1 && count <= 5
    && agents.some(a => a.id === agent && a.status === "active") && (!needsConsent || consent);
  return <section className="evaluation-runs" aria-label="评测运行">
    <h3>评测运行</h3>
    <p>评测用于验证结构化行为。工具仅进行模拟验证，不调用真实执行服务或创建审批；权限结果来自共享策略的模拟验证。</p>
    <p>启用用例：{count ?? "加载中"} / 最多 5 条。用例按顺序运行，整次评测时限为 120 秒。</p>
    <fieldset className="evaluation-form" disabled={busy}>
      <legend>发起评测</legend>
      <label>评测智能体<select aria-label="评测智能体" value={agent} onChange={e => setAgent(e.target.value)}>
        <option value="">选择已启用的智能体</option>
        {agents.filter(a => a.status === "active").map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select></label>
      {needsConsent && <label className="evaluation-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />我已检查数据集、智能体能力范围及评测知识库，确认内容均为合成或脱敏数据，不含密钥及生产环境个人信息。我知悉测试输入、能力范围和检索证据可能发送至已配置的 OpenAI 服务。</label>}
      <button type="button" disabled={!canRun} onClick={() => void operation(async () => {
        const run = await createEvaluationRun(workspaceId, dataset.id, agent, consent, accessToken);
        if (!live.current) return;
        await Promise.all([openRun(run.id), refresh()]);
      }, true)} className="primary-button">运行评测</button>
    </fieldset>
    {busy && <p aria-live="polite">正在加载或运行评测…</p>}
    {error && <p role="alert">{error}</p>}
    <button type="button" disabled={busy} onClick={() => void operation(async () => {
      await refresh(); if (selected) await openRun(selected.id);
    })}>刷新运行记录</button>
    <ul>{history.map(run => <li key={run.id}><button type="button" disabled={busy} onClick={() => void operation(() => openRun(run.id))}>
      {run.agent_name} — {formatEnumLabel(run.status)} — {formatTimestamp(run.created_at)}
    </button></li>)}</ul>
    {more && <button disabled={busy} onClick={() => void operation(() => historyPage(history.length))}>加载更多运行记录</button>}
    {selected && <div>
      <h4>运行概览： {selected.dataset_name} / {selected.agent_name}</h4>
      <p>{formatEnumLabel(selected.status)}：通过 {selected.passed_cases}，未通过 {selected.failed_cases}，错误 {selected.error_cases}，待处理 {selected.pending_cases}</p>
      {selected.failure_category && <p>运行错误： {formatEnumLabel(selected.failure_category)}</p>}
      <p>通过率： {fraction(selected.metrics.overall_pass_rate)}. 评测覆盖率： {fraction(selected.metrics.evaluation_coverage)}. 错误率： {fraction(selected.metrics.error_rate)}.</p>
      <dl>{Object.entries(selected.metrics).filter(([key]) => !["category_pass_rate", "latency_ms", "overall_pass_rate", "evaluation_coverage", "error_rate"].includes(key))
        .map(([key, value]) => <div key={key}><dt>{formatEnumLabel(key)}</dt><dd>{fraction(value as Rate)}</dd></div>)}</dl>
      <h4>按类型查看结果</h4><ul>{Object.entries(selected.metrics.category_pass_rate).map(([key, value]) =>
        <li key={key}>{formatEnumLabel(key)}: {fraction(value)}</li>)}</ul>
      <p>耗时（毫秒），已记录尝试的用例（含错误）： {selected.metrics.latency_ms.count}; 其中错误尝试： {selected.metrics.latency_ms.error_count};
        最小 {selected.metrics.latency_ms.min ?? "未评测"}, 最大 {selected.metrics.latency_ms.max ?? "未评测"},
        平均 {selected.metrics.latency_ms.mean ?? "未评测"}, 中位数 {selected.metrics.latency_ms.median ?? "未评测"}.</p>
      <div className="evaluation-results"><table><thead><tr><th>用例</th><th>类型</th><th>结果</th><th>已记录运行尝试</th><th>耗时（毫秒）</th><th>错误</th></tr></thead>
        <tbody>{cases.map(row => <tr key={row.id}><td><button disabled={busy} onClick={() => void operation(async () => {
          const value = await getRunCase(workspaceId, selected.id, row.id, accessToken); if (live.current) setDetail(value);
        })}>{row.name}</button></td><td>{formatEnumLabel(row.case_type)}</td><td>{formatEnumLabel(row.result ?? "pending")}</td>
          <td>{row.attempted ? "是" : "未记录"}</td><td>{row.latency_ms ?? "无运行记录"}</td><td>{row.error_category ? formatEnumLabel(row.error_category) : "—"}</td></tr>)}</tbody>
      </table></div>
    </div>}
    {detail && <article aria-label="预期与实际结果">
      <h4>{detail.name}：预期与实际结果</h4>
      {detail.case_type === "tool_calling" && <p>工具评测仅进行模拟验证。“可执行”表示符合正常操作条件，本次评测不会实际执行工具。</p>}
      {detail.case_type === "permission_boundary" && <p>此结果来自共享权限策略的模拟验证，未创建真实用户身份。</p>}
      <p>本次测试输入：</p><pre>{detail.test_input_snapshot}</pre>
      <p>预期结果：</p><pre>{JSON.stringify(detail.expected_behavior_snapshot, null, 2)}</pre>
      <p>实际结果：</p><pre>{JSON.stringify(detail.actual_behavior, null, 2)}</pre>
      <p>未通过的检查： {Object.entries(detail.comparison_checks ?? {}).filter(([, matched]) => !matched).map(([key]) => formatEnumLabel(key)).join(", ") || "无"}</p>
      <RegisterBadCase workspaceId={workspaceId} accessToken={accessToken} onUnauthorized={onUnauthorized} source={detail} runTerminal={selected?.status === "completed" || selected?.status === "failed"} />
    </article>}
  </section>;
}
