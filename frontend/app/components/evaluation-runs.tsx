"use client";

import { useEffect, useRef, useState } from "react";

import { AgentSummary, ApiError } from "@/utils/api";
import { EvaluationCaseSummary, EvaluationDataset } from "@/utils/evaluation";
import {
  activeRunCases, createEvaluationRun, EvaluationRun, getEvaluationRun, getRunCase,
  listEvaluationRuns, listRunCases, Rate, RunCase, RunCaseDetail,
} from "@/utils/evaluation-runs";
import { formatEnumLabel } from "@/utils/presentation";

type Props = { workspaceId: string; accessToken: string; dataset: EvaluationDataset;
  agents: AgentSummary[]; onUnauthorized: () => void };

export function EvaluationRuns(props: Props) {
  return <WorkspaceRuns key={`${props.workspaceId}:${props.accessToken}:${props.dataset.id}:${props.dataset.updated_at}`} {...props} />;
}
function fraction(rate: Rate) {
  return rate.value === null ? "Not evaluated" : `${(rate.value * 100).toFixed(1)}% (${rate.matched}/${rate.eligible})`;
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
    setError(reason instanceof ApiError && !(submission && (reason.status === 0 || reason.status >= 500)) ? reason.message : submission
      ? "Run response unavailable. Refresh run history before starting another run; the server may have saved it."
      : "Evaluation runs unavailable. Refresh to try again.");
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
  return <section aria-label="Evaluation runs">
    <h3>Evaluation runs</h3>
    <p>Runs evaluate structured behavior. Tool outcomes are dry runs; no Tool adapters or Approvals are invoked. Permission results simulate the shared policy.</p>
    <p>Active cases: {count ?? "Loading"} / maximum 5. Execution is sequential, with a 120-second run budget.</p>
    <fieldset disabled={busy}>
      <legend>Run evaluation</legend>
      <label>Evaluation Agent<select aria-label="Evaluation Agent" value={agent} onChange={e => setAgent(e.target.value)}>
        <option value="">Select an active Agent</option>
        {agents.filter(a => a.status === "active").map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select></label>
      {needsConsent && <label><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />
        I reviewed the Dataset, Agent scope and evaluation knowledge bases: all content is synthetic or redacted. I acknowledge that inputs, scope and retrieved evidence may be sent to the configured OpenAI provider. No secrets or production personal data.
      </label>}
      <button type="button" disabled={!canRun} onClick={() => void operation(async () => {
        const run = await createEvaluationRun(workspaceId, dataset.id, agent, consent, accessToken);
        if (!live.current) return;
        await Promise.all([openRun(run.id), refresh()]);
      }, true)}>Run Evaluation</button>
    </fieldset>
    {busy && <p aria-live="polite">Loading or running evaluation…</p>}
    {error && <p role="alert">{error}</p>}
    <button type="button" disabled={busy} onClick={() => void operation(async () => {
      await refresh(); if (selected) await openRun(selected.id);
    })}>Refresh run history</button>
    <ul>{history.map(run => <li key={run.id}><button type="button" disabled={busy} onClick={() => void operation(() => openRun(run.id))}>
      {run.agent_name} — {run.status} — {new Date(run.created_at).toLocaleString()}
    </button></li>)}</ul>
    {more && <button disabled={busy} onClick={() => void operation(() => historyPage(history.length))}>More runs</button>}
    {selected && <div>
      <h4>Run summary: {selected.dataset_name} / {selected.agent_name}</h4>
      <p>{selected.status}: Passed {selected.passed_cases}, Failed {selected.failed_cases}, Error {selected.error_cases}, Pending {selected.pending_cases}</p>
      {selected.failure_category && <p>Run error: {formatEnumLabel(selected.failure_category)}</p>}
      <p>Pass rate: {fraction(selected.metrics.overall_pass_rate)}. Evaluation coverage: {fraction(selected.metrics.evaluation_coverage)}. Error rate: {fraction(selected.metrics.error_rate)}.</p>
      <dl>{Object.entries(selected.metrics).filter(([key]) => !["category_pass_rate", "latency_ms", "overall_pass_rate", "evaluation_coverage", "error_rate"].includes(key))
        .map(([key, value]) => <div key={key}><dt>{formatEnumLabel(key)}</dt><dd>{fraction(value as Rate)}</dd></div>)}</dl>
      <h4>Category breakdown</h4><ul>{Object.entries(selected.metrics.category_pass_rate).map(([key, value]) =>
        <li key={key}>{formatEnumLabel(key)}: {fraction(value)}</li>)}</ul>
      <p>Latency (ms), attempted cases including errors: {selected.metrics.latency_ms.count}; errors attempted: {selected.metrics.latency_ms.error_count};
        min {selected.metrics.latency_ms.min ?? "Not evaluated"}, max {selected.metrics.latency_ms.max ?? "Not evaluated"},
        mean {selected.metrics.latency_ms.mean ?? "Not evaluated"}, median {selected.metrics.latency_ms.median ?? "Not evaluated"}.</p>
      <table><thead><tr><th>Case</th><th>Category</th><th>Result</th><th>Measured attempt recorded</th><th>Latency (ms)</th><th>Error</th></tr></thead>
        <tbody>{cases.map(row => <tr key={row.id}><td><button disabled={busy} onClick={() => void operation(async () => {
          const value = await getRunCase(workspaceId, selected.id, row.id, accessToken); if (live.current) setDetail(value);
        })}>{row.name}</button></td><td>{formatEnumLabel(row.case_type)}</td><td>{row.result ?? "pending"}</td>
          <td>{row.attempted ? "Yes" : "Not recorded"}</td><td>{row.latency_ms ?? "No recorded attempt"}</td><td>{row.error_category ?? "—"}</td></tr>)}</tbody>
      </table>
    </div>}
    {detail && <article aria-label="Expected versus Actual">
      <h4>{detail.name}: Expected vs Actual</h4>
      {detail.case_type === "tool_calling" && <p>Dry run only. Would execute means eligibility for the normal product path; nothing executed here.</p>}
      {detail.case_type === "permission_boundary" && <p>Shared authorization policy simulation; no runtime identity was created.</p>}
      <p>Captured test input:</p><pre>{detail.test_input_snapshot}</pre>
      <p>Expected:</p><pre>{JSON.stringify(detail.expected_behavior_snapshot, null, 2)}</pre>
      <p>Actual:</p><pre>{JSON.stringify(detail.actual_behavior, null, 2)}</pre>
      <p>Failed checks: {Object.entries(detail.comparison_checks ?? {}).filter(([, matched]) => !matched).map(([key]) => formatEnumLabel(key)).join(", ") || "None"}</p>
    </article>}
  </section>;
}
