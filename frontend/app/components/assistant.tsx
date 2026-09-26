"use client";

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
}: AssistantProps) {
  const activeAgents = agents.filter((agent) => agent.status === "active");
  const activeKnowledgeBases = knowledgeBases.filter((base) => base.status === "active");
  const [selectedAgentId, setSelectedAgentId] = useState(
    activeAgents[0]?.id ?? "",
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
      setValidationMessage("Enter a request before asking the Assistant.");
      return;
    }
    if (normalizedRequest.length > 2000) {
      setValidationMessage("Keep your request to 2,000 characters or fewer.");
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
            error.status === 403 ? "Assistant access denied" :
            error.status === 404 ? "Agent or knowledge context not found" :
            error.status === 409 ? "Agent or knowledge context unavailable" :
            error.status === 422 ? "Request needs revision" :
            error.status === 502 || error.status === 503 ? "Assistant service unavailable" :
            error.status === 0 ? "Connection unavailable" :
            "Assistant request failed";
          setResult({ kind: "error", title, message: error.message });
          return;
        }
        setResult({
          kind: "error",
          title: "Assistant request failed",
          message: "We could not process this request. Try again in a moment.",
        });
      })
      .finally(() => onPendingChange(false));
  }

  if (agentsPending) {
    return (
      <section className="qa-loading-shell" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>Loading active agents</strong>
          <p>Preparing the available Assistants for {workspaceName}.</p>
        </div>
      </section>
    );
  }

  if (agentsError) {
    return (
      <section className="qa-state-card error-state" role="alert">
        <span className="state-icon" aria-hidden="true">!</span>
        <div>
          <p className="section-kicker">Assistant unavailable</p>
          <h2>{agentsError.kind === "forbidden" ? "Assistant access denied" : "We could not load active agents"}</h2>
          <p>{agentsError.message}</p>
          <button className="assistant-retry-button" type="button" onClick={onRetryAgents}>
            Try again
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
          <p className="section-kicker">Assistant</p>
          <h2 id="no-agents-title">No active agents are available</h2>
          <p>Ask an Agent administrator to activate an Agent in this workspace.</p>
          <button className="assistant-retry-button" type="button" onClick={onRetryAgents}>
            Refresh agents
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
              <p className="section-kicker">Assistant</p>
              <h2 id="assistant-title">Route an enterprise request</h2>
              <p className="muted">
                Ask one request. The Agent will identify whether it needs knowledge,
                an enterprise tool, or is outside its scope.
              </p>
            </div>
            <span className="grounded-badge">Single request</span>
          </div>

          <form className="assistant-form" onSubmit={handleSubmit}>
            <div className="assistant-context-grid">
              <div>
                <label htmlFor="assistant-agent">Agent</label>
                <select
                  id="assistant-agent"
                  value={selectedAgent.id}
                  onChange={(event) => {
                    setSelectedAgentId(event.target.value);
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
                <label htmlFor="assistant-knowledge-base">Knowledge context (optional)</label>
                <select
                  id="assistant-knowledge-base"
                  value={selectedKnowledgeBase?.id ?? ""}
                  onChange={(event) => {
                    setSelectedKnowledgeBaseId(event.target.value);
                    resetResult();
                  }}
                  disabled={isPending}
                >
                  <option value="">No knowledge context</option>
                  {activeKnowledgeBases.map((base) => (
                    <option key={base.id} value={base.id}>{base.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {(knowledgeBasesError || activeKnowledgeBases.length === 0 || !selectedKnowledgeBase) && (
              <p className="assistant-context-guidance" role="status">
                {knowledgeBasesError
                  ? "Knowledge contexts could not be loaded. Requests for tools or outside this Agent's scope can still be routed."
                  : activeKnowledgeBases.length === 0
                    ? "No active knowledge base is available. Requests for tools or outside this Agent's scope can still be routed."
                    : "No knowledge context selected. Knowledge questions will need an active knowledge base."}
              </p>
            )}

            <div className="question-form">
              <label htmlFor="assistant-request">Request</label>
              <textarea
                id="assistant-request"
                value={request}
                onChange={(event) => {
                  setRequest(event.target.value);
                  if (validationMessage) setValidationMessage(null);
                }}
                placeholder="Ask about a policy, business status, or enterprise service…"
                rows={5}
                maxLength={2001}
                disabled={isPending}
                aria-describedby="assistant-request-guidance assistant-request-validation"
              />
              <div className="composer-footer">
                <span id="assistant-request-guidance">
                  {request.length.toLocaleString()} / 2,000 characters
                </span>
                <button className="primary-button ask-button" type="submit" disabled={isPending}>
                  {isPending ? "Routing request…" : "Route request"}
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
              <h2>Your Assistant result will appear here</h2>
              <p>Each request receives one routed result. Knowledge answers show their sources.</p>
            </div>
          )}

          {result.kind === "loading" && (
            <div className="answer-loading" role="status">
              <div className="thinking-mark" aria-hidden="true"><span /><span /><span /></div>
              <div>
                <p className="section-kicker">Routing request</p>
                <h2>Reviewing your request</h2>
                <p className="submitted-question">“{result.request}”</p>
              </div>
            </div>
          )}

          {result.kind === "routed" && result.response.intent === "knowledge_qa" &&
            (result.response.outcome.status === "answered" ? (
              <article className="answer-content">
                <div className="answer-meta">
                  <span className="answer-status"><span aria-hidden="true">✓</span> Knowledge answer</span>
                  <span>{result.response.outcome.citations.length} source{result.response.outcome.citations.length === 1 ? "" : "s"}</span>
                </div>
                <p className="answer-question">{result.response.request}</p>
                <div className="answer-copy">{result.response.outcome.answer}</div>
              </article>
            ) : (
              <div className="answer-state unsupported-state" role="status">
                <span className="state-icon" aria-hidden="true">?</span>
                <p className="section-kicker">Knowledge question · insufficient evidence</p>
                <h2>The selected knowledge base cannot support an answer</h2>
                <p>{result.response.outcome.message}</p>
              </div>
            ))}

          {result.kind === "routed" && result.response.intent === "tool_request" && (
            <div className="answer-state assistant-tool-state" role="status">
              <span className="state-icon" aria-hidden="true">↗</span>
              <p className="section-kicker">Enterprise tool required</p>
              <h2>No action was executed</h2>
              <p>{result.response.outcome.message}</p>
            </div>
          )}

          {result.kind === "routed" && result.response.intent === "unsupported" && (
            <div className="answer-state unsupported-state" role="status">
              <span className="state-icon" aria-hidden="true">?</span>
              <p className="section-kicker">Outside Agent scope</p>
              <h2>This Agent cannot handle that request</h2>
              <p>{result.response.outcome.message}</p>
            </div>
          )}

          {result.kind === "context_required" && (
            <div className="answer-state assistant-context-required" role="alert">
              <span className="state-icon" aria-hidden="true">⌑</span>
              <p className="section-kicker">Knowledge context required</p>
              <h2>Select a knowledge base for this question</h2>
              <p>{KNOWLEDGE_CONTEXT_REQUIRED}</p>
            </div>
          )}

          {result.kind === "error" && (
            <div className="answer-state error-state" role="alert">
              <span className="state-icon" aria-hidden="true">!</span>
              <p className="section-kicker">Request failed</p>
              <h2>{result.title}</h2>
              <p>{result.message}</p>
            </div>
          )}
        </section>
      </div>

      <aside className="sources-panel" aria-labelledby="assistant-sources-title">
        <div className="sources-heading">
          <div>
            <p className="section-kicker">Evidence</p>
            <h2 id="assistant-sources-title">Citations</h2>
          </div>
          {answeredOutcome && <span>{answeredOutcome.citations.length}</span>}
        </div>

        {!answeredOutcome ? (
          <div className="sources-empty">
            <span aria-hidden="true">⌑</span>
            <p>Citations appear only when a knowledge question has a grounded answer.</p>
          </div>
        ) : (
          <>
            <div className="citation-list" aria-label="Answer citations">
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
                    <small>Chunk {citation.chunk_index + 1} · Version {citation.document_version}</small>
                    <span>{citation.excerpt}</span>
                  </span>
                </button>
              ))}
            </div>
            {selectedCitation && (
              <section className="source-inspector" aria-label={selectedCitation.file_name}>
                <p className="section-kicker">Selected source</p>
                <h3>{selectedCitation.file_name}</h3>
                <p className="source-location">
                  Chunk {selectedCitation.chunk_index + 1} · Document version {selectedCitation.document_version}
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
