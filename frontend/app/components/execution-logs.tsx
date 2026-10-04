"use client";

import { Fragment, useEffect, useRef, useState } from "react";

import {
  ApiError,
  ExecutionLog,
  ExecutionLogDetails,
  ExecutionLogFilters,
  ExecutionLogOperation,
  ExecutionLogStatus,
  listExecutionLogs,
} from "@/utils/api";
import { displayMessage, formatEnumLabel, formatTimestamp } from "@/utils/presentation";

export const EXECUTION_LOG_PAGE_SIZE = 50;

const OPERATION_LABELS: Record<ExecutionLogOperation, string> = {
  agent_route: "助手请求",
  knowledge_answer: "知识回答",
  approval_decision: "审批决定",
  approval_cancel: "取消申请",
};

const STATUS_LABELS: Record<ExecutionLogStatus, string> = {
  succeeded: "成功",
  failed: "失败",
};

const DETAIL_LABELS: Record<keyof ExecutionLogDetails, string> = {
  tool_not_executed_reason: "未执行原因",
  citation_count: "引用来源",
  generation_model: "模型",
  prompt_version: "提示词版本",
  input_tokens: "输入令牌数",
  output_tokens: "输出令牌数",
  total_tokens: "总令牌数",
  decision: "提交的审批决定",
};

type Failure = { title: string; message: string };

type ListState =
  | { kind: "loading" }
  | { kind: "loaded"; items: ExecutionLog[]; hasMore: boolean; loadingMore: boolean }
  | { kind: "error"; failure: Failure };

interface ExecutionLogsProps {
  workspaceId: string;
  workspaceName: string;
  accessToken: string;
  onUnauthorized: () => void;
}

function failureFor(error: unknown): Failure {
  if (!(error instanceof ApiError)) {
    return {
      title: "执行日志暂不可用",
      message: "无法加载执行日志，请稍后重试。",
    };
  }
  const title =
    error.status === 403 ? "没有执行日志访问权限" :
    error.status === 0 ? "无法连接服务" :
    "执行日志暂不可用";
  return { title, message: displayMessage(error.message, error.status) };
}


function formatDetailValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "未记录";
  return typeof value === "number" ? value.toLocaleString("zh-CN") : formatEnumLabel(value);
}

function resultLabel(log: ExecutionLog): string {
  if (log.error_category) return formatEnumLabel(log.error_category);
  return log.outcome ? formatEnumLabel(log.outcome) : "—";
}

function LogDetails({ log }: { log: ExecutionLog }) {
  const detailEntries = (Object.keys(DETAIL_LABELS) as (keyof ExecutionLogDetails)[])
    .filter((key) => key in log.details);
  return (
    <dl className="tool-result-grid execution-log-fields">
      <div><dt>请求类型</dt><dd>{log.routing_intent ? formatEnumLabel(log.routing_intent) : "—"}</dd></div>
      <div><dt>HTTP 状态码</dt><dd>{log.http_status}</dd></div>
      {log.outcome && log.error_category && (
        <div><dt>处理结果</dt><dd>{formatEnumLabel(log.outcome)}</dd></div>
      )}
      <div><dt>知识库</dt><dd>{log.knowledge_base?.name ?? "—"}</dd></div>
      <div className="tool-result-wide"><dt>审批详情</dt><dd>{log.approval_id ?? "—"}</dd></div>
      {detailEntries.map((key) => (
        <div key={key}>
          <dt>{DETAIL_LABELS[key]}</dt>
          <dd>{key === "generation_model" || key === "prompt_version"
            ? (log.details[key] ?? "未记录")
            : formatDetailValue(log.details[key])}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ExecutionLogs({
  workspaceId,
  workspaceName,
  accessToken,
  onUnauthorized,
}: ExecutionLogsProps) {
  const [filters, setFilters] = useState<ExecutionLogFilters>({});
  const [list, setList] = useState<ListState>({ kind: "loading" });
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const generation = useRef(0);

  async function fetchPage(
    nextFilters: ExecutionLogFilters,
    offset: number,
    previous: ExecutionLog[],
    requestGeneration: number,
  ) {
    try {
      const response = await listExecutionLogs(
        workspaceId, nextFilters, EXECUTION_LOG_PAGE_SIZE, offset, accessToken,
      );
      if (requestGeneration !== generation.current) return;
      setList({
        kind: "loaded",
        items: [...previous, ...response.items],
        hasMore: response.items.length === EXECUTION_LOG_PAGE_SIZE,
        loadingMore: false,
      });
    } catch (error) {
      if (requestGeneration !== generation.current) return;
      if (error instanceof ApiError && error.status === 401) {
        onUnauthorized();
        return;
      }
      setList({ kind: "error", failure: failureFor(error) });
    }
  }

  function reload(nextFilters: ExecutionLogFilters) {
    const requestGeneration = ++generation.current;
    setList({ kind: "loading" });
    setExpandedId(null);
    void fetchPage(nextFilters, 0, [], requestGeneration);
  }

  useEffect(() => {
    // The initial state is already "loading"; load once per mounted Workspace.
    void fetchPage({}, 0, [], ++generation.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function changeFilter(update: ExecutionLogFilters) {
    const nextFilters = { ...filters, ...update };
    setFilters(nextFilters);
    reload(nextFilters);
  }

  function loadMore() {
    if (list.kind !== "loaded" || list.loadingMore) return;
    const requestGeneration = ++generation.current;
    setList({ ...list, loadingMore: true });
    void fetchPage(filters, list.items.length, list.items, requestGeneration);
  }

  return (
    <section className="qa-context-card execution-logs" aria-labelledby="execution-logs-title">
      <div className="qa-heading-row">
        <div>
          <p className="section-kicker">执行追踪</p>
          <h2 id="execution-logs-title">执行日志</h2>
          <p className="muted">
            AI operations in {workspaceName}: who ran them, through which Agent and Tool,
            the outcome, and how long they took. Request and answer content is never stored.
          </p>
        </div>
      </div>

      <div className="execution-log-filters">
        <label>
          <span>操作类型</span>
          <select
            value={filters.operation ?? ""}
            onChange={(event) => changeFilter({
              operation: (event.target.value || undefined) as ExecutionLogOperation | undefined,
            })}
          >
            <option value="">全部操作</option>
            {(Object.keys(OPERATION_LABELS) as ExecutionLogOperation[]).map((operation) => (
              <option key={operation} value={operation}>{OPERATION_LABELS[operation]}</option>
            ))}
          </select>
        </label>
        <label>
          <span>状态</span>
          <select
            value={filters.status ?? ""}
            onChange={(event) => changeFilter({
              status: (event.target.value || undefined) as ExecutionLogStatus | undefined,
            })}
          >
            <option value="">全部状态</option>
            <option value="succeeded">成功</option>
            <option value="failed">失败</option>
          </select>
        </label>
      </div>

      {list.kind === "loading" && (
        <p className="approval-list-state" role="status">正在加载执行日志…</p>
      )}
      {list.kind === "error" && (
        <div className="approval-list-state error-state" role="alert">
          <strong>{list.failure.title}</strong>
          <p>{list.failure.message}</p>
        </div>
      )}
      {list.kind === "loaded" && list.items.length === 0 && (
        <p className="approval-list-state">暂无符合筛选条件的执行日志。</p>
      )}
      {list.kind === "loaded" && list.items.length > 0 && (
        <>
          <div className="execution-log-table-wrap">
            <table className="execution-log-table">
              <thead>
                <tr>
                  <th scope="col">时间</th>
                  <th scope="col">操作类型</th>
                  <th scope="col">用户</th>
                  <th scope="col">智能体</th>
                  <th scope="col">工具</th>
                  <th scope="col">状态</th>
                  <th scope="col">结果</th>
                  <th scope="col" className="numeric">耗时</th>
                  <th scope="col"><span className="sr-only">详情</span></th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((log) => {
                  const expanded = expandedId === log.id;
                  return (
                    <Fragment key={log.id}>
                      <tr>
                        <td>{formatTimestamp(log.created_at)}</td>
                        <td>{OPERATION_LABELS[log.operation]}</td>
                        <td>{log.user.name}</td>
                        <td>{log.agent?.name ?? "—"}</td>
                        <td>{log.tool?.name ?? "—"}</td>
                        <td>
                          <span className={`approval-label log-status-${log.status}`}>
                            {STATUS_LABELS[log.status]}
                          </span>
                        </td>
                        <td>{resultLabel(log)}</td>
                        <td className="numeric">{log.latency_ms.toLocaleString("zh-CN")} 毫秒</td>
                        <td>
                          <button
                            type="button"
                            className="execution-log-toggle"
                            aria-expanded={expanded}
                            aria-controls={`execution-log-${log.id}`}
                            onClick={() => setExpandedId(expanded ? null : log.id)}
                          >
                            {expanded ? "收起" : "详情"}
                          </button>
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="execution-log-detail-row" id={`execution-log-${log.id}`}>
                          <td colSpan={9}><LogDetails log={log} /></td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          {list.hasMore && (
            <button
              type="button"
              className="execution-log-more"
              onClick={loadMore}
              disabled={list.loadingMore}
            >
              {list.loadingMore ? "正在加载…" : "加载更多"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
