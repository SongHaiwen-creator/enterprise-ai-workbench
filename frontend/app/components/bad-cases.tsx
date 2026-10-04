"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError } from "@/utils/api";
import {
  BadCaseDetail, BadCaseSummary, Category, Filters, HistoryItem, HumanValues, Status,
  categories, origins, statuses, createBadCase, getBadCase, getBadCaseHistory, listBadCases, updateBadCase,
} from "@/utils/bad-cases";
import { RunCaseDetail, getEvaluationRun } from "@/utils/evaluation-runs";
import { displayMessage, formatEnumLabel, formatTimestamp } from "@/utils/presentation";

type Props = { workspaceId: string; accessToken: string; onUnauthorized: () => void };
const notice = "只记录合成或脱敏问题。请勿粘贴生产个人信息、凭据、完整生产问答、工具参数或服务原始数据。变更历史会保留旧文本，清空字段不会删除历史。";
const transitions: Record<Status, Status[]> = { open: ["open", "investigating", "resolved", "dismissed"], investigating: ["investigating", "open", "resolved", "dismissed"], resolved: ["resolved", "open"], dismissed: ["dismissed", "open"] };

function Editor({ item, initialTitle, busy, onSave }: { item?: BadCaseDetail; initialTitle?: string; busy: boolean; onSave: (values: HumanValues, reason: string | null) => void }) {
  const [title, setTitle] = useState(item?.title ?? initialTitle ?? "");
  const [description, setDescription] = useState(item?.description ?? "");
  const [category, setCategory] = useState<Category>(item?.category ?? "unclassified");
  const [cause, setCause] = useState(item?.possible_cause ?? "");
  const [handling, setHandling] = useState(item?.handling_note ?? "");
  const [status, setStatus] = useState<Status>(item?.status ?? "open");
  const [resolution, setResolution] = useState(item?.resolution_note ?? "");
  const [reason, setReason] = useState("");
  const terminal = status === "resolved" || status === "dismissed";
  function submit(event: FormEvent) {
    event.preventDefault();
    onSave({ title: title.trim(), description: description.trim(), category,
      possible_cause: cause.trim() || null, handling_note: handling.trim() || null, status,
      resolution_note: terminal ? resolution.trim() || null : null }, reason.trim() || null);
  }
  return <form className="evaluation-form" onSubmit={submit}><fieldset disabled={busy}>
    <legend>{item ? "编辑问题" : "登记问题"}</legend><p>{notice}</p>
    <label>问题标题<input required maxLength={255} value={title} onChange={e => setTitle(e.target.value)} /></label>
    <label>问题描述<textarea required maxLength={5000} value={description} onChange={e => setDescription(e.target.value)} /></label>
    <label>人工分类<select aria-label="人工分类" value={category} onChange={e => setCategory(e.target.value as Category)}>{Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>可能原因（人工假设）<textarea maxLength={5000} value={cause} onChange={e => setCause(e.target.value)} /></label>
    {item && <>
      <label>处理备注<textarea maxLength={5000} value={handling} onChange={e => setHandling(e.target.value)} /></label>
      <label>处理状态<select aria-label="处理状态" value={status} onChange={e => setStatus(e.target.value as Status)}>{transitions[item.status].map(key => <option key={key} value={key}>{statuses[key]}</option>)}</select></label>
      {terminal && <label>人工处理结论<textarea required maxLength={5000} value={resolution} onChange={e => setResolution(e.target.value)} /></label>}
      <label>变更理由<textarea required={status !== item.status} maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} /></label>
      <p>结束问题是人工判断，不表示系统已验证修复或复测通过。</p>
    </>}
    <button type="submit" className="primary-button" disabled={!title.trim() || !description.trim()}>{item ? "保存问题" : "提交登记"}</button>
  </fieldset></form>;
}

function Evidence({ item }: { item: BadCaseDetail }) {
  const source = item.source_evidence;
  return <article aria-label="问题源证据"><h3>原始评测证据</h3>
    <p>{origins[item.origin_kind]}。原始评分保持不变。</p>
    <p>源运行：{item.source_run_id}；源结果：{item.source_run_case_id}</p>
    <p>用例：{source.name}；{formatEnumLabel(source.case_type)}；结果：{formatEnumLabel(source.result ?? "pending")}</p>
    {source.error_category && <p>运行错误：{formatEnumLabel(source.error_category)}。ERROR 不代表回答质量评分。</p>}
    {source.case_type === "tool_calling" && <p>工具仅作模拟验证（dry run），没有执行工具。</p>}
    {source.case_type === "permission_boundary" && <p>权限策略模拟（policy simulation），不代表真实身份执行。</p>}
    <p>原始输入</p><pre>{source.test_input_snapshot}</pre>
    <p>预期结果</p><pre>{JSON.stringify(source.expected_behavior_snapshot, null, 2)}</pre>
    <p>实际结果</p><pre>{JSON.stringify(source.actual_behavior, null, 2)}</pre>
    <p>检查结果</p><pre>{JSON.stringify(source.comparison_checks, null, 2)}</pre>
  </article>;
}

export function BadCases(props: Props) {
  return <WorkspaceBadCases key={`${props.workspaceId}:${props.accessToken}`} {...props} />;
}
function WorkspaceBadCases({ workspaceId, accessToken, onUnauthorized }: Props) {
  const [items, setItems] = useState<BadCaseSummary[]>([]);
  const [filters, setFilters] = useState<Filters>({});
  const [more, setMore] = useState(false);
  const [selected, setSelected] = useState<BadCaseDetail | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyMore, setHistoryMore] = useState(false);
  const [runSummary, setRunSummary] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [blocked, setBlocked] = useState(false);
  const [editorEpoch, setEditorEpoch] = useState(0);
  const live = useRef(true), pending = useRef(false);
  async function page(offset = 0, chosen = filters) {
    const response = await listBadCases(workspaceId, chosen, offset, accessToken);
    if (!live.current) return;
    setItems(old => offset ? [...old, ...response.items] : response.items);
    setMore(response.items.length === 50);
  }
  async function open(id: string) {
    const [item, entries] = await Promise.all([getBadCase(workspaceId, id, accessToken), getBadCaseHistory(workspaceId, id, 0, accessToken)]);
    if (!live.current) return;
    setSelected(item); setHistory(entries.items); setHistoryMore(entries.items.length === 50);
    setEditorEpoch(old => old + 1);
    setBlocked(false); setRunSummary("");
  }
  function failure(reason: unknown, mutation = false) {
    if (!live.current) return;
    if (reason instanceof ApiError && reason.status === 401) { onUnauthorized(); return; }
    if (mutation) setBlocked(true);
    setError(mutation && reason instanceof ApiError && reason.status === 409
      ? "问题已被其他人修改或正在处理中。请重新读取最新问题并手动协调，草稿不会自动重提。"
      : mutation && (!(reason instanceof ApiError) || reason.status === 0 || reason.status >= 500)
        ? "未收到保存确认，服务端可能已保存。请先重新读取最新问题，再决定是否提交。"
        : reason instanceof ApiError ? displayMessage(reason.message, reason.status) : "问题案例暂不可用，请重试。");
  }
  async function operation(action: () => Promise<void>, mutation = false) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try { await action(); } catch (reason) { failure(reason, mutation); }
    finally { pending.current = false; if (live.current) setBusy(false); }
  }
  useEffect(() => {
    live.current = true; pending.current = true;
    void page().catch(reason => failure(reason)).finally(() => { pending.current = false; if (live.current) setBusy(false); });
    return () => { live.current = false; };
    // Workspace and session changes remount confidential state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <section className="qa-context-card bad-cases" aria-label="问题案例">
    <h2>问题案例</h2><p>从评测结果详情登记问题。分类、原因与结论由管理员人工记录，原始评分不变。</p>
    <fieldset className="evaluation-form" disabled={busy}><legend>筛选问题</legend>
      {(["status", "category", "origin_kind"] as const).map(key => <label key={key}>{key === "status" ? "状态筛选" : key === "category" ? "分类筛选" : "来源筛选"}<select value={filters[key] ?? ""} onChange={e => {
        const next = { ...filters, [key]: e.target.value || undefined }; setFilters(next);
        void operation(() => page(0, next));
      }}><option value="">全部</option>{Object.entries(key === "status" ? statuses : key === "category" ? categories : origins).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>)}
      <button type="button" onClick={() => void operation(() => page())}>刷新问题列表</button>
    </fieldset>
    {busy && <p aria-live="polite">正在加载或保存问题…</p>}{error && <p role="alert">{error}</p>}
    {!items.length && !busy && <p>暂无符合条件的问题。</p>}
    <div className="evaluation-results"><table><thead><tr><th>问题</th><th>来源</th><th>分类</th><th>状态</th><th>登记时间</th></tr></thead>
      <tbody>{items.map(item => <tr key={item.id}><td><button disabled={busy} onClick={() => void operation(() => open(item.id))}>{item.title}</button></td><td>{origins[item.origin_kind]}</td><td>{categories[item.category]}</td><td>{statuses[item.status]}</td><td>{formatTimestamp(item.created_at)}</td></tr>)}</tbody></table></div>
    {more && <button disabled={busy} onClick={() => void operation(() => page(items.length))}>加载更多问题</button>}
    {selected && <>
      <h3>{selected.title}</h3><p>修订 {selected.revision}；最后修改者：{selected.updated_by}</p>
      <button disabled={busy} onClick={() => void operation(() => open(selected.id))}>重新读取最新问题（替换草稿）</button>
      <Editor key={`${selected.id}:${selected.revision}:${editorEpoch}`} item={selected} busy={busy || blocked} onSave={(values, reason) => void operation(async () => {
        const result = await updateBadCase(workspaceId, selected.id, { ...values, expected_revision: selected.revision, change_reason: reason }, accessToken);
        if (!live.current) return;
        // Retain the prior revision until detail AND history refresh succeeds.
        await open(result.id); if (live.current) await page();
      }, true)} />
      <Evidence item={selected} />
      <button disabled={busy} onClick={() => void operation(async () => {
        const run = await getEvaluationRun(workspaceId, selected.source_run_id, accessToken);
        if (live.current) setRunSummary(`${run.dataset_name} / ${run.agent_name}；${formatEnumLabel(run.status)}；评分器 ${run.scorer_version}；配置 ${run.configuration_sha256}`);
      })}>查看源运行概览</button>{runSummary && <p>{runSummary}</p>}
      <h3>人工变更历史</h3><ol>{history.map(entry => <li key={entry.id}>
        <p>修订 {entry.revision} · {formatTimestamp(entry.created_at)} · 操作者 {entry.actor_id}</p>
        <p>理由：{entry.change_reason ?? "未填写"}</p><p>修改前</p><pre>{JSON.stringify(entry.before_values, null, 2)}</pre>
        <p>修改后</p><pre>{JSON.stringify(entry.after_values, null, 2)}</pre>
      </li>)}</ol>
      {historyMore && <button disabled={busy} onClick={() => void operation(async () => {
        const response = await getBadCaseHistory(workspaceId, selected.id, history.length, accessToken);
        if (live.current) { setHistory(old => [...old, ...response.items]); setHistoryMore(response.items.length === 50); }
      })}>加载更多变更历史</button>}
    </>}
  </section>;
}

export function RegisterBadCase(props: Props & { source: RunCaseDetail; runTerminal: boolean }) {
  return <SourceRegistration key={`${props.workspaceId}:${props.accessToken}:${props.source.id}`} {...props} />;
}
function SourceRegistration({ workspaceId, accessToken, onUnauthorized, source, runTerminal }: Props & { source: RunCaseDetail; runTerminal: boolean }) {
  const [item, setItem] = useState<BadCaseDetail | null>(null);
  const [form, setForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState("");
  const live = useRef(true), pending = useRef(false);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  async function findExisting() {
    const response = await listBadCases(workspaceId, { source_run_case_id: source.id }, 0, accessToken);
    const existing = response.items[0] ? await getBadCase(workspaceId, response.items[0].id, accessToken) : null;
    if (!live.current) return;
    setItem(existing); setForm(!existing); setBlocked(false);
  }
  async function operation(action: () => Promise<void>, submission = false) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try { await action(); } catch (reason) {
      if (!live.current) return;
      if (reason instanceof ApiError && reason.status === 401) { onUnauthorized(); return; }
      if (submission) setBlocked(true);
      if (submission && reason instanceof ApiError && reason.message === "Bad case already exists") {
        setError("该结果已登记。请刷新核查并查看原问题。");
      } else setError(submission ? "登记未确认。请先刷新核查，避免重复提交。" : "无法读取问题，请重试。");
    } finally { pending.current = false; if (live.current) setBusy(false); }
  }
  if (!runTerminal || !source.result) return <p>运行结束且用例形成终态结果后才能登记问题。</p>;
  return <section aria-label="登记评测问题">
    <p>{source.result === "passed" ? "PASS 可登记人工复核，不会改成 FAIL。" : source.result === "error" ? "ERROR 表示运行错误，不是回答质量评分。" : "FAIL 表示结构化期待未匹配，不证明语义回答错误。"}</p>
    <button disabled={busy} onClick={() => void operation(findExisting)}>登记问题 / 刷新核查</button>
    {error && <p role="alert">{error}</p>}
    {form && <Editor initialTitle={source.name} busy={busy || blocked} onSave={values => void operation(async () => {
      const result = await createBadCase(workspaceId, source, { title: values.title, description: values.description, category: values.category, possible_cause: values.possible_cause }, accessToken);
      if (live.current) { setItem(result); setForm(false); }
    }, true)} />}
    {item && <article><h4>已登记：{item.title}</h4><p>{statuses[item.status]}；问题编号 {item.id}。请在“问题案例”中查看及处理。</p><Evidence item={item} /></article>}
  </section>;
}
