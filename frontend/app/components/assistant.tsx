"use client";

import { displayMessage, formatEnumLabel } from "@/utils/presentation";

import { FormEvent, useState } from "react";

import type { KnowledgeBasesLoadFailure } from "@/app/components/knowledge-qa";
import {
  AgentRouteResponse,
  AgentSummary,
  ApiError,
  KnowledgeBase,
  routeAgentRequest,
} from "@/utils/api";

const KNOWLEDGE_CONTEXT_REQUIRED =
  "Knowledge base context is required for knowledge questions.";

type ResultState =
  | { kind: "initial" }
  | { kind: "loading"; request: string }
  | { kind: "routed"; response: AgentRouteResponse }
  | { kind: "context_required" }
  | { kind: "error"; title: string; message: string };

export type AgentsLoadFailure =
  | { kind: "forbidden"; message: string }
  | { kind: "error"; message: string }
  | null;

interface AssistantProps {
  workspaceId: string;
  workspaceName: string;
  agents: AgentSummary[];
  agentsPending: boolean;
  agentsError: AgentsLoadFailure;
  knowledgeBases: KnowledgeBase[];
  knowledgeBasesError: KnowledgeBasesLoadFailure;
  accessToken: string;
  onUnauthorized: () => void;
  onPendingChange: (pending: boolean) => void;
  onRetryAgents: () => void;
  preferredAgentId?: string | null;
  onAgentSelectionChange?: (id: string) => void;
}

export function Assistant({
  workspaceId,
  workspaceName,
  agents,
  agentsPending,
  agentsError,
  knowledgeBases,
  knowledgeBasesError,
  accessToken,
  onUnauthorized,
  onPendingChange,
  onRetryAgents,
  preferredAgentId,
  onAgentSelectionChange,
}: AssistantProps) {
  const activeAgents = agents.filter((agent) => agent.status === "active");
  const activeKnowledgeBases = knowledgeBases.filter((base) => base.status === "active");
  const [selectedAgentId, setSelectedAgentId] = useState(
    preferredAgentId ?? activeAgents[0]?.id ?? "",
  );
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState(
    activeKnowledgeBases[0]?.id ?? "",
  );
  const [request, setRequest] = useState("");
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ResultState>({ kind: "initial" });
  const [selectedCitationIndex, setSelectedCitationIndex] = useState(0);

  const selectedAgent =
    activeAgents.find((agent) => agent.id === selectedAgentId) ?? activeAgents[0] ?? null;
  const selectedKnowledgeBase =
    activeKnowledgeBases.find((base) => base.id === selectedKnowledgeBaseId) ?? null;
  const isPending = result.kind === "loading";
  const answeredOutcome =
    result.kind === "routed" &&
    result.response.intent === "knowledge_qa" &&
    result.response.outcome.status === "answered"
      ? result.response.outcome
      : null;
  const selectedCitation = answeredOutcome?.citations[selectedCitationIndex] ?? null;
  const toolOutcome =
    result.kind === "routed" && result.response.intent === "tool_request"
      ? result.response.outcome
      : null;

  function resetResult() {
    setValidationMessage(null);
    setResult({ kind: "initial" });
    setSelectedCitationIndex(0);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isPending || !selectedAgent) return;

    const normalizedRequest = request.trim();
    if (normalizedRequest.length === 0) {
      setValidationMessage("请先输入请求内容。");
      return;
    }
    if (normalizedRequest.length > 2000) {
      setValidationMessage("请求内容不能超过 2,000 字。");
      return;
    }

    setValidationMessage(null);
    setResult({ kind: "loading", request: normalizedRequest });
    onPendingChange(true);

    routeAgentRequest(
      workspaceId,
      selectedAgent.id,
      normalizedRequest,
      selectedKnowledgeBase?.id ?? null,
      accessToken,
    )
      .then((response) => {
        setSelectedCitationIndex(0);
        setResult({ kind: "routed", response });
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          onUnauthorized();
          return;
        }
        if (
          error instanceof ApiError &&
          error.status === 422 &&
          error.message === KNOWLEDGE_CONTEXT_REQUIRED
        ) {
          setResult({ kind: "context_required" });
          return;
        }

        if (error instanceof ApiError) {
          const title =
            error.status === 403 ? "没有智能助手访问权限" :
            error.status === 404 ? "智能体或知识库不存在" :
            error.status === 409 ? "智能体或知识库暂不可用" :
            error.status === 422 ? "请检查请求内容" :
            error.status === 502 || error.status === 503 ? "智能助手服务暂不可用" :
            error.status === 0 ? "无法连接服务" :
            "请求处理失败";
          setResult({ kind: "error", title, message: displayMessage(error.message, error.status) });
          return;
        }
        setResult({
          kind: "error",
          title: "请求处理失败",
          message: "暂时无法处理此请求，请稍后重试。",
        });
      })
      .finally(() => onPendingChange(false));
  }

  if (agentsPending) {
    return (
      <section className="qa-loading-shell" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>正在加载智能体</strong>
          <p>正在加载 {workspaceName} 中可用的智能助手。</p>
        </div>
      </section>
    );
  }

  if (agentsError) {
    return (
      <section className="qa-state-card error-state" role="alert">
        <span className="state-icon" aria-hidden="true">!</span>
        <div>
          <p className="section-kicker">智能助手暂不可用</p>
          <h2>{agentsError.kind === "forbidden" ? "没有智能助手访问权限" : "无法加载可用智能体"}</h2>
          <p>{agentsError.message}</p>
          <button className="assistant-retry-button" type="button" onClick={onRetryAgents}>
            重试
          </button>
        </div>
      </section>
    );
  }

  if (!selectedAgent) {
    return (
      <section className="qa-state-card" aria-labelledby="no-agents-title">
        <span className="state-icon" aria-hidden="true">◇</span>
        <div>
          <p className="section-kicker">智能助手</p>
          <h2 id="no-agents-title">暂无已启用的智能体</h2>
          <p>请联系 AI 管理员启用当前空间的智能体。</p>
          <button className="assistant-retry-button" type="button" onClick={onRetryAgents}>
            刷新智能体
          </button>
        </div>
      </section>
    );
  }

  return (
    <div className="qa-layout assistant-layout">
      <div className="qa-main-column">
        <section className="qa-context-card" aria-labelledby="assistant-title">
          <div className="qa-heading-row">
            <div>
              <p className="section-kicker">智能助手</p>
              <h2 id="assistant-title">你想了解什么？</h2>
              <p className="muted">提出一个需求，智能体会判断它需要查询知识、调用企业工具，还是超出了当前能力范围。</p>
            </div>
            <span className="grounded-badge">单次请求</span>
          </div>

          <form className="assistant-form" onSubmit={handleSubmit}>
            <div className="assistant-context-grid">
              <div>
                <label htmlFor="assistant-agent">智能体</label>
                <select
                  id="assistant-agent"
                  value={selectedAgent.id}
                  onChange={(event) => {
                    setSelectedAgentId(event.target.value);
                    onAgentSelectionChange?.(event.target.value);
                    resetResult();
                  }}
                  disabled={isPending}
                >
                  {activeAgents.map((agent) => (
                    <option key={agent.id} value={agent.id}>{agent.name}</option>
                  ))}
                </select>
                {selectedAgent.description && (
                  <p className="knowledge-description">{selectedAgent.description}</p>
                )}
              </div>
              <div>
                <label htmlFor="assistant-knowledge-base">知识库（可选）</label>
                <select
                  id="assistant-knowledge-base"
                  value={selectedKnowledgeBase?.id ?? ""}
                  onChange={(event) => {
                    setSelectedKnowledgeBaseId(event.target.value);
                    resetResult();
                  }}
                  disabled={isPending}
                >
                  <option value="">不选择知识库</option>
                  {activeKnowledgeBases.map((base) => (
                    <option key={base.id} value={base.id}>{base.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {(knowledgeBasesError || activeKnowledgeBases.length === 0 || !selectedKnowledgeBase) && (
              <p className="assistant-context-guidance" role="status">
                {knowledgeBasesError
                  ? "知识库加载失败。你仍可提交业务查询请求。"
                  : activeKnowledgeBases.length === 0
                    ? "暂无已启用的知识库。你仍可提交业务查询请求。"
                    : "知识类问题需要选择已启用的知识库。"}
              </p>
            )}

            <div className="example-prompts" aria-label="示例提问">
              {["差旅报销需要哪些材料？", "查询我的报销状态", "申请 IT 系统访问权限"].map(prompt => <button type="button" key={prompt} disabled={isPending} onClick={() => { setRequest(prompt); setValidationMessage(null); document.getElementById("assistant-request")?.focus(); }}>{prompt}</button>)}
            </div>

            <div className="question-form">
              <label htmlFor="assistant-request">请求内容</label>
              <textarea
                id="assistant-request"
                value={request}
                onChange={(event) => {
                  setRequest(event.target.value);
                  if (validationMessage) setValidationMessage(null);
                }}
                placeholder="例如：出差报销需要哪些材料？或查询我的报销状态。"
                rows={5}
                maxLength={2001}
                disabled={isPending}
                aria-describedby="assistant-request-guidance assistant-request-validation"
              />
              <div className="composer-footer">
                <span id="assistant-request-guidance">
                  {request.length.toLocaleString()} / 2,000 字
                </span>
                <button className="primary-button ask-button" type="submit" disabled={isPending}>
                  {isPending ? "正在处理…" : "发送请求"}
                </button>
              </div>
              {validationMessage && (
                <p id="assistant-request-validation" className="form-message error-message" role="alert">
                  {validationMessage}
                </p>
              )}
            </div>
          </form>
        </section>

        <section className="answer-panel" aria-live="polite" aria-busy={isPending}>
          {result.kind === "initial" && (
            <div className="answer-empty">
              <span aria-hidden="true">✦</span>
              <h2>处理结果将显示在这里</h2>
              <p>提交请求后查看结果；知识类回答会附上引用来源。</p>
            </div>
          )}

          {result.kind === "loading" && (
            <div className="answer-loading" role="status">
              <div className="thinking-mark" aria-hidden="true"><span /><span /><span /></div>
              <div>
                <p className="section-kicker">正在处理请求</p>
                <h2>正在分析你的请求</h2>
                <p className="submitted-question">“{result.request}”</p>
              </div>
            </div>
          )}

          {result.kind === "routed" && result.response.intent === "knowledge_qa" &&
            (result.response.outcome.status === "answered" ? (
              <article className="answer-content">
                <div className="answer-meta">
                  <span className="answer-status"><span aria-hidden="true">✓</span> 知识回答</span>
                  <span>{result.response.outcome.citations.length} 个来源</span>
                </div>
                <p className="answer-question">{result.response.request}</p>
                <div className="answer-copy">{result.response.outcome.answer}</div>
              </article>
            ) : (
              <div className="answer-state unsupported-state" role="status">
                <span className="state-icon" aria-hidden="true">?</span>
                <p className="section-kicker">知识问答 · 资料不足</p>
                <h2>当前知识库没有足够资料支持回答</h2>
                <p>{displayMessage(result.response.outcome.message ?? "检索到的资料不足以支持回答此问题。")}</p>
              </div>
            ))}

          {toolOutcome?.status === "not_executed" && (
            <div className="answer-state assistant-tool-state" role="status">
              <span className="state-icon" aria-hidden="true">↗</span>
              <p className="section-kicker">企业工具请求</p>
              <h2>未执行任何操作</h2>
              <p>{displayMessage(toolOutcome.message)}</p>
            </div>
          )}

          {toolOutcome?.status === "executed" && (
            <article className="answer-content assistant-tool-result" role="status">
              <div className="answer-meta">
                <span className="answer-status"><span aria-hidden="true">✓</span> 已执行</span>
                <span>只读查询结果 · 模拟服务</span>
              </div>
              <p className="section-kicker">{toolOutcome.tool.name}</p>
              <h2>业务查询已完成</h2>
              {toolOutcome.result.type === "reimbursement_status" ? (
                <dl className="tool-result-grid">
                  <div><dt>申请编号</dt><dd>{toolOutcome.result.reimbursement_reference}</dd></div>
                  <div><dt>状态</dt><dd>{formatEnumLabel(toolOutcome.result.status)}</dd></div>
                  <div><dt>金额</dt><dd>{(toolOutcome.result.amount_minor / 100).toFixed(2)} {toolOutcome.result.currency}</dd></div>
                  <div><dt>提交时间</dt><dd>{toolOutcome.result.submitted_on}</dd></div>
                  <div><dt>更新时间</dt><dd>{toolOutcome.result.last_updated_on}</dd></div>
                </dl>
              ) : (
                <dl className="tool-result-grid">
                  <div><dt>姓名</dt><dd>{toolOutcome.result.name}</dd></div>
                  <div><dt>邮箱</dt><dd>{toolOutcome.result.email}</dd></div>
                  <div><dt>部门</dt><dd>{toolOutcome.result.department}</dd></div>
                  <div><dt>职位</dt><dd>{toolOutcome.result.job_title}</dd></div>
                  <div><dt>在职状态</dt><dd>{formatEnumLabel(toolOutcome.result.employment_status)}</dd></div>
                </dl>
              )}
              <p className="tool-result-message">{displayMessage(toolOutcome.message)}</p>
            </article>
          )}

          {toolOutcome?.status === "approval_required" && (
            <article className="answer-content assistant-approval-result" role="status">
              <div className="answer-meta">
                <span className="approval-status">等待人工审批 · 尚未执行</span>
                <span>敏感操作 · 模拟服务</span>
              </div>
              <p className="section-kicker">{toolOutcome.tool.name}</p>
              <h2>此请求需要人工审批</h2>
              <dl className="tool-result-grid">
                <div><dt>目标系统</dt><dd>{formatEnumLabel(toolOutcome.validated_arguments.system)}</dd></div>
                <div><dt>访问级别</dt><dd>{formatEnumLabel(toolOutcome.validated_arguments.access_level)}</dd></div>
                <div><dt>有效期限</dt><dd>{toolOutcome.validated_arguments.duration_days} 天</dd></div>
                <div className="tool-result-wide"><dt>申请理由</dt><dd>{toolOutcome.validated_arguments.business_justification}</dd></div>
              </dl>
              <p className="approval-reference">
                审批编号 {toolOutcome.approval.id} · 审批决定 {formatEnumLabel(toolOutcome.approval.decision_status)} · 执行状态 {formatEnumLabel(toolOutcome.approval.execution_status)}
              </p>
              <p className="tool-result-message">{displayMessage(toolOutcome.message)}</p>
            </article>
          )}

          {result.kind === "routed" && result.response.intent === "unsupported" && (
            <div className="answer-state unsupported-state" role="status">
              <span className="state-icon" aria-hidden="true">?</span>
              <p className="section-kicker">超出智能体能力范围</p>
              <h2>当前智能体无法处理此请求</h2>
              <p>{displayMessage(result.response.outcome.message ?? "检索到的资料不足以支持回答此问题。")}</p>
            </div>
          )}

          {result.kind === "context_required" && (
            <div className="answer-state assistant-context-required" role="alert">
              <span className="state-icon" aria-hidden="true">⌑</span>
              <p className="section-kicker">需要知识库</p>
              <h2>请为此问题选择知识库</h2>
              <p>{displayMessage(KNOWLEDGE_CONTEXT_REQUIRED)}</p>
            </div>
          )}

          {result.kind === "error" && (
            <div className="answer-state error-state" role="alert">
              <span className="state-icon" aria-hidden="true">!</span>
              <p className="section-kicker">请求失败</p>
              <h2>{result.title}</h2>
              <p>{result.message}</p>
            </div>
          )}
        </section>
      </div>

      <aside className="sources-panel" aria-labelledby="assistant-sources-title">
        <div className="sources-heading">
          <div>
            <p className="section-kicker">引用资料</p>
            <h2 id="assistant-sources-title">引用来源</h2>
          </div>
          {answeredOutcome && <span>{answeredOutcome.citations.length}</span>}
        </div>

        {!answeredOutcome ? (
          <div className="sources-empty">
            <span aria-hidden="true">⌑</span>
            <p>知识类问题得到有依据的回答后，引用来源会显示在这里。</p>
          </div>
        ) : (
          <>
            <div className="citation-list" aria-label="回答引用">
              {answeredOutcome.citations.map((citation, index) => (
                <button
                  key={`${citation.chunk_id}-${index}`}
                  type="button"
                  className={`citation-card ${selectedCitationIndex === index ? "selected" : ""}`}
                  onClick={() => setSelectedCitationIndex(index)}
                  aria-pressed={selectedCitationIndex === index}
                >
                  <span className="citation-number">{index + 1}</span>
                  <span className="citation-summary">
                    <strong>{citation.file_name}</strong>
                    <small>片段 {citation.chunk_index + 1} · 版本 {citation.document_version}</small>
                    <span>{citation.excerpt}</span>
                  </span>
                </button>
              ))}
            </div>
            {selectedCitation && (
              <section className="source-inspector" aria-label={selectedCitation.file_name}>
                <p className="section-kicker">原文摘录</p>
                <h3>{selectedCitation.file_name}</h3>
                <p className="source-location">
                  片段 {selectedCitation.chunk_index + 1} · 文档版本 {selectedCitation.document_version}
                </p>
                <blockquote>{selectedCitation.excerpt}</blockquote>
                <p className="verified-note"><span aria-hidden="true">✓</span> 以下摘录来自检索到的原始资料</p>
              </section>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
