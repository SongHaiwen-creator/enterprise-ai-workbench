"use client";

import { displayMessage, formatTimestamp, formatEnumLabel } from "@/utils/presentation";

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
  pending: "待审核",
  approved: "已批准",
  rejected: "已拒绝",
  cancelled: "已取消",
  expired: "已过期",
  invalidated: "已失效",
};

const EXECUTION_LABELS: Record<ApprovalExecutionStatus, string> = {
  not_started: "未执行",
  succeeded: "已执行",
  failed: "执行失败",
};

const INVALIDATION_LABELS = {
  requester_ineligible: "申请人已不再满足操作条件。",
  capability_unavailable: "智能体或工具已不可用。",
  configuration_drift: "提交申请后工具配置已发生变化。",
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
      title: "审批请求失败",
      message: "无法完成请求，请稍后重试。",
    };
  }
  const title =
    error.status === 403 ? "没有审批访问权限" :
    error.status === 404 ? "审批申请不存在" :
    error.status === 409 ? "审批状态已变化" :
    error.status === 422 ? "请检查审批意见" :
    error.status === 502 ? "执行失败" :
    error.status === 503 ? "审批服务暂不可用" :
    error.status === 0 ? "无法连接服务" :
    "审批请求失败";
  return { title, message: displayMessage(error.message, error.status) };
}



function StatusLabels({ approval }: { approval: ApprovalResponse }) {
  return (
    <span className="approval-status-labels">
      <span className={`approval-label decision-${approval.decision_status}`}>
        <span className="sr-only">审批决定：</span>
        {DECISION_LABELS[approval.decision_status]}
      </span>
      <span className={`approval-label execution-${approval.execution_status}`}>
        <span className="sr-only">执行状态：</span>
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
        title: "请检查审批意见",
        message: "审批意见不能超过 1,000 字。",
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
        title: decision === "approve" ? "批准决定已保存" : "拒绝决定已保存",
        message: "审批决定已保存，最新状态将从服务端更新。",
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
              <p className="section-kicker">人工审核</p>
              <h2 id="approvals-title">审批中心</h2>
              <p className="muted">
                {workspaceName} 中的敏感操作申请，在此等待有权限的审核者处理。
              </p>
            </div>
          </div>
          <div className="approval-scope" role="group" aria-label="审批列表">
            <button
              type="button"
              className={scope === "mine" ? "scope-button active" : "scope-button"}
              aria-pressed={scope === "mine"}
              onClick={() => changeScope("mine")}
              disabled={actionPending}
            >
              我的申请
            </button>
            {canReview && (
              <button
                type="button"
                className={scope === "review" ? "scope-button active" : "scope-button"}
                aria-pressed={scope === "review"}
                onClick={() => changeScope("review")}
                disabled={actionPending}
              >
                待我审核
              </button>
            )}
          </div>

          {list.kind === "loading" && (
            <p className="approval-list-state" role="status">正在加载审批列表…</p>
          )}
          {list.kind === "error" && (
            <div className="approval-list-state error-state" role="alert">
              <strong>{list.failure.title}</strong>
              <p>{list.failure.message}</p>
            </div>
          )}
          {list.kind === "loaded" && list.items.length === 0 && (
            <p className="approval-list-state">暂无审批申请。</p>
          )}
          {list.kind === "loaded" && list.items.length > 0 && (
            <ul className="approval-list" aria-label="审批中心">
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
            <p className="section-kicker">详情</p>
            <h2 id="approval-detail-title">审批详情</h2>
          </div>
        </div>

        {detail.kind === "none" && (
          <div className="sources-empty">
            <p>选择一条申请，查看申请内容和审批结果。</p>
          </div>
        )}
        {detail.kind === "loading" && <p role="status">正在加载申请详情…</p>}
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
              <div><dt>业务能力</dt><dd>{approval.tool.name}</dd></div>
              <div><dt>智能体</dt><dd>{approval.agent.name}</dd></div>
              <div><dt>申请人</dt><dd>{approval.requester.name}</dd></div>
              <div><dt>目标系统</dt><dd>{formatEnumLabel(approval.arguments.system)}</dd></div>
              <div><dt>访问级别</dt><dd>{formatEnumLabel(approval.arguments.access_level)}</dd></div>
              <div><dt>有效期限</dt><dd>{approval.arguments.duration_days} 天</dd></div>
              <div className="tool-result-wide">
                <dt>申请理由</dt>
                <dd className="literal-text">{approval.arguments.business_justification}</dd>
              </div>
              <div><dt>申请时间</dt><dd>{formatTimestamp(approval.created_at)}</dd></div>
              <div><dt>到期时间</dt><dd>{formatTimestamp(approval.expires_at)}</dd></div>
            </dl>

            {approval.decision && (
              <section className="approval-section" aria-label="审批决定">
                <h3>审批决定</h3>
                <p>
                  {approval.decision.decided_by
                    ? `${DECISION_LABELS[approval.decision_status]} · 审核者：${approval.decision.decided_by.name}`
                    : `${DECISION_LABELS[approval.decision_status]} · 系统处理`}
                  {" · "}
                  {formatTimestamp(approval.decision.decided_at)}
                </p>
                {approval.decision.invalidation_reason && (
                  <p>{INVALIDATION_LABELS[approval.decision.invalidation_reason]} 请提交新的申请。</p>
                )}
                {approval.decision.note && (
                  <p className="literal-text">{approval.decision.note}</p>
                )}
              </section>
            )}

            {approval.execution && (
              <section className="approval-section" aria-label="执行结果">
                <h3>执行结果</h3>
                {approval.execution.result ? (
                  <p>
                    模拟 IT 权限申请 {approval.execution.result.reference} 已记录
                    {" · "}
                    {formatTimestamp(approval.execution.executed_at)}
                  </p>
                ) : (
                  <p>申请已批准，但执行服务返回错误，操作未能完成。系统不会自动重试。</p>
                )}
              </section>
            )}

            {canDecide && (
              <div className="approval-actions">
                <label htmlFor="approval-note">审批意见（可选）</label>
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
                    {actionPending ? "正在保存…" : "批准"}
                  </button>
                  <button
                    type="button"
                    className="secondary-action-button"
                    onClick={() => void submitDecision("reject")}
                    disabled={actionPending}
                  >
                    拒绝
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
