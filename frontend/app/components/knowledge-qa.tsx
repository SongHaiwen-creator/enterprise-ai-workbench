"use client";

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
  return `Chunk ${chunkIndex + 1}`;
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
      setValidationMessage("Enter a question before asking the knowledge base.");
      return;
    }
    if (normalizedQuestion.length > 2000) {
      setValidationMessage("Keep your question to 2,000 characters or fewer.");
      return;
    }
    if (selectedKnowledgeBase.status === "disabled") {
      setResult({
        kind: "disabled",
        message: "This knowledge base is disabled and cannot answer questions.",
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
            message: "You no longer have access to ask this knowledge base.",
          });
        } else if (error instanceof ApiError && error.status === 409) {
          setResult({
            kind: "disabled",
            message: "This knowledge base is disabled or unavailable for questions.",
          });
        } else {
          setResult({
            kind: "error",
            message:
              error instanceof ApiError
                ? error.message
                : "We could not get an answer. Try again in a moment.",
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
          <strong>Loading knowledge bases</strong>
          <p>Preparing the authorized sources for {workspaceName}.</p>
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
            <p className="section-kicker">Access denied</p>
            <h2>You cannot access Knowledge Q&A in this workspace</h2>
            <p>{knowledgeBasesError.message}</p>
          </div>
        </section>
      );
    }

    return (
      <section className="qa-state-card error-state" role="alert">
        <span className="state-icon" aria-hidden="true">!</span>
        <div>
          <p className="section-kicker">Knowledge Q&A unavailable</p>
          <h2>We could not load your knowledge bases</h2>
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
          <p className="section-kicker">Knowledge Q&A</p>
          <h2 id="no-knowledge-bases-title">No knowledge bases are available</h2>
          <p>
            Ask a knowledge administrator to add an authorized knowledge base to this
            workspace.
          </p>
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
              <p className="section-kicker">Knowledge Q&A</p>
              <h2 id="qa-title">Ask your enterprise knowledge</h2>
              <p className="muted">
                Answers use only evidence retrieved from the selected knowledge base.
              </p>
            </div>
            <span className="grounded-badge">
              <span aria-hidden="true">●</span> Grounded response
            </span>
          </div>

          <label htmlFor="knowledge-base">Knowledge base</label>
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
                  {knowledgeBase.status === "disabled" ? " — Disabled" : ""}
                </option>
              ))}
            </select>
            {selectedKnowledgeBase && (
              <span
                className={`kb-status kb-status-${selectedKnowledgeBase.status}`}
              >
                {selectedKnowledgeBase.status}
              </span>
            )}
          </div>
          {selectedKnowledgeBase?.description && (
            <p className="knowledge-description">{selectedKnowledgeBase.description}</p>
          )}

          {selectedKnowledgeBase?.status === "disabled" ? (
            <div className="inline-state disabled-state" role="status">
              <strong>Knowledge base disabled</strong>
              <p>Select an active knowledge base to ask a question.</p>
            </div>
          ) : (
            <form className="question-form" onSubmit={handleSubmit}>
              <label htmlFor="question">Question</label>
              <textarea
                id="question"
                value={question}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  if (validationMessage) setValidationMessage(null);
                }}
                placeholder="Ask a specific question about policies, procedures, or internal guidance…"
                rows={5}
                maxLength={2001}
                disabled={isPending}
                aria-describedby="question-guidance question-validation"
              />
              <div className="composer-footer">
                <span id="question-guidance">
                  {question.length.toLocaleString()} / 2,000 characters
                </span>
                <button className="primary-button ask-button" type="submit" disabled={isPending}>
                  {isPending ? (
                    <><span className="button-spinner" aria-hidden="true" /> Finding answer…</>
                  ) : (
                    <>Ask knowledge <span aria-hidden="true">→</span></>
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
              <h2>Your grounded answer will appear here</h2>
              <p>
                Ask one clear question. Every supported answer includes the exact source
                excerpts used to generate it.
              </p>
            </div>
          )}

          {result.kind === "loading" && (
            <div className="answer-loading" role="status">
              <div className="thinking-mark" aria-hidden="true"><span /><span /><span /></div>
              <div>
                <p className="section-kicker">Reviewing authorized sources</p>
                <h2>Building a grounded answer</h2>
                <p className="submitted-question">“{result.question}”</p>
              </div>
            </div>
          )}

          {result.kind === "answered" && (
            <article className="answer-content">
              <div className="answer-meta">
                <span className="answer-status"><span aria-hidden="true">✓</span> Answered</span>
                <span>{result.response.citations.length} source{result.response.citations.length === 1 ? "" : "s"}</span>
              </div>
              <p className="answer-question">{result.response.question}</p>
              <div className="answer-copy">{result.response.answer}</div>
            </article>
          )}

          {result.kind === "unsupported" && (
            <div className="answer-state unsupported-state" role="status">
              <span className="state-icon" aria-hidden="true">?</span>
              <p className="section-kicker">Insufficient evidence</p>
              <h2>This knowledge base cannot support an answer</h2>
              <p>{result.response.message ?? "The retrieved knowledge does not contain enough evidence to answer this question."}</p>
            </div>
          )}

          {result.kind === "forbidden" && (
            <div className="answer-state error-state" role="alert">
              <span className="state-icon" aria-hidden="true">×</span>
              <p className="section-kicker">Access denied</p>
              <h2>You cannot use this knowledge base</h2>
              <p>{result.message}</p>
            </div>
          )}

          {result.kind === "disabled" && (
            <div className="answer-state disabled-state" role="status">
              <span className="state-icon" aria-hidden="true">—</span>
              <p className="section-kicker">Knowledge base unavailable</p>
              <h2>Questions are disabled for this source</h2>
              <p>{result.message}</p>
            </div>
          )}

          {result.kind === "error" && (
            <div className="answer-state error-state" role="alert">
              <span className="state-icon" aria-hidden="true">!</span>
              <p className="section-kicker">Request failed</p>
              <h2>We could not get an answer</h2>
              <p>{result.message}</p>
            </div>
          )}
        </section>
      </div>

      <aside className="sources-panel" aria-labelledby="sources-title">
        <div className="sources-heading">
          <div>
            <p className="section-kicker">Evidence</p>
            <h2 id="sources-title">Citations</h2>
          </div>
          {answeredResponse && <span>{answeredResponse.citations.length}</span>}
        </div>

        {!answeredResponse ? (
          <div className="sources-empty">
            <span aria-hidden="true">⌑</span>
            <p>Supporting sources will appear with an answered response.</p>
          </div>
        ) : (
          <>
            <div className="citation-list" aria-label="Answer citations">
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
                    <small>{chunkLabel(citation.chunk_index)} · Version {citation.document_version}</small>
                    <span>{citation.excerpt}</span>
                  </span>
                </button>
              ))}
            </div>

            {selectedCitation && (
              <section className="source-inspector" aria-labelledby="source-inspector-title">
                <p className="section-kicker">Selected source</p>
                <h3 id="source-inspector-title">{selectedCitation.file_name}</h3>
                <p className="source-location">
                  {chunkLabel(selectedCitation.chunk_index)} · Document version {selectedCitation.document_version}
                </p>
                <blockquote>{selectedCitation.excerpt}</blockquote>
                <p className="verified-note"><span aria-hidden="true">✓</span> Verified excerpt from the retrieved source</p>
              </section>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
