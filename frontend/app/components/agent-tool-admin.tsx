"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, type AgentSummary, type MembershipRole, listAgents } from "@/utils/api";
import {
  type AgentConfiguration, type AgentCreate, type AgentUpdate, type ToolConfiguration,
  type ToolCreate, type ToolUpdate, TOOL_HELP, assignTool, createAgent, createTool,
  getAgent, getTool, isToolKey, listAgentTools, listManagedAgents, listTools, toolHelp,
  unassignTool, updateAgent, updateTool, usableConfiguration,
} from "@/utils/agent-tool-admin";
import { displayMessage, formatEnumLabel, formatTimestamp } from "@/utils/presentation";

type Props = {
  workspaceId: string; accessToken: string; role: MembershipRole;
  onUnauthorized: () => void; onPendingChange: (pending: boolean) => void;
  onAgentsChange: (items: AgentSummary[] | null) => void;
};
type Tab = "agent" | "tool";
const length = (value: string) => Array.from(value).length;

function AgentEditor({ agent, busy, onDirty, onSave }: {
  agent: AgentConfiguration | null; busy: boolean; onDirty: (value: boolean) => void;
  onSave: (payload: AgentUpdate) => void;
}) {
  const [name, setName] = useState(agent?.name ?? "");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [prompt, setPrompt] = useState(agent?.system_prompt ?? "");
  const [error, setError] = useState("");
  function dirty(n: string, d: string, p: string) {
    onDirty(n !== (agent?.name ?? "") || d !== (agent?.description ?? "") || p !== (agent?.system_prompt ?? ""));
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    const n = name.trim(), d = description.trim() || null, p = prompt.trim();
    if (!n || length(n) > 255 || length(d ?? "") > 5000 || !p || length(p) > 8000) {
      setError("名称须为 1–255 字符，描述最多 5000 字符，系统提示词须为 1–8000 字符。"); return;
    }
    setError("");
    const payload: AgentUpdate = {};
    if (!agent || n !== agent.name) payload.name = n;
    if (!agent || d !== agent.description) payload.description = d;
    if (!agent || p !== agent.system_prompt) payload.system_prompt = p;
    onSave(payload);
  }
  return <form className="knowledge-form" onSubmit={submit}>
    <fieldset disabled={busy}><legend>{agent ? "编辑 Agent" : "创建 Agent"}</legend>
      <label>Agent 名称<input required value={name} onChange={e => { setName(e.target.value); dirty(e.target.value, description, prompt); }} /></label>
      <label>Agent 描述<textarea rows={2} value={description} onChange={e => { setDescription(e.target.value); dirty(name, e.target.value, prompt); }} /></label>
      <label>系统提示词<textarea required rows={5} value={prompt} onChange={e => { setPrompt(e.target.value); dirty(name, description, e.target.value); }} /></label>
      <p className="muted">提示词控制路由范围和工具选择，不改变知识答案的生成提示。不要填写密钥、凭据或敏感业务记录；保存不调用模型，之后使用 Agent 时会按现有规则发送至已配置模型服务。</p>
      {error && <p role="alert">{error}</p>}
      <button className="primary-button" type="submit">{agent ? "保存 Agent" : "创建 Agent"}</button>
    </fieldset>
  </form>;
}

function CapabilityHelp({ toolKey }: { toolKey: string }) {
  const help = toolHelp(toolKey);
  return <section className="capability-help" aria-label="能力限制">
    <h3>能力限制（只读）</h3>
    {help ? <><p><strong>{help.label}</strong> · <code>{help.tool_key}</code></p>
      <ul>{help.restrictions.map(text => <li key={text}>{text}</li>)}</ul></>
      : <p role="alert">该能力的说明不可用，请联系管理员；不能在此新增或执行能力。</p>}
  </section>;
}

function ToolEditor({ tool, tools, busy, onDirty, onSave }: {
  tool: ToolConfiguration | null; tools: ToolConfiguration[]; busy: boolean;
  onDirty: (value: boolean) => void; onSave: (payload: ToolCreate | ToolUpdate) => void;
}) {
  const available = TOOL_HELP.filter(help => !tools.some(item => item.tool_key === help.tool_key));
  const [key, setKey] = useState(tool?.tool_key ?? available[0]?.tool_key ?? "");
  const [name, setName] = useState(tool?.name ?? "");
  const [description, setDescription] = useState(tool?.description ?? "");
  const [error, setError] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    const n = name.trim(), d = description.trim();
    if (!n || length(n) > 255 || !d || length(d) > 5000 || !isToolKey(key)) {
      setError("请选择注册能力，名称须为 1–255 字符，说明须为 1–5000 字符。"); return;
    }
    setError("");
    if (!tool) onSave({ tool_key: key, name: n, description: d });
    else {
      const payload: ToolUpdate = {};
      if (n !== tool.name) payload.name = n;
      if (d !== tool.description) payload.description = d;
      onSave(payload);
    }
  }
  function dirty(n: string, d: string) { onDirty(n !== (tool?.name ?? "") || d !== (tool?.description ?? "")); }
  return <>
    <form className="knowledge-form" onSubmit={submit}>
      <fieldset disabled={busy || (!tool && !available.length)}><legend>{tool ? "编辑工具" : "创建工具"}</legend>
        {!tool && <label>注册能力<select value={key} onChange={e => { setKey(e.target.value); onDirty(true); }}>
          {available.map(help => <option value={help.tool_key} key={help.tool_key}>{help.label}</option>)}
        </select></label>}
        <label>工具名称<input required value={name} onChange={e => { setName(e.target.value); dirty(e.target.value, description); }} /></label>
        <label>工具说明<textarea required rows={3} value={description} onChange={e => { setDescription(e.target.value); dirty(name, e.target.value); }} /></label>
        <p className="muted">名称与说明仅用于显示，不改变模型选工具时的指令。新工具默认禁用，需显式启用及分配。</p>
        {error && <p role="alert">{error}</p>}
        <button className="primary-button" type="submit">{tool ? "保存工具" : "创建工具"}</button>
      </fieldset>
    </form>
    <CapabilityHelp toolKey={key} />
  </>;
}

export function AgentToolAdmin(props: Props) {
  if (props.role !== "agent_admin" && props.role !== "system_admin") return <p role="alert">Agent 与工具管理需要当前工作空间的 Agent 管理员或系统管理员权限。</p>;
  return <WorkspaceAgentToolAdmin key={`${props.workspaceId}:${props.accessToken}:${props.role}`} {...props} />;
}

function WorkspaceAgentToolAdmin({ workspaceId, accessToken, onUnauthorized, onPendingChange, onAgentsChange }: Props) {
  const [tab, setTab] = useState<Tab>("agent");
  const [agents, setAgents] = useState<AgentSummary[]>([]), [tools, setTools] = useState<ToolConfiguration[]>([]);
  const [agent, setAgent] = useState<AgentConfiguration | null>(null), [tool, setTool] = useState<ToolConfiguration | null>(null);
  const [assigned, setAssigned] = useState<ToolConfiguration[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false), [editorEpoch, setEditorEpoch] = useState(0);
  const [loading, setLoading] = useState(true), [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false), [blocked, setBlocked] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false), [listsReady, setListsReady] = useState(false);
  const [error, setError] = useState(""), [message, setMessage] = useState("");
  const [confirmation, setConfirmation] = useState<{ text: string; action: () => void } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null), confirmTrigger = useRef<HTMLElement | null>(null);
  const live = useRef(false), pending = useRef(false), dirty = useRef(false), denied = useRef(false);
  const listsRequest = useRef(0), detailRequest = useRef(0), sharedRequest = useRef(0);
  const locked = busy || blocked || needsRefresh || loading || !listsReady;
  function invalidate() { listsRequest.current++; detailRequest.current++; sharedRequest.current++; }
  function clearDetail() {
    detailRequest.current++; dirty.current = false;
    setAgent(null); setTool(null); setAssigned(null); setSelectedId(null); setCreating(false);
    setDetailLoading(false); setEditorEpoch(n => n + 1); setConfirmation(null);
  }
  function failure(reason: unknown, mutation = false) {
    if (!live.current) return;
    const status = reason instanceof ApiError ? reason.status : 0;
    if (status === 401 || status === 403) {
      denied.current = true; invalidate(); clearDetail(); setAgents([]); setTools([]);
      setListsReady(false); setBlocked(true); setMessage(""); onAgentsChange(null);
      if (status === 401) { onUnauthorized(); return; }
      setError("你没有管理当前工作空间 Agent 与工具的权限，请联系管理员。"); return;
    }
    if (status === 503) setNeedsRefresh(true);
    const uncertain = mutation && (status === 0 || status >= 500);
    if (uncertain) setNeedsRefresh(true);
    setError(status === 503 ? "工具注册配置不可用，请联系管理员核对。写入结果可能未确认，不要重复提交。"
      : uncertain ? "操作结果未确认，服务端可能已完成。请先刷新核对；再次创建 Agent 可能产生重复记录。"
        : reason instanceof ApiError ? displayMessage(reason.message, status) : "暂时无法读取配置，请手动刷新。");
  }

  async function openDetail(nextTab: Tab, id: string) {
    const sequence = ++detailRequest.current;
    dirty.current = false; setCreating(false); setSelectedId(id); setAgent(null); setTool(null);
    setAssigned(null); setDetailLoading(true); setEditorEpoch(n => n + 1);
    try {
      if (nextTab === "agent") {
        const [fresh, assignments] = await Promise.all([
          getAgent(workspaceId, id, accessToken), listAgentTools(workspaceId, id, accessToken),
        ]);
        if (!live.current || sequence !== detailRequest.current) return;
        setAgent(fresh); setAssigned(assignments);
      } else {
        const fresh = await getTool(workspaceId, id, accessToken);
        if (!live.current || sequence !== detailRequest.current) return;
        setTool(fresh);
      }
    } catch (reason) {
      if (!live.current || sequence !== detailRequest.current) return;
      if (reason instanceof ApiError && reason.status === 404) clearDetail();
      failure(reason); throw reason;
    } finally {
      if (live.current && sequence === detailRequest.current) setDetailLoading(false);
    }
  }
  async function loadLists(nextTab = tab, preferredId?: string, preferredKey?: string) {
    const sequence = ++listsRequest.current;
    clearDetail(); setLoading(true); setListsReady(false);
    try {
      const [nextAgents, nextTools] = await Promise.all([
        listManagedAgents(workspaceId, accessToken), listTools(workspaceId, accessToken),
      ]);
      if (!live.current || sequence !== listsRequest.current) return;
      setAgents(nextAgents); setTools(nextTools); setListsReady(true); setNeedsRefresh(false);
      const items = nextTab === "agent" ? nextAgents : nextTools;
      const next = items.find(item => item.id === preferredId)
        ?? (nextTab === "tool" ? nextTools.find(item => item.tool_key === preferredKey) : undefined) ?? items[0];
      if (next) await openDetail(nextTab, next.id);
    } catch (reason) {
      if (!live.current || sequence !== listsRequest.current || denied.current) return;
      failure(reason); throw reason;
    } finally {
      if (live.current && sequence === listsRequest.current) setLoading(false);
    }
  }
  async function refreshSharedAgents() {
    const sequence = ++sharedRequest.current;
    try {
      const active = await listAgents(workspaceId, accessToken);
      if (live.current && !denied.current && sequence === sharedRequest.current) onAgentsChange(active);
    } catch (reason) {
      if (live.current && sequence === sharedRequest.current) { onAgentsChange(null); failure(reason); }
      throw reason;
    }
  }
  function confirm(text: string, action: () => void) {
    if (pending.current || blocked || !live.current) return;
    confirmTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setConfirmation({ text: dirty.current && !text.includes("未保存") ? `有未保存的修改，继续将放弃当前草稿。${text}` : text, action });
  }
  function closeConfirmation() { setConfirmation(null); confirmTrigger.current?.focus(); }
  function discardThen(action: () => void) {
    if (pending.current || blocked) return;
    if (dirty.current) confirm("有未保存的修改，继续将放弃当前草稿。", action);
    else action();
  }
  function read(action: () => Promise<void>) {
    if (pending.current || blocked || !live.current) return;
    setError(""); setMessage("");
    void action().catch(() => { /* Scoped loaders already display the error. */ });
  }
  async function mutate<T>(action: () => Promise<T>, apply: (value: T) => string,
    refresh: (value: T) => Promise<void>, affectsAgents = false, conflictKey?: string) {
    if (!live.current || pending.current || denied.current || locked || detailLoading) return;
    pending.current = true; invalidate(); setBusy(true); setLoading(false); setDetailLoading(false);
    setError(""); setMessage(""); onPendingChange(true);
    if (affectsAgents) onAgentsChange(null);
    let committed = false;
    try {
      const result = await action();
      if (!live.current) return;
      committed = true; dirty.current = false; setMessage(apply(result));
      if (affectsAgents) await refreshSharedAgents();
      if (!live.current || denied.current) return;
      await refresh(result);
    } catch (reason) {
      if (!live.current) return;
      failure(reason, !committed);
      if (committed && !denied.current) {
        setNeedsRefresh(true); setError("操作已完成，列表刷新失败。请手动刷新，不要重复提交操作。");
      } else if (reason instanceof ApiError && [404, 409].includes(reason.status)) {
        try { await loadLists(tab, selectedId ?? undefined, conflictKey); } catch { /* No write replay. */ }
      }
    } finally {
      pending.current = false;
      if (live.current) { setBusy(false); onPendingChange(false); }
    }
  }

  useEffect(() => {
    live.current = true; const mounted = ++listsRequest.current;
    void Promise.resolve().then(() => {
      if (live.current && mounted === listsRequest.current) return loadLists();
    }).catch(() => {});
    return () => { live.current = false; invalidate(); onPendingChange(false); };
    // The wrapper remounts on every Workspace/token/role change, including A -> B -> A.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!confirmation) return;
    const modal = dialog.current; modal?.showModal();
    return () => modal?.close();
  }, [confirmation]);

  function saveAgent(payload: AgentUpdate) {
    if (creating) void mutate(() => createAgent(workspaceId, payload as AgentCreate, accessToken),
      () => "Agent 已创建为草稿，尚未开放使用。", result => loadLists("agent", result.id), true);
    else if (agent && Object.keys(payload).length) void mutate(() => updateAgent(workspaceId, agent.id, payload, accessToken),
      () => "Agent 已保存。", result => loadLists("agent", result.id), true);
    else { dirty.current = false; setMessage("Agent 内容未修改。"); }
  }
  function saveTool(payload: ToolCreate | ToolUpdate) {
    if (creating && "tool_key" in payload) void mutate(() => createTool(workspaceId, payload, accessToken),
      () => "工具已创建为禁用状态，尚未开放使用。", result => loadLists("tool", result.id), false, payload.tool_key);
    else if (tool && Object.keys(payload).length) void mutate(() => updateTool(workspaceId, tool.id, payload, accessToken),
      () => "工具已保存。", result => loadLists("tool", result.id));
    else { dirty.current = false; setMessage("工具内容未修改。"); }
  }
  function newItem() {
    discardThen(() => { invalidate(); clearDetail(); setLoading(false); setCreating(true); setError(""); setMessage(""); });
  }
  function switchTab(next: Tab) {
    if (next === tab) return;
    discardThen(() => {
      invalidate(); clearDetail(); setLoading(false); setTab(next); setError(""); setMessage("");
      if (!listsReady) { read(() => loadLists(next)); return; }
      const first = next === "agent" ? agents[0] : tools[0];
      if (first) read(() => openDetail(next, first.id));
    });
  }
  const items = tab === "agent" ? agents : tools;
  const available = TOOL_HELP.filter(help => !tools.some(item => item.tool_key === help.tool_key));
  const selectedTools = new Map([...tools, ...(assigned ?? [])].map(item => [item.id, item]));
  return <section className="knowledge-admin agent-tool-admin" aria-label="Agent 与工具管理">
    <p className="knowledge-intro">配置当前工作空间的 Agent 与注册工具。分配和启用不会绕过运行时权限或人工审批。</p>
    <div className="knowledge-actions admin-tabs" aria-label="管理分类">
      <button type="button" aria-pressed={tab === "agent"} disabled={busy || blocked} onClick={() => switchTab("agent")}>Agent 配置</button>
      <button type="button" aria-pressed={tab === "tool"} disabled={busy || blocked} onClick={() => switchTab("tool")}>工具配置</button>
    </div>
    {busy && <p role="status">正在提交操作，请等待结果…</p>}
    {error && <p className="notice error-notice" role="alert">{error}</p>}
    {message && <p className="notice success-notice" role="status">{message}</p>}
    {!blocked && <div className="knowledge-admin-layout">
      <aside className="qa-context-card knowledge-library" aria-label={tab === "agent" ? "Agent 列表" : "工具列表"}>
        <h2>{tab === "agent" ? "Agent" : "注册工具"}</h2>
        <div className="knowledge-actions">
          <button type="button" disabled={busy} onClick={() => discardThen(() => read(async () => {
            await loadLists(tab, selectedId ?? undefined); await refreshSharedAgents();
          }))}>刷新配置</button>
          <button type="button" disabled={locked || tab === "tool" && !available.length} onClick={newItem}>{tab === "agent" ? "新建 Agent" : "新建工具"}</button>
        </div>
        {loading && <p role="status">正在读取配置…</p>}
        {listsReady && !items.length && <p>{tab === "agent" ? "暂无 Agent，可先创建草稿。" : "暂无工具，可从注册能力创建配置。"}</p>}
        {tab === "tool" && listsReady && !available.length && <p>所有注册能力均已配置。</p>}
        <ul className="knowledge-base-list">{items.map(item => <li key={item.id}>
          <button type="button" aria-pressed={selectedId === item.id} disabled={busy || loading} onClick={() => discardThen(() => {
            listsRequest.current++; setLoading(false); read(() => openDetail(tab, item.id));
          })}><strong>{item.name}</strong><span>{formatEnumLabel(item.status)}</span></button>
        </li>)}</ul>
      </aside>
      <div className="agent-admin-detail">
        {detailLoading && <p role="status">正在读取详情和分配…</p>}
        {!detailLoading && !creating && !agent && !tool && <p className="muted">选择已有配置或新建配置。读取失败时请刷新，不会将失败结果视为空配置。</p>}
        {tab === "agent" && !detailLoading && (creating || agent) && <>
          <AgentEditor key={`agent:${editorEpoch}`} agent={agent} busy={locked} onDirty={value => { dirty.current = value; }} onSave={saveAgent} />
          {creating && <button type="button" disabled={busy} onClick={() => discardThen(() => read(() => loadLists("agent")))}>取消创建</button>}
          {agent && <>
            <p>当前状态：<strong>{formatEnumLabel(agent.status)}</strong> · 更新于 {formatTimestamp(agent.updated_at)}</p>
            <div className="knowledge-actions" aria-label="Agent 状态操作">{(["draft", "active", "disabled"] as const).filter(status => status !== agent.status).map(status =>
              <button key={status} type="button" disabled={locked} onClick={() => confirm(status === "active"
                ? "启用后，当前工作空间成员可以使用此 Agent；工具执行仍需满足分配、状态和审批规则。"
                : "改为草稿或禁用后，新的 Agent 请求不可用，尚待审批的申请可能在审批检查时失效。工具分配保留。",
              () => { void mutate(() => updateAgent(workspaceId, agent.id, { status }, accessToken),
                () => "Agent 状态已更新。", result => loadLists("agent", result.id), true); })}>
                {status === "active" ? "启用 Agent" : status === "draft" ? "改为草稿" : "禁用 Agent"}</button>)}</div>
            <section className="agent-assignments" aria-label="Agent 工具分配"><h2>工具分配</h2>
              <p className="muted">已分配不代表可以执行。只有 Agent 与工具均启用才成为候选能力，后端仍检查当前权限和审批。</p>
              {!selectedTools.size && <p>尚无工具配置，请先进入工具配置创建。</p>}
              <ul>{Array.from(selectedTools.values()).map(item => {
                const has = assigned?.some(edge => edge.id === item.id) ?? false;
                const eligible = has && agent.status === "active" && item.status === "active";
                const valid = usableConfiguration(item);
                return <li className="agent-tool-row" key={item.id}>
                  <div><strong>{item.name}</strong><p>{has ? eligible ? "已分配，满足候选状态条件" : "已分配，当前未生效" : "未分配"} · {formatEnumLabel(item.status)}</p>
                    <small>{formatEnumLabel(item.operation_type)} · {item.risk_level === "high" ? "高风险，需人工审批" : item.risk_level === "low" ? "低风险" : "中风险"}</small>
                    {!valid && <p role="alert">能力配置不可用，请联系管理员。</p>}
                  </div>
                  <button type="button" disabled={locked || !assigned || !valid} aria-label={`${has ? "解除" : "分配"} ${item.name}`} onClick={() => confirm(has
                    ? "解除后，新的请求不能选择此工具，尚待审批的申请可能在审批检查时失效。只解除关联，不删除工具。"
                    : `分配 ${item.name} 后，仅在 Agent 与工具均启用时成为候选能力；仍遵守本人数据限制及需要时的人工审批。`,
                  () => { void mutate(() => has ? unassignTool(workspaceId, agent.id, item.id, accessToken) : assignTool(workspaceId, agent.id, item.id, accessToken).then(() => undefined),
                    () => has ? "工具关联已解除。" : "工具已分配。", () => loadLists("agent", agent.id)); })}>{has ? "解除" : "分配"}</button>
                </li>;
              })}</ul>
            </section>
          </>}
        </>}
        {tab === "tool" && !detailLoading && (creating || tool) && <>
          <ToolEditor key={`tool:${editorEpoch}`} tool={tool} tools={tools} busy={locked || !!tool && !usableConfiguration(tool)} onDirty={value => { dirty.current = value; }} onSave={saveTool} />
          {creating && <button type="button" disabled={busy} onClick={() => discardThen(() => read(() => loadLists("tool")))}>取消创建</button>}
          {tool && <>
            <p>当前状态：<strong>{formatEnumLabel(tool.status)}</strong> · {formatEnumLabel(tool.operation_type)} · {tool.risk_level === "high" ? "高风险" : tool.risk_level === "low" ? "低风险" : "中风险"}</p>
            <p className="muted">更新于 {formatTimestamp(tool.updated_at)}；能力标识、类型、风险、参数和审批规则不可编辑。</p>
            {!usableConfiguration(tool) && <p role="alert">能力配置不可用，请联系管理员。</p>}
            <button type="button" disabled={locked || !usableConfiguration(tool)} onClick={() => confirm(tool.status === "active"
              ? "禁用影响所有已分配此工具的 Agent。保留分配关系，待审批申请可能在审批检查时失效；不会立即取消已有申请。"
              : "启用仅使已分配且启用的 Agent 可以选择该工具；敏感申请仍需人工审批。",
            () => { void mutate(() => updateTool(workspaceId, tool.id, { status: tool.status === "active" ? "disabled" : "active" }, accessToken),
              () => "工具状态已更新。", result => loadLists("tool", result.id)); })}>{tool.status === "active" ? "禁用工具" : "启用工具"}</button>
          </>}
        </>}
      </div>
    </div>}
    {confirmation && <dialog className="knowledge-confirmation" ref={dialog} aria-label="确认配置操作" onCancel={e => { e.preventDefault(); closeConfirmation(); }}>
      <h2>确认操作</h2><p>{confirmation.text}</p><div className="knowledge-actions">
        <button type="button" onClick={closeConfirmation}>取消</button>
        <button className="primary-button" type="button" onClick={() => { const action = confirmation.action; closeConfirmation(); action(); }}>确认继续</button>
      </div>
    </dialog>}
  </section>;
}
