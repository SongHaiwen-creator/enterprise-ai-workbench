"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "@/utils/api";
import {
  CaseCreate, EvaluationCase, EvaluationCaseSummary, EvaluationCaseType, EvaluationDataset,
  EvaluationExpectation, EvaluationStatus, PermissionExpectation,
  createEvaluationCase, createEvaluationDataset, evaluationResources, getEvaluationCase,
  listEvaluationCases, listEvaluationDatasets, updateEvaluationCase, updateEvaluationDataset,
} from "@/utils/evaluation";
import { displayMessage, formatEnumLabel } from "@/utils/presentation";
import { EvaluationRuns } from "./evaluation-runs";

const CATEGORIES: EvaluationCaseType[] = ["knowledge_qa", "tool_calling", "permission_boundary", "refusal_behavior"];
type Resources = Awaited<ReturnType<typeof evaluationResources>>;
type Props = { workspaceId: string; workspaceName: string; accessToken: string; onUnauthorized: () => void };

function defaultExpectation(category: EvaluationCaseType): EvaluationExpectation {
  switch (category) {
    case "knowledge_qa": return { routing_intent: "knowledge_qa", answer_status: "answered", citation_requirement: "present" };
    case "tool_calling": return { routing_intent: "tool_request", outcome: "not_executed", tool_key: null, approval_required: false, non_execution_reason: "no_available_tool" };
    case "permission_boundary": return { actor_role: "employee", actor_membership_status: "active", target_context: "other_workspace", operation: "agent_route", expected_http_status: 404, result_category: "not_found", access_denied: true };
    case "refusal_behavior": return { routing_intent: "unsupported", response_category: "unsupported_request", safe_response_required: true };
  }
}

function Choice({ label, value, options, onChange, required = false }: {
  label: string; value: string; options: { value: string; label: string }[];
  onChange: (value: string) => void; required?: boolean;
}) {
  return <label>{label}<select aria-label={label} value={value} required={required} onChange={event => onChange(event.target.value)}>
    {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
  </select></label>;
}
const choices = (values: string[]) => values.map(value => ({ value, label: formatEnumLabel(value) }));

function DatasetEditor({ dataset, busy, onSave }: {
  dataset: EvaluationDataset | null; busy: boolean;
  onSave: (name: string, description: string | null, status: EvaluationStatus) => void;
}) {
  const [name, setName] = useState(dataset?.name ?? "");
  const [description, setDescription] = useState(dataset?.description ?? "");
  const [status, setStatus] = useState<EvaluationStatus>(dataset?.status ?? "active");
  return <form onSubmit={event => { event.preventDefault(); onSave(name.trim(), description.trim() || null, status); }}>
    <fieldset disabled={busy} className="evaluation-form">
      <legend>{dataset ? "编辑数据集" : "创建数据集"}</legend>
      <label>数据集名称<input aria-label="数据集名称" required maxLength={255} value={name} onChange={e => setName(e.target.value)} /></label>
      <label>数据集描述<textarea aria-label="数据集描述" maxLength={5000} value={description} onChange={e => setDescription(e.target.value)} /></label>
      {dataset && <Choice label="数据集状态" value={status} options={choices(["active", "disabled"])} onChange={value => setStatus(value as EvaluationStatus)} />}
      <button type="submit" disabled={!name.trim()}>{dataset ? "保存数据集" : "创建数据集"}</button>
    </fieldset>
  </form>;
}

function CaseEditor({ item, dataset, resources, busy, onSave, onCancel }: {
  item: EvaluationCase | null; dataset: EvaluationDataset; resources: Resources;
  busy: boolean; onSave: (payload: CaseCreate, status: EvaluationStatus) => void; onCancel: () => void;
}) {
  const [category, setCategory] = useState<EvaluationCaseType>(item?.case_type ?? "knowledge_qa");
  const [name, setName] = useState(item?.name ?? "");
  const [description, setDescription] = useState(item?.description ?? "");
  const [input, setInput] = useState(item?.test_input ?? "");
  const [status, setStatus] = useState<EvaluationStatus>(item?.status ?? "active");
  const [expected, setExpected] = useState<EvaluationExpectation>(item?.expected_behavior ?? defaultExpectation("knowledge_qa"));
  const [agentId, setAgent] = useState(item?.agent_id ?? "");
  const [kbId, setKB] = useState(item?.knowledge_base_id ?? "");
  const [toolId, setTool] = useState(item?.tool_id ?? "");
  const permission = "actor_role" in expected ? expected : null;
  const knowledge = "answer_status" in expected ? expected : null;
  const tool = "outcome" in expected ? expected : null;
  const refusal = "safe_response_required" in expected ? expected : null;
  const agentAllowed = !permission || (permission.target_context === "same_workspace" && ["agent_route", "agent_configuration_read"].includes(permission.operation));
  const kbAllowed = !!knowledge || refusal?.routing_intent === "knowledge_qa" || (permission?.target_context === "same_workspace" && permission.operation === "knowledge_answer");
  const toolAllowed = !!tool && tool.outcome !== "not_executed" || (permission?.target_context === "same_workspace" && permission.operation === "tool_configuration_read");
  const resourceOptions = (rows: { id: string; name: string; status: string }[]) => [
    { value: "", label: "无" }, ...rows.map(row => ({ value: row.id, label: `${row.name} （${formatEnumLabel(row.status)}）` })),
  ];
  function changeCategory(value: EvaluationCaseType) {
    setCategory(value); setExpected(defaultExpectation(value)); setAgent(""); setKB(""); setTool("");
  }
  function changePermission(next: PermissionExpectation) {
    setExpected(next); setAgent(""); setKB(""); setTool("");
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    onSave({ case_type: category, name: name.trim(), description: description.trim() || null,
      test_input: input.trim(), expected_behavior: expected,
      agent_id: agentAllowed ? agentId || null : null,
      knowledge_base_id: kbAllowed ? kbId || null : null,
      tool_id: toolAllowed ? toolId || null : null }, status);
  }
  return <form onSubmit={submit}>
    <fieldset disabled={busy || (!item && dataset.status === "disabled")} className="evaluation-form">
      <legend>{item ? "编辑用例" : "创建用例"}</legend>
      <p>仅使用合成或脱敏的测试内容。停用后内容仍会保留。</p>
      {item ? <p>用例类型：{formatEnumLabel(category)}</p> : <Choice label="用例类型" value={category} options={choices(CATEGORIES)} onChange={value => changeCategory(value as EvaluationCaseType)} />}
      <label>用例名称<input aria-label="用例名称" required maxLength={255} value={name} onChange={e => setName(e.target.value)} /></label>
      <label>用例描述<textarea aria-label="用例描述" maxLength={5000} value={description} onChange={e => setDescription(e.target.value)} /></label>
      <label>测试输入<textarea aria-label="测试输入" required maxLength={2000} value={input} onChange={e => setInput(e.target.value)} /></label>
      {knowledge && <Choice label="预期回答状态" value={knowledge.answer_status} options={choices(["answered", "unsupported"])} onChange={value => setExpected({ ...knowledge, answer_status: value as "answered" | "unsupported", citation_requirement: value === "answered" ? "present" : "none" })} />}
      {knowledge && <p>引用要求：{formatEnumLabel(knowledge.citation_requirement)}</p>}
      {tool && <>
        <Choice label="预期工具结果" value={tool.outcome} options={choices(["executed", "approval_required", "not_executed"])} onChange={value => {
          setTool(""); setExpected({ ...tool, outcome: value as typeof tool.outcome, tool_key: null,
            approval_required: value === "approval_required", non_execution_reason: value === "not_executed" ? "no_available_tool" : null });
        }} />
        <p>需要审批： {tool.approval_required ? "是" : "否"}</p>
        {tool.outcome === "not_executed" && <Choice label="未执行原因" value={tool.non_execution_reason ?? "no_available_tool"} options={choices(["no_available_tool", "no_matching_tool", "missing_required_arguments"])} onChange={value => setExpected({ ...tool, non_execution_reason: value as typeof tool.non_execution_reason })} />}
      </>}
      {permission && <>
        <Choice label="测试角色" value={permission.actor_role} options={choices(["employee", "knowledge_admin", "agent_admin", "system_admin"])} onChange={value => setExpected({ ...permission, actor_role: value as typeof permission.actor_role })} />
        <Choice label="测试成员状态" value={permission.actor_membership_status} options={choices(["active", "invited", "disabled", "absent"])} onChange={value => setExpected({ ...permission, actor_membership_status: value as typeof permission.actor_membership_status })} />
        <Choice label="目标空间" value={permission.target_context} options={choices(["same_workspace", "other_workspace", "nonexistent"])} onChange={value => changePermission({ ...permission, target_context: value as typeof permission.target_context })} />
        <Choice label="目标操作" value={permission.operation} options={choices(["agent_route", "knowledge_answer", "agent_configuration_read", "tool_configuration_read", "evaluation_dataset_read"])} onChange={value => changePermission({ ...permission, operation: value as typeof permission.operation })} />
        <Choice label="预期拒绝状态" value={String(permission.expected_http_status)} options={[{ value: "403", label: "403 无访问权限" }, { value: "404", label: "404 资源不存在" }]} onChange={value => setExpected({ ...permission, expected_http_status: value === "403" ? 403 : 404, result_category: value === "403" ? "forbidden" : "not_found" })} />
        <p>测试角色与目标空间仅为合成测试标签，预期结果为拒绝访问。</p>
      </>}
      {refusal && <>
        <Choice label="预期拒绝类型" value={refusal.routing_intent} options={choices(["unsupported", "knowledge_qa"])} onChange={value => { setKB(""); setExpected({ ...refusal, routing_intent: value as typeof refusal.routing_intent, response_category: value === "unsupported" ? "unsupported_request" : "knowledge_unsupported" }); }} />
        <p>预期返回结构化拒绝响应；此处不进行语义安全评分。</p>
      </>}
      {agentAllowed && <Choice label="关联智能体" value={agentId} options={resourceOptions(resources.agents)} onChange={setAgent} />}
      {kbAllowed && <Choice label="关联知识库" value={kbId} required={!!knowledge || refusal?.routing_intent === "knowledge_qa"} options={resourceOptions(resources.knowledgeBases)} onChange={setKB} />}
      {toolAllowed && <Choice label="关联工具" value={toolId} required={!!tool} options={resourceOptions(resources.tools.filter(row => !tool || (tool.outcome === "approval_required" ? row.tool_key === "create_it_access_request" : row.tool_key !== "create_it_access_request")))} onChange={value => {
        setTool(value);
        if (tool) setExpected({ ...tool, tool_key: resources.tools.find(row => row.id === value)?.tool_key ?? null });
      }} />}
      {item && <Choice label="用例状态" value={status} options={choices(["active", "disabled"])} onChange={value => setStatus(value as EvaluationStatus)} />}
      <div><button type="submit" disabled={!name.trim() || !input.trim()}>{item ? "保存用例" : "创建用例"}</button> <button type="button" onClick={onCancel}>取消编辑</button></div>
    </fieldset>
  </form>;
}

export function EvaluationDatasets(props: Props) {
  // Remount all content and invalidate requests when Workspace or session changes.
  return <WorkspaceDatasets key={`${props.workspaceId}:${props.accessToken}`} {...props} />;
}

function WorkspaceDatasets({ workspaceId, workspaceName, accessToken, onUnauthorized }: Props) {
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [dataset, setDataset] = useState<EvaluationDataset | null>(null);
  const [cases, setCases] = useState<EvaluationCaseSummary[]>([]);
  const [detail, setDetail] = useState<EvaluationCase | null>(null);
  const [editingCase, setEditingCase] = useState(false);
  const [resources, setResources] = useState<Resources>({ agents: [], knowledgeBases: [], tools: [] });
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [moreDatasets, setMoreDatasets] = useState(false);
  const [moreCases, setMoreCases] = useState(false);
  const live = useRef(true);
  const pending = useRef(false);

  function failure(reason: unknown) {
    if (!live.current) return;
    if (reason instanceof ApiError && reason.status === 401) { onUnauthorized(); return; }
    setError(reason instanceof ApiError ? `${reason.status === 403 ? "访问权限不足：" : ""}${displayMessage(reason.message, reason.status)}` : "评测数据暂不可用，请稍后重试。");
  }
  async function run(operation: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try { await operation(); } catch (reason) { failure(reason); }
    finally { pending.current = false; if (live.current) setBusy(false); }
  }
  async function reloadDatasets(offset = 0) {
    const response = await listEvaluationDatasets(workspaceId, offset, accessToken);
    if (!live.current) return;
    setDatasets(previous => offset ? [...previous, ...response.items] : response.items);
    setMoreDatasets(response.items.length === 50);
  }
  async function reloadCases(selected: EvaluationDataset, offset = 0) {
    const response = await listEvaluationCases(workspaceId, selected.id, offset, accessToken);
    if (!live.current) return;
    setCases(previous => offset ? [...previous, ...response.items] : response.items);
    setMoreCases(response.items.length === 50);
  }
  async function initialize() {
    await Promise.all([reloadDatasets(), evaluationResources(workspaceId, accessToken).then(value => {
      if (live.current) setResources(value);
    })]);
  }
  useEffect(() => {
    live.current = true;
    pending.current = true;
    void initialize().catch(failure).finally(() => {
      pending.current = false;
      if (live.current) setBusy(false);
    });
    return () => { live.current = false; };
    // Workspace/session changes create a fresh component and state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <section className="qa-context-card" aria-label="评测数据集">
    <h2>评测数据集</h2>
    <p>管理 {workspaceName} 中可重复使用的测试定义，选择已启用的数据集发起评测。</p>
    <p className="muted">仅使用合成或脱敏内容。停用的数据集与用例仍会保留内容。</p>
    {busy && <p role="status">正在加载评测数据…</p>}
    {error && <div role="alert">{error} <button type="button" disabled={busy} onClick={() => void run(async () => { await initialize(); if (dataset) await reloadCases(dataset); })}>重试</button></div>}
    <div className="evaluation-columns">
      <div>
        <h3>数据集</h3>
        {!busy && !datasets.length && <p>暂无评测数据集。</p>}
        <ul>{datasets.map(row => <li key={row.id}><button disabled={busy} type="button" onClick={() => {
          setDataset(row); setCases([]); setDetail(null); setEditingCase(false); setMoreCases(false);
          void run(() => reloadCases(row));
        }}>{row.name} （{formatEnumLabel(row.status)}）</button></li>)}</ul>
        {moreDatasets && <button disabled={busy} onClick={() => void run(() => reloadDatasets(datasets.length))}>加载更多数据集</button>}
        <button type="button" disabled={busy} onClick={() => { setDataset(null); setCases([]); setDetail(null); setEditingCase(false); }}>新建数据集</button>
        <DatasetEditor key={dataset ? `${dataset.id}:${dataset.updated_at}` : "new"} dataset={dataset} busy={busy} onSave={(name, description, status) => void run(async () => {
          const result = dataset ? await updateEvaluationDataset(workspaceId, dataset.id, { name, description, status }, accessToken) : await createEvaluationDataset(workspaceId, { name, description }, accessToken);
          if (!live.current) return;
          setDataset(result); setDetail(null); setEditingCase(false);
          await Promise.all([reloadDatasets(), reloadCases(result)]);
        })} />
      </div>
      {dataset && <div>
        <EvaluationRuns key={`${dataset.id}:${cases.map(c => `${c.id}:${c.updated_at}`).join(",")}`} workspaceId={workspaceId} accessToken={accessToken} dataset={dataset} agents={resources.agents} onUnauthorized={onUnauthorized} />
        <h3>{dataset.name} 的用例</h3><p>{dataset.description}</p>
        {dataset.status === "disabled" && <p>数据集已停用。重新启用后可创建用例；已有用例仍可编辑。</p>}
        {!busy && !cases.length && <p>暂无评测用例。</p>}
        <ul>{cases.map(row => <li key={row.id}><button type="button" disabled={busy} onClick={() => {
          setDetail(null); setEditingCase(false);
          void run(async () => { const item = await getEvaluationCase(workspaceId, dataset.id, row.id, accessToken); if (live.current) { setDetail(item); setEditingCase(true); } });
        }}>{row.name} — {formatEnumLabel(row.case_type)} （{formatEnumLabel(row.status)}）</button></li>)}</ul>
        {moreCases && <button disabled={busy} onClick={() => void run(() => reloadCases(dataset, cases.length))}>加载更多用例</button>}
        <button type="button" disabled={busy || dataset.status === "disabled"} onClick={() => { setDetail(null); setEditingCase(true); }}>新建用例</button>
        {editingCase && <CaseEditor key={detail ? `${detail.id}:${detail.updated_at}` : `new:${dataset.id}`} item={detail} dataset={dataset} resources={resources} busy={busy} onCancel={() => { setDetail(null); setEditingCase(false); }} onSave={(payload, status) => void run(async () => {
          if (detail) {
            const { case_type: _category, ...update } = payload;
            void _category;
            const result = await updateEvaluationCase(workspaceId, dataset.id, detail.id, { ...update, status }, accessToken);
            if (live.current) setDetail(result);
          } else {
            await createEvaluationCase(workspaceId, dataset.id, payload, accessToken);
            if (live.current) setEditingCase(false);
          }
          await reloadCases(dataset);
        })} />}
      </div>}
    </div>
  </section>;
}
