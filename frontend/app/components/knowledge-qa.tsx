"use client";

import { displayMessage, formatEnumLabel } from "@/utils/presentation";

import { FormEvent, useMemo, useState } from "react";

import {
  ApiError,
  GroundedAnswerResponse,
  KnowledgeBase,
  answerKnowledgeQuestion,
} from "@/utils/api";

type ResultState =
  | { kind: "initial" }
  | { kind: "loading"; question: string }
  | { kind: "answered"; response: GroundedAnswerResponse }
  | { kind: "unsupported"; response: GroundedAnswerResponse }
  | { kind: "forbidden"; message: string }
  | { kind: "disabled"; message: string }
  | { kind: "error"; message: string };

interface KnowledgeQAProps {
  workspaceId: string;
  workspaceName: string;
  knowledgeBases: KnowledgeBase[];
  knowledgeBasesPending: boolean;
  knowledgeBasesError: KnowledgeBasesLoadFailure;
  accessToken: string;
  onUnauthorized: () => void;
  onPendingChange: (pending: boolean) => void;
}

export type KnowledgeBasesLoadFailure =
  | { kind: "forbidden"; message: string }
  | { kind: "error"; message: string }
  | null;

function chunkLabel(chunkIndex: number): string {
  return `片段 ${chunkIndex + 1}`;
}

export function KnowledgeQA({
  workspaceId,
  workspaceName,
  knowledgeBases,
  knowledgeBasesPending,
  knowledgeBasesError,
  accessToken,
  onUnauthorized,
  onPendingChange,
}: KnowledgeQAProps) {
  const firstAvailableId =
    knowledgeBases.find((knowledgeBase) => knowledgeBase.status === "active")?.id ??
    knowledgeBases[0]?.id ??
    "";
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState(firstAvailableId);
  const [question, setQuestion] = useState("");
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ResultState>({ kind: "initial" });
  const [selectedCitationIndex, setSelectedCitationIndex] = useState(0);

  const selectedKnowledgeBase = useMemo(
    () =>
      knowledgeBases.find((item) => item.id === selectedKnowledgeBaseId) ??
      knowledgeBases.find((item) => item.status === "active") ??
      knowledgeBases[0] ??
      null,
    [knowledgeBases, selectedKnowledgeBaseId],
  );
  const isPending = result.kind === "loading";
  const answeredResponse = result.kind === "answered" ? result.response : null;
  const selectedCitation = answeredResponse?.citations[selectedCitationIndex] ?? null;

  function selectKnowledgeBase(knowledgeBaseId: string) {
    setSelectedKnowledgeBaseId(knowledgeBaseId);
    setValidationMessage(null);
    setResult({ kind: "initial" });
    setSelectedCitationIndex(0);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isPending || !selectedKnowledgeBase) return;

    const normalizedQuestion = question.trim();
    if (normalizedQuestion.length === 0) {
      setValidationMessage("请先输入问题。");
      return;
    }
    if (normalizedQuestion.length > 2000) {
      setValidationMessage("问题不能超过 2,000 字。");
      return;
    }
    if (selectedKnowledgeBase.status === "disabled") {
      setResult({
        kind: "disabled",
        message: "此知识库已停用，暂时无法回答问题。",
      });
      return;
    }

    setValidationMessage(null);
    setResult({ kind: "loading", question: normalizedQuestion });
    onPendingChange(true);

    answerKnowledgeQuestion(
      workspaceId,
      selectedKnowledgeBase.id,
      normalizedQuestion,
      accessToken,
    )
      .then((response) => {
        setSelectedCitationIndex(0);
        setResult(
          response.status === "answered"
            ? { kind: "answered", response }
            : { kind: "unsupported", response },
        );
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          onUnauthorized();
          return;
        }
        if (error instanceof ApiError && error.status === 403) {
          setResult({
            kind: "forbidden",
            message: "你已没有访问此知识库的权限。",
          });
        } else if (error instanceof ApiError && error.status === 409) {
          setResult({
            kind: "disabled",
            message: "此知识库已停用或暂不可用。",
          });
        } else {
          setResult({
            kind: "error",
            message:
              error instanceof ApiError
                ? displayMessage(error.message, error.status)
                : "暂时无法获得回答，请稍后重试。",
          });
        }
      })
      .finally(() => onPendingChange(false));
  }

  if (knowledgeBasesPending) {
    return (
      <section className="qa-loading-shell" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>正在加载知识库</strong>
          <p>正在加载 {workspaceName} 中可访问的资料。</p>
        </div>
      </section>
    );
  }

  if (knowledgeBasesError) {
    if (knowledgeBasesError.kind === "forbidden") {
      return (
        <section className="qa-state-card error-state" role="alert">
          <span className="state-icon" aria-hidden="true">×</span>
          <div>
            <p className="section-kicker">访问权限不足</p>
            <h2>你没有当前空间的知识问答访问权限</h2>
            <p>{knowledgeBasesError.message}</p>
          </div>
        </section>
      );
    }

    return (
      <section className="qa-state-card error-state" role="alert">
        <span className="state-icon" aria-hidden="true">!</span>
        <div>
          <p className="section-kicker">知识问答暂不可用</p>
          <h2>无法加载知识库</h2>
          <p>{knowledgeBasesError.message}</p>
        </div>
      </section>
    );
  }

  if (knowledgeBases.length === 0) {
    return (
      <section className="qa-state-card" aria-labelledby="no-knowledge-bases-title">
        <span className="state-icon" aria-hidden="true">◇</span>
        <div>
          <p className="section-kicker">知识问答</p>
          <h2 id="no-knowledge-bases-title">暂无可用知识库</h2>
          <p>请联系知识管理员，为当前工作空间添加可访问的知识库。</p>
        </div>
      </section>
    );
  }

  return (
    <div className="qa-layout">
      <div className="qa-main-column">
        <section className="qa-context-card" aria-labelledby="qa-title">
          <div className="qa-heading-row">
            <div>
              <p className="section-kicker">知识问答</p>
              <h2 id="qa-title">向企业知识库提问</h2>
              <p className="muted">回答仅使用从所选知识库中检索到的依据。</p>
            </div>
            <span className="grounded-badge">
              <span aria-hidden="true">●</span>有据可查</span>
          </div>

          <label htmlFor="knowledge-base">知识库</label>
          <div className="knowledge-select-wrap">
            <select
              id="knowledge-base"
              value={selectedKnowledgeBase?.id ?? ""}
              onChange={(event) => selectKnowledgeBase(event.target.value)}
              disabled={isPending}
            >
              {knowledgeBases.map((knowledgeBase) => (
                <option key={knowledgeBase.id} value={knowledgeBase.id}>
                  {knowledgeBase.name}
                  {knowledgeBase.status === "disabled" ? " — 已停用" : ""}
                </option>
              ))}
            </select>
            {selectedKnowledgeBase && (
              <span
                className={`kb-status kb-status-${selectedKnowledgeBase.status}`}
              >
                {formatEnumLabel(selectedKnowledgeBase.status)}
              </span>
            )}
          </div>
          {selectedKnowledgeBase?.description && (
            <p className="knowledge-description">{selectedKnowledgeBase.description}</p>
          )}

          {selectedKnowledgeBase?.status === "disabled" ? (
            <div className="inline-state disabled-state" role="status">
              <strong>知识库已停用</strong>
              <p>请选择已启用的知识库进行提问。</p>
            </div>
          ) : (
            <form className="question-form" onSubmit={handleSubmit}>
              <label htmlFor="question">问题</label>
              <textarea
                id="question"
                value={question}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  if (validationMessage) setValidationMessage(null);
                }}
                placeholder="例如：差旅报销需要准备哪些材料？"
                rows={5}
                maxLength={2001}
                disabled={isPending}
                aria-describedby="question-guidance question-validation"
              />
              <div className="composer-footer">
                <span id="question-guidance">
                  {question.length.toLocaleString()} / 2,000 字
                </span>
                <button className="primary-button ask-button" type="submit" disabled={isPending}>
                  {isPending ? (
                    <><span className="button-spinner" aria-hidden="true" /> 正在查找答案…</>
                  ) : (
                    <>提交问题<span aria-hidden="true">→</span></>
                  )}
                </button>
              </div>
              {validationMessage && (
                <p id="question-validation" className="form-message error-message" role="alert">
                  {validationMessage}
                </p>
              )}
            </form>
          )}
        </section>

        <section className="answer-panel" aria-live="polite" aria-busy={isPending}>
          {result.kind === "initial" && (
            <div className="answer-empty">
              <span aria-hidden="true">✦</span>
              <h2>有依据的回答将显示在这里</h2>
              <p>
                提出一个清晰的问题。有依据的回答会附上支持结论的原文摘录。
              </p>
            </div>
          )}

          {result.kind === "loading" && (
            <div className="answer-loading" role="status">
              <div className="thinking-mark" aria-hidden="true"><span /><span /><span /></div>
              <div>
                <p className="section-kicker">正在检索可访问的资料</p>
                <h2>正在整理回答与引用</h2>
                <p className="submitted-question">“{result.question}”</p>
              </div>
            </div>
          )}

          {result.kind === "answered" && (
            <article className="answer-content">
              <div className="answer-meta">
                <span className="answer-status"><span aria-hidden="true">✓</span> 已回答</span>
                <span>{result.response.citations.length} 个来源</span>
              </div>
              <p className="answer-question">{result.response.question}</p>
              <div className="answer-copy">{result.response.answer}</div>
            </article>
          )}

          {result.kind === "unsupported" && (
            <div className="answer-state unsupported-state" role="status">
              <span className="state-icon" aria-hidden="true">?</span>
              <p className="section-kicker">资料不足</p>
              <h2>当前知识库没有足够资料支持回答</h2>
              <p>{displayMessage(result.response.message ?? "检索到的资料不足以支持回答此问题。")}</p>
            </div>
          )}

          {result.kind === "forbidden" && (
            <div className="answer-state error-state" role="alert">
              <span className="state-icon" aria-hidden="true">×</span>
              <p className="section-kicker">访问权限不足</p>
              <h2>你无法使用此知识库</h2>
              <p>{result.message}</p>
            </div>
          )}

          {result.kind === "disabled" && (
            <div className="answer-state disabled-state" role="status">
              <span className="state-icon" aria-hidden="true">—</span>
              <p className="section-kicker">知识库暂不可用</p>
              <h2>此知识库暂时无法接受提问</h2>
              <p>{result.message}</p>
            </div>
          )}

          {result.kind === "error" && (
            <div className="answer-state error-state" role="alert">
              <span className="state-icon" aria-hidden="true">!</span>
              <p className="section-kicker">请求失败</p>
              <h2>暂时无法获得回答</h2>
              <p>{result.message}</p>
            </div>
          )}
        </section>
      </div>

      <aside className="sources-panel" aria-labelledby="sources-title">
        <div className="sources-heading">
          <div>
            <p className="section-kicker">引用资料</p>
            <h2 id="sources-title">引用来源</h2>
          </div>
          {answeredResponse && <span>{answeredResponse.citations.length}</span>}
        </div>

        {!answeredResponse ? (
          <div className="sources-empty">
            <span aria-hidden="true">⌑</span>
            <p>回答完成后，相关引用来源会显示在这里。</p>
          </div>
        ) : (
          <>
            <div className="citation-list" aria-label="回答引用">
              {answeredResponse.citations.map((citation, index) => (
                <button
                  type="button"
                  className={`citation-card ${selectedCitationIndex === index ? "selected" : ""}`}
                  key={`${citation.chunk_id}-${index}`}
                  onClick={() => setSelectedCitationIndex(index)}
                  aria-pressed={selectedCitationIndex === index}
                >
                  <span className="citation-number">{index + 1}</span>
                  <span className="citation-summary">
                    <strong>{citation.file_name}</strong>
                    <small>{chunkLabel(citation.chunk_index)} · 版本 {citation.document_version}</small>
                    <span>{citation.excerpt}</span>
                  </span>
                </button>
              ))}
            </div>

            {selectedCitation && (
              <section className="source-inspector" aria-labelledby="source-inspector-title">
                <p className="section-kicker">原文摘录</p>
                <h3 id="source-inspector-title">{selectedCitation.file_name}</h3>
                <p className="source-location">
                  {chunkLabel(selectedCitation.chunk_index)} · 文档版本 {selectedCitation.document_version}
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
