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
import { formatEnumLabel } from "@/utils/presentation";

export const EXECUTION_LOG_PAGE_SIZE = 50;

const OPERATION_LABELS: Record<ExecutionLogOperation, string> = {
  agent_route: "Agent request",
  knowledge_answer: "Knowledge answer",
  approval_decision: "Approval decision",
  approval_cancel: "Approval cancel",
};

const STATUS_LABELS: Record<ExecutionLogStatus, string> = {
  succeeded: "Succeeded",
  failed: "Failed",
};

const DETAIL_LABELS: Record<keyof ExecutionLogDetails, string> = {
  tool_not_executed_reason: "Not executed because",
  citation_count: "Citations",
  generation_model: "Model",
  prompt_version: "Prompt version",
  input_tokens: "Input tokens",
  output_tokens: "Output tokens",
  total_tokens: "Total tokens",
  decision: "Requested decision",
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
      title: "Execution logs unavailable",
      message: "We could not load execution logs. Try again in a moment.",
    };
  }
  const title =
    error.status === 403 ? "Execution log access denied" :
    error.status === 0 ? "Connection unavailable" :
    "Execution logs unavailable";
  return { title, message: error.message };
}

function formatTimestamp(value: string): string {
  return `${new Date(value).toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

function formatDetailValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "Not reported";
  return typeof value === "number" ? value.toLocaleString("en") : formatEnumLabel(value);
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
      <div><dt>Routing intent</dt><dd>{log.routing_intent ? formatEnumLabel(log.routing_intent) : "—"}</dd></div>
      <div><dt>HTTP status</dt><dd>{log.http_status}</dd></div>
      {log.outcome && log.error_category && (
        <div><dt>Outcome</dt><dd>{formatEnumLabel(log.outcome)}</dd></div>
      )}
      <div><dt>Knowledge base</dt><dd>{log.knowledge_base?.name ?? "—"}</dd></div>
      <div className="tool-result-wide"><dt>Approval</dt><dd>{log.approval_id ?? "—"}</dd></div>
      {detailEntries.map((key) => (
        <div key={key}>
          <dt>{DETAIL_LABELS[key]}</dt>
          <dd>{key === "generation_model" || key === "prompt_version"
            ? (log.details[key] ?? "Not reported")
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
          <p className="section-kicker">Traceability</p>
          <h2 id="execution-logs-title">Execution logs</h2>
          <p className="muted">
            AI operations in {workspaceName}: who ran them, through which Agent and Tool,
            the outcome, and how long they took. Request and answer content is never stored.
          </p>
        </div>
      </div>

      <div className="execution-log-filters">
        <label>
          <span>Operation</span>
          <select
            value={filters.operation ?? ""}
            onChange={(event) => changeFilter({
              operation: (event.target.value || undefined) as ExecutionLogOperation | undefined,
            })}
          >
            <option value="">All operations</option>
            {(Object.keys(OPERATION_LABELS) as ExecutionLogOperation[]).map((operation) => (
              <option key={operation} value={operation}>{OPERATION_LABELS[operation]}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Status</span>
          <select
            value={filters.status ?? ""}
            onChange={(event) => changeFilter({
              status: (event.target.value || undefined) as ExecutionLogStatus | undefined,
            })}
          >
            <option value="">All statuses</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
          </select>
        </label>
      </div>

      {list.kind === "loading" && (
        <p className="approval-list-state" role="status">Loading execution logs…</p>
      )}
      {list.kind === "error" && (
        <div className="approval-list-state error-state" role="alert">
          <strong>{list.failure.title}</strong>
          <p>{list.failure.message}</p>
        </div>
      )}
      {list.kind === "loaded" && list.items.length === 0 && (
        <p className="approval-list-state">No execution logs match these filters.</p>
      )}
      {list.kind === "loaded" && list.items.length > 0 && (
        <>
          <div className="execution-log-table-wrap">
            <table className="execution-log-table">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Operation</th>
                  <th scope="col">User</th>
                  <th scope="col">Agent</th>
                  <th scope="col">Tool</th>
                  <th scope="col">Status</th>
                  <th scope="col">Result</th>
                  <th scope="col" className="numeric">Latency</th>
                  <th scope="col"><span className="sr-only">Details</span></th>
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
                        <td className="numeric">{log.latency_ms.toLocaleString("en")} ms</td>
                        <td>
                          <button
                            type="button"
                            className="execution-log-toggle"
                            aria-expanded={expanded}
                            aria-controls={`execution-log-${log.id}`}
                            onClick={() => setExpandedId(expanded ? null : log.id)}
                          >
                            {expanded ? "Hide" : "Details"}
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
              {list.loadingMore ? "Loading…" : "Load more"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
