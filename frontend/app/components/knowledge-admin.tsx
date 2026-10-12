"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, type KnowledgeBase, type MembershipRole, listKnowledgeBases } from "@/utils/api";
import {
  type DocumentIndexResponse, type DocumentFamily, type KnowledgeDocument, type KnowledgeBaseUpdate,
  createKnowledgeBase, getDocument, getKnowledgeBase, indexDocument,
  updateDocumentStatus, updateKnowledgeBase, uploadDocument, listDocumentFamilies,
  getDocumentFamily, listDocumentVersions, uploadDocumentVersion, activateDocumentVersion,
} from "@/utils/knowledge-admin";
import { displayMessage, formatTimestamp } from "@/utils/presentation";

type Props = {
  workspaceId: string; accessToken: string; role: MembershipRole;
  onUnauthorized: () => void; onPendingChange: (pending: boolean) => void;
  onBasesChange: (items: KnowledgeBase[] | null) => void;
};
const statusLabels = { uploaded: "已上传", processing: "解析中", ready: "解析完成", failed: "解析失败", disabled: "已禁用" };
const codepoints = (value: string) => Array.from(value).length;

function BaseEditor({ base, busy, onSave }: {
  base: KnowledgeBase | null; busy: boolean; onSave: (values: KnowledgeBaseUpdate) => void;
}) {
  const [name, setName] = useState(base?.name ?? "");
  const [description, setDescription] = useState(base?.description ?? "");
  const [error, setError] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    const nextName = name.trim(), nextDescription = description.trim() || null;
    if (!nextName || codepoints(nextName) > 255 || codepoints(nextDescription ?? "") > 5000) {
      setError("名称须为 1–255 个字符，描述最多 5000 个字符。"); return;
    }
    setError("");
    const values: KnowledgeBaseUpdate = {};
    if (!base || nextName !== base.name) values.name = nextName;
    if (!base || nextDescription !== base.description) values.description = nextDescription;
    onSave(values);
  }
  return <form className="knowledge-form" onSubmit={submit}>
    <fieldset disabled={busy}><legend>{base ? "编辑知识库" : "创建知识库"}</legend>
      <label>知识库名称<input required value={name} onChange={e => setName(e.target.value)} /></label>
      <label>知识库描述<textarea rows={3} value={description} onChange={e => setDescription(e.target.value)} /></label>
      {error && <p role="alert">{error}</p>}
      <button className="primary-button" type="submit">{base ? "保存知识库" : "创建知识库"}</button>
    </fieldset>
  </form>;
}

export function KnowledgeAdmin(props: Props) {
  if (props.role !== "knowledge_admin" && props.role !== "system_admin") {
    return <p role="alert">知识管理需要当前工作空间的知识管理员或系统管理员权限。</p>;
  }
  return <WorkspaceKnowledgeAdmin key={`${props.workspaceId}:${props.accessToken}:${props.role}`} {...props} />;
}

function WorkspaceKnowledgeAdmin({ workspaceId, accessToken, onUnauthorized, onPendingChange, onBasesChange }: Props) {
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [base, setBase] = useState<KnowledgeBase | null>(null);
  const [families, setFamilies] = useState<DocumentFamily[]>([]);
  const [family, setFamily] = useState<DocumentFamily | null>(null);
  const [replacement, setReplacement] = useState(false);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [document, setDocument] = useState<KnowledgeDocument | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileEpoch, setFileEpoch] = useState(0);
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadingBases, setLoadingBases] = useState(true);
  const [loadingBaseDetail, setLoadingBaseDetail] = useState(false);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [indexResult, setIndexResult] = useState<DocumentIndexResponse | null>(null);
  const [confirmation, setConfirmation] = useState<{ text: string; action: () => void } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(false), pending = useRef(false);
  const baseRequest = useRef(0), documentsRequest = useRef(0), detailRequest = useRef(0);
  const locked = busy || blocked;

  function invalidateReads() {
    baseRequest.current += 1; documentsRequest.current += 1; detailRequest.current += 1;
  }
  function resetDocuments() {
    documentsRequest.current += 1; detailRequest.current += 1;
    setFamilies([]); setFamily(null); setReplacement(false); setDocuments([]); setDocument(null); setFile(null); setFileEpoch(n => n + 1);
    setIndexResult(null); setLoadingDocuments(false);
  }
  function failure(reason: unknown, mutation = false) {
    if (!live.current) return;
    if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
      invalidateReads(); setBases([]); setBase(null); resetDocuments();
      setCreating(false); setEditorEpoch(n => n + 1); setMessage(""); setBlocked(true); setConfirmation(null);
      onBasesChange(null);
      if (reason.status === 401) { onUnauthorized(); return; }
      setError("你没有管理当前工作空间知识的权限，请联系管理员。"); return;
    }
    const status = reason instanceof ApiError ? reason.status : 0;
    const errors: Record<number, string> = {
      409: "当前知识库或文档状态不允许此操作，已尝试刷新最新状态，请确认后再操作。",
      413: "文件超过 10 MiB，请选择较小文件。", 415: "格式不支持，请选择 PDF、TXT 或 Markdown。",
      422: "提交内容或文件不符合要求，请检查输入、文件编码和内容。",
      502: "索引服务请求失败，原有完整索引不会因失败被删除，可手动重试。",
      503: "索引服务尚未配置，请联系管理员。",
    };
    const uncertain = mutation && (status === 0 || status >= 500 && status !== 502 && status !== 503);
    setError(uncertain ? "未收到操作确认，服务端可能已完成。请先刷新核对，再决定是否重试；再次上传可能创建重复文档。"
      : errors[status] ?? (reason instanceof ApiError ? displayMessage(reason.message, status) : "暂时无法加载，请手动刷新。"));
  }

  async function loadDocuments(baseId: string, preferredFamily?: string, preferredDocument?: string) {
    const sequence = ++documentsRequest.current;
    detailRequest.current += 1; setDocument(null); setFamily(null); setLoadingDocuments(true);
    try {
      const items = await listDocumentFamilies(workspaceId, baseId, accessToken);
      if (!live.current || sequence !== documentsRequest.current) return;
      setFamilies(items); setDocuments([]);
      const chosen = items.find(item => item.id === preferredFamily);
      if (chosen) await openFamily(chosen, baseId, preferredDocument);
    } catch (reason) {
      if (!live.current || sequence !== documentsRequest.current) return;
      setFamilies([]); setFamily(null); setDocuments([]); failure(reason); throw reason;
    } finally {
      if (live.current && sequence === documentsRequest.current) setLoadingDocuments(false);
    }
  }
  async function openFamily(item: DocumentFamily, baseId: string, preferredDocument?: string) {
    const sequence = ++detailRequest.current;
    setFamily(null); setDocuments([]); setDocument(null); setFile(null); setReplacement(false); setFileEpoch(n => n + 1);
    try {
      const [fresh, versions] = await Promise.all([
        getDocumentFamily(workspaceId, baseId, item.id, accessToken),
        listDocumentVersions(workspaceId, baseId, item.id, accessToken),
      ]);
      if (!live.current || sequence !== detailRequest.current) return;
      setFamily(fresh); setDocuments(versions);
      const chosen = versions.find(v => v.id === preferredDocument) ?? versions.find(v => v.id === fresh.current_document_id) ?? versions[0];
      if (chosen) {
        const detail = await getDocument(workspaceId, baseId, chosen.id, accessToken);
        if (live.current && sequence === detailRequest.current) setDocument(detail);
      }
    } catch (reason) {
      if (!live.current || sequence !== detailRequest.current) return;
      setFamily(null); setDocuments([]); setDocument(null); failure(reason); throw reason;
    }
  }
  async function chooseBase(item: KnowledgeBase) {
    setLoadingBases(false);
    setBase(item); setCreating(false); setEditorEpoch(n => n + 1); resetDocuments();
    const sequence = ++baseRequest.current;
    setLoadingBaseDetail(true);
    // List metadata is sufficient to start browsing; detail refreshes the editor.
    void getKnowledgeBase(workspaceId, item.id, accessToken).then(fresh => {
      if (!live.current || sequence !== baseRequest.current) return;
      setBase(fresh); setEditorEpoch(n => n + 1);
    }).catch(reason => {
      if (!live.current || sequence !== baseRequest.current) return;
      if (reason instanceof ApiError && reason.status === 404) { setBase(null); resetDocuments(); }
      failure(reason);
    }).finally(() => {
      if (live.current && sequence === baseRequest.current) setLoadingBaseDetail(false);
    });
    await loadDocuments(item.id);
  }
  async function loadBases(preferredId?: string) {
    const sequence = ++baseRequest.current;
    setLoadingBases(true);
    let items: KnowledgeBase[];
    try {
      items = await listKnowledgeBases(workspaceId, accessToken);
    } catch (reason) {
      if (!live.current || sequence !== baseRequest.current) return;
      setBases([]); onBasesChange(null); failure(reason); throw reason;
    } finally {
      if (live.current && sequence === baseRequest.current) setLoadingBases(false);
    }
    if (!live.current || sequence !== baseRequest.current) return;
    setBases(items); onBasesChange(items);
    const next = items.find(item => item.id === preferredId) ?? items[0];
    if (next) await chooseBase(next);
    else { setBase(null); resetDocuments(); }
  }
  async function read(action: () => Promise<void>) {
    if (pending.current || blocked) return;
    setError(""); setMessage("");
    try { await action(); } catch { /* Load functions display scoped errors. */ }
  }
  async function mutate<T>(action: () => Promise<T>, apply: (result: T) => string,
    refresh?: (result: T) => Promise<void>, affectsBases = false) {
    if (pending.current || blocked) return;
    pending.current = true; invalidateReads(); setBusy(true); setLoadingDocuments(false);
    setLoadingBases(false); setLoadingBaseDetail(false); setError(""); setMessage(""); onPendingChange(true);
    if (affectsBases) onBasesChange(null);
    let committed = false;
    try {
      const result = await action();
      if (!live.current) return;
      committed = true; setMessage(apply(result));
      if (refresh) await refresh(result);
    } catch (reason) {
      if (!live.current) return;
      failure(reason, !committed);
      if (committed && !(reason instanceof ApiError && [401, 403].includes(reason.status))) {
        setError("操作已完成，列表刷新失败。请手动刷新，不要重复提交操作。");
      } else if (reason instanceof ApiError && [404, 409].includes(reason.status)) {
        // Clear stale detail immediately. Refresh is a GET, never a replayed write.
        setDocument(null); setIndexResult(null);
        try { await loadBases(base?.id); } catch { /* Retain the refresh failure. */ }
      }
    } finally {
      pending.current = false;
      if (live.current) { setBusy(false); onPendingChange(false); }
    }
  }

  useEffect(() => {
    live.current = true;
    const mounted = ++baseRequest.current;
    void Promise.resolve().then(() => {
      if (live.current && mounted === baseRequest.current) return loadBases();
    }).catch(() => {});
    return () => { live.current = false; invalidateReads(); onPendingChange(false); };
    // The wrapper remounts every Workspace/session/role context, including A -> B -> A.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!confirmation) return;
    const modal = dialog.current;
    modal?.showModal();
    return () => modal?.close();
  }, [confirmation]);

  function saveBase(values: KnowledgeBaseUpdate) {
    if (creating) {
      void mutate(() => createKnowledgeBase(workspaceId, { name: values.name!, description: values.description }, accessToken),
        result => { setCreating(false); setBase(result); return "知识库已创建。"; }, result => loadBases(result.id), true);
    } else if (base && Object.keys(values).length) {
      void mutate(() => updateKnowledgeBase(workspaceId, base.id, values, accessToken),
        result => { setBase(result); setEditorEpoch(n => n + 1); return "知识库已保存。"; }, result => loadBases(result.id), true);
    } else setMessage("知识库内容未修改。");
  }
  function submitUpload(event: FormEvent) {
    event.preventDefault();
    if (!base || !file || base.status !== "active") return;
    if (!/\.(pdf|txt|md)$/i.test(file.name) || file.size === 0 || file.size > 10 * 1024 * 1024) {
      setError("请选择非空 PDF、TXT 或 Markdown 文件，大小不超过 10 MiB。"); return;
    }
    const chosen = base, chosenFamily = replacement ? family : null;
    if (replacement && !chosenFamily) return;
    void mutate(() => chosenFamily ? uploadDocumentVersion(workspaceId, chosen.id, chosenFamily.id, file, accessToken) : uploadDocument(workspaceId, chosen.id, file, accessToken), result => {
      setFile(null); setFileEpoch(n => n + 1);
      return result.status === "failed" ? `文档已登记，解析失败。${result.processing_error ?? "请检查文件内容。"} 修正后重新选择文件上传，失败记录保留。`
        : chosenFamily ? "替代版本已解析，当前版本未切换。请索引后显式激活。" : "上传并解析完成，可手动索引。";
    }, result => loadDocuments(chosen.id, result.family_id, result.id));
  }
  async function openDocument(item: KnowledgeDocument) {
    if (!base || pending.current || blocked) return;
    setError(""); setDocument(null); setIndexResult(null);
    const sequence = ++detailRequest.current;
    try {
      const fresh = await getDocument(workspaceId, base.id, item.id, accessToken);
      if (live.current && sequence === detailRequest.current) setDocument(fresh);
    } catch (reason) {
      if (live.current && sequence === detailRequest.current) failure(reason);
    }
  }

  return <section className="knowledge-admin" aria-label="知识管理">
    <p className="knowledge-intro">维护当前工作空间的知识库与文档。上传完成后，需显式生成索引才能用于知识检索。</p>
    {busy && <p role="status">正在提交操作，请等待结果…</p>}
    {error && <p className="notice error-notice" role="alert">{error}</p>}
    {message && <p className="notice success-notice" role="status">{message}</p>}
    {!blocked && <div className="knowledge-admin-layout">
      <aside className="qa-context-card knowledge-library" aria-label="知识库列表">
        <h2>知识库</h2>
        <div className="knowledge-actions">
          <button disabled={locked || loadingBases} onClick={() => { setCreating(true); setLoadingBaseDetail(false); setEditorEpoch(n => n + 1); setError(""); setMessage(""); baseRequest.current += 1; }}>新建知识库</button>
          <button disabled={locked || loadingBases} onClick={() => void read(() => loadBases(base?.id))}>刷新知识库（替换草稿）</button>
        </div>
        {loadingBases && <p role="status">正在加载知识库…</p>}
        {!loadingBases && !bases.length && !error && <p>暂无知识库，可先创建知识库。</p>}
        <ul>{bases.map(item => <li key={item.id}><button disabled={locked || !!confirmation} aria-current={base?.id === item.id && !creating ? "true" : undefined}
          onClick={() => void read(() => chooseBase(item))}><strong>{item.name}</strong>{" "}<span>{item.status === "active" ? "已启用" : "已禁用"}</span></button></li>)}</ul>
      </aside>
      <div className="knowledge-main">
        {(creating || base) && <section className="qa-context-card">
          <BaseEditor key={`${creating ? "new" : base?.id}:${editorEpoch}`} base={creating ? null : base} busy={locked || loadingBases || loadingBaseDetail} onSave={saveBase} />
          {creating ? <button disabled={locked} onClick={() => setCreating(false)}>取消创建</button> : base && <>
            <p>状态：{base.status === "active" ? "已启用" : "已禁用"} · 更新于 {formatTimestamp(base.updated_at)}</p>
            <button disabled={locked || loadingBases || loadingBaseDetail} onClick={() => {
              const selected = base;
              const action = () => void mutate(() => updateKnowledgeBase(workspaceId, selected.id, { status: selected.status === "active" ? "disabled" : "active" }, accessToken),
                result => { setBase(result); return result.status === "disabled" ? "知识库已禁用。" : "知识库已启用，未自动索引文档。"; }, result => loadBases(result.id), true);
              if (base.status === "active") setConfirmation({ text: "禁用后，该知识库不再参与新的知识检索和问答。文档与索引保留。", action });
              else action();
            }}>{base.status === "active" ? "禁用知识库" : "启用知识库"}</button>
          </>}
        </section>}
        {base && !creating && <section className="qa-context-card" aria-label="文档管理">
          <div className="knowledge-heading"><h2>{base.name} · 文档</h2>
            <button disabled={locked} onClick={() => { setIndexResult(null); void read(() => loadBases(base.id)); }}>刷新文档与状态</button></div>
          {base.status === "disabled" && <p>知识库已禁用：可查看和启停已有文档，上传、索引与激活不可用。</p>}
          <form className="knowledge-form" onSubmit={submitUpload}><fieldset disabled={locked || base.status !== "active"}>
            <legend>{replacement ? "上传替代版本" : "上传新文档"}</legend>
            <p>单个文件最多 10 MiB。PDF 须可提取文本；TXT/Markdown 须为 UTF-8。原始文件不保留，同名上传创建独立文档。</p>
            <label>{replacement ? `选择替代文件（${family?.display_name}）` : "选择文档"}<input key={fileEpoch} type="file" accept=".pdf,.txt,.md" onChange={e => { setFile(e.target.files?.[0] ?? null); setError(""); }} /></label>
            <button type="submit" className="primary-button" disabled={!file}>上传并解析</button>
          </fieldset></form>
          {replacement && <button disabled={locked} onClick={() => { setReplacement(false); setFile(null); setFileEpoch(n => n + 1); }}>改为上传新文档</button>}
          {loadingDocuments && <p role="status">正在加载文档…</p>}
          {!loadingDocuments && !families.length && !error && <p>暂无文档，请上传文档。</p>}
          <ul className="knowledge-documents" aria-label="逻辑文档列表">{families.map(item => <li key={item.id}>
            <button disabled={locked || !!confirmation} aria-pressed={family?.id === item.id}
              onClick={() => { setError(""); documentsRequest.current += 1; setLoadingDocuments(false); void read(() => openFamily(item, base.id)); }}>{item.display_name}</button>
            <span>{item.current_document_id ? "已选择当前版本" : "尚无当前版本"}</span>
          </li>)}</ul>
          {family && <div className="knowledge-heading"><h3>{family.display_name} · 版本记录</h3>
            <button disabled={locked || base.status !== "active" || !!confirmation} onClick={() => {
              setReplacement(true); setFile(null); setFileEpoch(n => n + 1); setError("");
            }}>上传替代版本</button></div>}

          <ul className="knowledge-documents">{documents.map(item => <li key={item.id}>
            <button disabled={locked} aria-pressed={document?.id === item.id} onClick={() => void openDocument(item)}>{item.file_name} · 版本 {item.version}</button>
            <span>{item.file_type.toUpperCase()} · 版本 {item.version} · {statusLabels[item.status]} · {item.is_current ? "当前版本" : "历史/候选版本"}</span>
            <small>创建 {formatTimestamp(item.created_at)} · 更新 {formatTimestamp(item.updated_at)}</small>
            {item.processing_error && <p>{item.processing_error}</p>}
            {item.status === "failed" && <p>请修正文件后重新选择上传，新上传不会替换本记录。</p>}
          </li>)}</ul>
          {document && <article className="knowledge-document-detail" aria-label="文档详情">
            <h3>{document.file_name}</h3>
            <p>{document.file_type.toUpperCase()} · 版本 {document.version} · {statusLabels[document.status]}</p>
            <p>创建 {formatTimestamp(document.created_at)} · 更新 {formatTimestamp(document.updated_at)}</p>
            {document.processing_error && <p>解析错误：{document.processing_error}</p>}
            <p>{document.is_current ? "当前版本" : "历史/候选版本"}；解析完成不代表已经生成索引。</p>
            {document.indexing ? <div className="knowledge-index-result"><strong>已冻结索引</strong>
              <p>{document.indexing.chunk_count} 个片段 · {formatTimestamp(document.indexing.indexed_at)}</p>
              <p>{document.indexing.embedding_model} · {document.indexing.embedding_dimensions} 维</p>
              <p>此索引保留历史引用。更新内容或索引请上传新版本。</p></div> : <p>尚未成功索引。</p>}
            <div className="knowledge-actions">
              {family && !document.is_current && document.status === "ready" && document.indexing && <button
                disabled={locked || base.status !== "active" || !!confirmation} onClick={() => {
                  const chosenBase = base, chosenFamily = family, chosenDocument = document;
                  const previous = documents.find(v => v.id === chosenFamily.current_document_id);
                  setConfirmation({ text: `将当前版本切换为 ${chosenDocument.file_name}（版本 ${chosenDocument.version}），原当前版本 ${previous ? previous.version : chosenFamily.current_document_id ? "未确认" : "无"}${previous ? `（${previous.file_name}）` : ""} 将保留为历史记录。新的检索使用目标版本。`,
                    action: () => void mutate(() => activateDocumentVersion(workspaceId, chosenBase.id, chosenFamily.id, chosenDocument.id, chosenFamily.revision, accessToken),
                      () => "当前版本已切换。历史版本和引用保留。", () => loadDocuments(chosenBase.id, chosenFamily.id, chosenDocument.id)) });
                }}>激活此版本</button>}
              {document.status === "ready" && <>
                <button disabled={locked || base.status !== "active" || !!document.indexing} onClick={() => {
                  const chosenBase = base, chosenDocument = document;
                  setConfirmation({ text: "文档文本将发送至已配置的 OpenAI 服务生成索引，可能产生费用；成功的索引将冻结保留，不替换历史片段。", action: () => {
                    setIndexResult(null);
                    void mutate(() => indexDocument(workspaceId, chosenBase.id, chosenDocument.id, accessToken), result => { setIndexResult(result); return "本次索引成功。"; }, () => loadDocuments(chosenBase.id, chosenDocument.family_id, chosenDocument.id));
                  } });
                }}>生成索引</button>
                <button disabled={locked} onClick={() => {
                  const chosenBase = base, chosenDocument = document;
                  setConfirmation({ text: "禁用后，此版本不会进入新的知识检索。已保存的文本、索引与当前指针保留，不自动回退。", action: () => void mutate(
                    () => updateDocumentStatus(workspaceId, chosenBase.id, chosenDocument.id, "disabled", accessToken),
                    () => "文档已禁用，当前指针保留，不自动回退。", () => loadDocuments(chosenBase.id, chosenDocument.family_id, chosenDocument.id)) });
                }}>禁用文档</button>
              </>}
              {document.status === "disabled" && <button disabled={locked} onClick={() => {
                const chosenBase = base, chosenDocument = document;
                void mutate(() => updateDocumentStatus(workspaceId, chosenBase.id, chosenDocument.id, "ready", accessToken),
                  () => "文档已启用，未自动生成索引或激活历史版本。", () => loadDocuments(chosenBase.id, chosenDocument.family_id, chosenDocument.id));
              }}>启用文档</button>}
            </div>
          </article>}
          {indexResult && <div className="knowledge-index-result" role="status">
            <strong>本次索引结果</strong><p>{indexResult.chunk_count} 个片段 · {formatTimestamp(indexResult.indexed_at)}</p>
            <p>{indexResult.embedding_model} · {indexResult.embedding_dimensions} 维</p>
            <p>仅表示本次操作结果，重新进入后不作为持久索引状态。</p>
          </div>}
        </section>}
      </div>
    </div>}
    {confirmation && <dialog ref={dialog} className="knowledge-confirmation" aria-label="确认管理操作" onCancel={e => { e.preventDefault(); setConfirmation(null); }}>
      <h2>确认操作</h2><p>{confirmation.text}</p><div className="knowledge-actions">
        <button autoFocus onClick={() => setConfirmation(null)}>取消</button>
        <button className="primary-button" onClick={() => { const action = confirmation.action; setConfirmation(null); action(); }}>确认继续</button>
      </div>
    </dialog>}
  </section>;
}
