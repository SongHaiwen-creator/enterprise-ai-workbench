"use client";

import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  ApprovalDecisionStatus,
  ApprovalExecutionStatus,
  ApprovalResponse,
  ApprovalScope,
  decideApproval,
  getApproval,
  listApprovals,
} from "@/utils/api";

const DECISION_LABELS: Record<ApprovalDecisionStatus, string> = {
  pending: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
  expired: "Expired",
  invalidated: "Invalidated",
};

const EXECUTION_LABELS: Record<ApprovalExecutionStatus, string> = {
  not_started: "Not executed",
  succeeded: "Executed",
  failed: "Execution failed",
};

const INVALIDATION_LABELS = {
  requester_ineligible: "The requester is no longer eligible.",
  capability_unavailable: "The Agent or Tool is no longer available.",
  configuration_drift: "The Tool configuration changed after the request.",
} as const;

type Failure = { title: string; message: string };

type ListState =
  | { kind: "loading" }
  | { kind: "loaded"; items: ApprovalResponse[] }
  | { kind: "error"; failure: Failure };

type DetailState =
  | { kind: "none" }
  | { kind: "loading" }
  | { kind: "loaded"; approval: ApprovalResponse }
  | { kind: "error"; failure: Failure };

type ActionMessage = { tone: "success" | "error"; title: string; message: string } | null;

interface ApprovalsProps {
  workspaceId: string;
  workspaceName: string;
  currentUserId: string;
  canReview: boolean;
  accessToken: string;
  onUnauthorized: () => void;
  onPendingChange: (pending: boolean) => void;
}

function failureFor(error: unknown): Failure {
  if (!(error instanceof ApiError)) {
    return {
      title: "Approval request failed",
      message: "We could not complete this request. Try again in a moment.",
    };
  }
  const title =
    error.status === 403 ? "Approval access denied" :
    error.status === 404 ? "Approval not found" :
    error.status === 409 ? "Approval changed" :
    error.status === 422 ? "Decision needs revision" :
    error.status === 502 ? "Execution failed" :
    error.status === 503 ? "Approval service unavailable" :
    error.status === 0 ? "Connection unavailable" :
    "Approval request failed";
  return { title, message: error.message };
}

function formatTimestamp(value: string): string {
  return `${new Date(value).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function formatValue(value: string): string {
  return value.replaceAll("_", " ");
}

function StatusLabels({ approval }: { approval: ApprovalResponse }) {
  return (
    <span className="approval-status-labels">
      <span className={`approval-label decision-${approval.decision_status}`}>
        <span className="sr-only">Decision: </span>
        {DECISION_LABELS[approval.decision_status]}
      </span>
      <span className={`approval-label execution-${approval.execution_status}`}>
        <span className="sr-only">Execution: </span>
        {EXECUTION_LABELS[approval.execution_status]}
      </span>
    </span>
  );
}

export function Approvals({
  workspaceId,
  workspaceName,
  currentUserId,
  canReview,
  accessToken,
  onUnauthorized,
  onPendingChange,
}: ApprovalsProps) {
  const [scope, setScope] = useState<ApprovalScope>(canReview ? "review" : "mine");
  const [list, setList] = useState<ListState>({ kind: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailState>({ kind: "none" });
  const [note, setNote] = useState("");
  const [actionPending, setActionPending] = useState(false);
  const [actionMessage, setActionMessage] = useState<ActionMessage>(null);
  const listGeneration = useRef(0);
  const detailGeneration = useRef(0);

  async function fetchList(nextScope: ApprovalScope, generation: number) {
    try {
      const response = await listApprovals(workspaceId, nextScope, accessToken);
      if (generation !== listGeneration.current) return;
      setList({ kind: "loaded", items: response.items });
    } catch (error) {
      if (generation !== listGeneration.current) return;
      if (error instanceof ApiError && error.status === 401) {
        onUnauthorized();
        return;
      }
      setList({ kind: "error", failure: failureFor(error) });
    }
  }

  function loadList(nextScope: ApprovalScope) {
    const generation = ++listGeneration.current;
    setList({ kind: "loading" });
    void fetchList(nextScope, generation);
  }

  async function loadDetail(approvalId: string) {
    const generation = ++detailGeneration.current;
    setDetail({ kind: "loading" });
    try {
      const approval = await getApproval(workspaceId, approvalId, accessToken);
      if (generation !== detailGeneration.current) return;
      setDetail({ kind: "loaded", approval });
    } catch (error) {
      if (generation !== detailGeneration.current) return;
      if (error instanceof ApiError && error.status === 401) {
        onUnauthorized();
        return;
      }
      setDetail({ kind: "error", failure: failureFor(error) });
    }
  }

  useEffect(() => {
    // The initial state is already "loading"; load once per mounted Workspace.
    void fetchList(scope, ++listGeneration.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function changeScope(nextScope: ApprovalScope) {
    if (actionPending || nextScope === scope) return;
    setScope(nextScope);
    setSelectedId(null);
    detailGeneration.current += 1;
    setDetail({ kind: "none" });
    setActionMessage(null);
    loadList(nextScope);
  }

  function selectApproval(approvalId: string) {
    if (actionPending) return;
    setSelectedId(approvalId);
    setNote("");
    setActionMessage(null);
    void loadDetail(approvalId);
  }

  async function submitDecision(decision: "approve" | "reject") {
    if (actionPending || detail.kind !== "loaded") return;
    const approvalId = detail.approval.id;
    const normalizedNote = note.trim();
    if (normalizedNote.length > 1000) {
      setActionMessage({
        tone: "error",
        title: "Decision needs revision",
        message: "Keep the note to 1,000 characters or fewer.",
      });
      return;
    }

    setActionPending(true);
    setActionMessage(null);
    onPendingChange(true);
    try {
      await decideApproval(
        workspaceId, approvalId, decision, normalizedNote || null, accessToken,
      );
      setActionMessage({
        tone: "success",
        title: decision === "approve" ? "Approval recorded" : "Rejection recorded",
        message: "The decision was saved.",
      });
      setNote("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        onUnauthorized();
        return;
      }
      setActionMessage({ tone: "error", ...failureFor(error) });
    } finally {
      setActionPending(false);
      onPendingChange(false);
    }
    // Always re-read server state; the client never infers the outcome.
    void loadDetail(approvalId);
    loadList(scope);
  }

  const approval = detail.kind === "loaded" ? detail.approval : null;
  const canDecide =
    approval !== null &&
    canReview &&
    approval.requester.id !== currentUserId &&
    approval.decision_status === "pending";

  return (
    <div className="qa-layout approvals-layout">
      <div className="qa-main-column">
        <section className="qa-context-card" aria-labelledby="approvals-title">
          <div className="qa-heading-row">
            <div>
              <p className="section-kicker">Human approval</p>
              <h2 id="approvals-title">Approvals</h2>
              <p className="muted">
                Sensitive requests in {workspaceName} wait here until an authorized
                reviewer decides.
              </p>
            </div>
          </div>
          <div className="approval-scope" role="group" aria-label="Approval list">
            <button
              type="button"
              className={scope === "mine" ? "scope-button active" : "scope-button"}
              aria-pressed={scope === "mine"}
              onClick={() => changeScope("mine")}
              disabled={actionPending}
            >
              My requests
            </button>
            {canReview && (
              <button
                type="button"
                className={scope === "review" ? "scope-button active" : "scope-button"}
                aria-pressed={scope === "review"}
                onClick={() => changeScope("review")}
                disabled={actionPending}
              >
                Review queue
              </button>
            )}
          </div>

          {list.kind === "loading" && (
            <p className="approval-list-state" role="status">Loading approvals…</p>
          )}
          {list.kind === "error" && (
            <div className="approval-list-state error-state" role="alert">
              <strong>{list.failure.title}</strong>
              <p>{list.failure.message}</p>
            </div>
          )}
          {list.kind === "loaded" && list.items.length === 0 && (
            <p className="approval-list-state">No approvals to show.</p>
          )}
          {list.kind === "loaded" && list.items.length > 0 && (
            <ul className="approval-list" aria-label="Approvals">
              {list.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={item.id === selectedId ? "approval-item selected" : "approval-item"}
                    aria-pressed={item.id === selectedId}
                    onClick={() => selectApproval(item.id)}
                    disabled={actionPending}
                  >
                    <span className="approval-item-title">
                      <strong>{item.tool.name}</strong>
                      <small>{item.requester.name} · {formatTimestamp(item.created_at)}</small>
                    </span>
                    <StatusLabels approval={item} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <aside className="sources-panel approval-detail" aria-labelledby="approval-detail-title">
        <div className="sources-heading">
          <div>
            <p className="section-kicker">Details</p>
            <h2 id="approval-detail-title">Approval</h2>
          </div>
        </div>

        {detail.kind === "none" && (
          <div className="sources-empty">
            <p>Select an approval to see what was requested.</p>
          </div>
        )}
        {detail.kind === "loading" && <p role="status">Loading approval…</p>}
        {detail.kind === "error" && (
          <div className="error-state" role="alert">
            <strong>{detail.failure.title}</strong>
            <p>{detail.failure.message}</p>
          </div>
        )}
        {approval && (
          <article className="approval-detail-body" aria-busy={actionPending}>
            <StatusLabels approval={approval} />
            <dl className="tool-result-grid approval-fields">
              <div><dt>Capability</dt><dd>{approval.tool.name}</dd></div>
              <div><dt>Agent</dt><dd>{approval.agent.name}</dd></div>
              <div><dt>Requester</dt><dd>{approval.requester.name}</dd></div>
              <div><dt>System</dt><dd>{formatValue(approval.arguments.system)}</dd></div>
              <div><dt>Access level</dt><dd>{formatValue(approval.arguments.access_level)}</dd></div>
              <div><dt>Duration</dt><dd>{approval.arguments.duration_days} days</dd></div>
              <div className="tool-result-wide">
                <dt>Business justification</dt>
                <dd className="literal-text">{approval.arguments.business_justification}</dd>
              </div>
              <div><dt>Requested</dt><dd>{formatTimestamp(approval.created_at)}</dd></div>
              <div><dt>Expires</dt><dd>{formatTimestamp(approval.expires_at)}</dd></div>
            </dl>

            {approval.decision && (
              <section className="approval-section" aria-label="Decision">
                <h3>Decision</h3>
                <p>
                  {approval.decision.decided_by
                    ? `${DECISION_LABELS[approval.decision_status]} by ${approval.decision.decided_by.name}`
                    : `${DECISION_LABELS[approval.decision_status]} by the system`}
                  {" · "}
                  {formatTimestamp(approval.decision.decided_at)}
                </p>
                {approval.decision.invalidation_reason && (
                  <p>{INVALIDATION_LABELS[approval.decision.invalidation_reason]} Submit a new request.</p>
                )}
                {approval.decision.note && (
                  <p className="literal-text">{approval.decision.note}</p>
                )}
              </section>
            )}

            {approval.execution && (
              <section className="approval-section" aria-label="Execution">
                <h3>Execution</h3>
                {approval.execution.result ? (
                  <p>
                    Mock IT access request {approval.execution.result.reference} recorded
                    {" · "}
                    {formatTimestamp(approval.execution.executed_at)}
                  </p>
                ) : (
                  <p>
                    The approved request could not be executed (adapter error). It will not be
                    retried automatically.
                  </p>
                )}
              </section>
            )}

            {canDecide && (
              <div className="approval-actions">
                <label htmlFor="approval-note">Note (optional)</label>
                <textarea
                  id="approval-note"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  rows={3}
                  maxLength={1001}
                  disabled={actionPending}
                />
                <div className="approval-action-buttons">
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void submitDecision("approve")}
                    disabled={actionPending}
                  >
                    {actionPending ? "Saving…" : "Approve"}
                  </button>
                  <button
                    type="button"
                    className="secondary-action-button"
                    onClick={() => void submitDecision("reject")}
                    disabled={actionPending}
                  >
                    Reject
                  </button>
                </div>
              </div>
            )}
          </article>
        )}

        {actionMessage && (
          <div
            className={actionMessage.tone === "error" ? "approval-message error-state" : "approval-message"}
            role={actionMessage.tone === "error" ? "alert" : "status"}
          >
            <strong>{actionMessage.title}</strong>
            <p>{actionMessage.message}</p>
          </div>
        )}
      </aside>
    </div>
  );
}
