"use client";

import Link from "next/link";

import { FormEvent, useRef, useState } from "react";

import { Approvals } from "@/app/components/approvals";
import { Assistant } from "@/app/components/assistant";
import { ExecutionLogs } from "@/app/components/execution-logs";
import { PlatformNavigation, type ProductArea } from "@/app/components/platform-navigation";
import { Icon } from "@/app/components/ui-icon";
import { EvaluationDatasets } from "@/app/components/evaluation-datasets";
import { BadCases } from "@/app/components/bad-cases";
import type { AgentsLoadFailure } from "@/app/components/assistant";
import { KnowledgeQA } from "@/app/components/knowledge-qa";
import { KnowledgeAdmin } from "@/app/components/knowledge-admin";
import type { KnowledgeBasesLoadFailure } from "@/app/components/knowledge-qa";

import {
  AgentSummary,
  ApiError,
  CurrentUser,
  KnowledgeBase,
  MembershipRole,
  MembershipStatus,
  Workspace,
  WorkspaceListItem,
  WorkspaceMember,
  createWorkspaceMember,
  getCurrentUser,
  getWorkspace,
  listAgents,
  listKnowledgeBases,
  listWorkspaceMembers,
  listWorkspaces,
  login,
  updateWorkspaceMember,
} from "@/utils/api";
import { displayMessage, formatEnumLabel, formatJoinedAt, initials } from "@/utils/presentation";

const ROLES: MembershipRole[] = [
  "employee",
  "knowledge_admin",
  "agent_admin",
  "system_admin",
];

const STATUSES: MembershipStatus[] = ["invited", "active", "disabled"];

type Notice = { tone: "success" | "error"; message: string } | null;


export default function Workbench() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceListItem[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [agentsPending, setAgentsPending] = useState(false);
  const [agentsError, setAgentsError] = useState<AgentsLoadFailure>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [knowledgeBasesError, setKnowledgeBasesError] =
    useState<KnowledgeBasesLoadFailure>(null);
  const [requestedProductArea, setProductArea] = useState<ProductArea>("assistant");
  const [qaPending, setQaPending] = useState(false);
  const [knowledgePending, setKnowledgePending] = useState(false);
  const [loginPending, setLoginPending] = useState(false);
  const [workspacePending, setWorkspacePending] = useState(false);
  const [memberPending, setMemberPending] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [newMemberId, setNewMemberId] = useState("");
  const [newMemberRole, setNewMemberRole] = useState<MembershipRole>("employee");
  const workspaceRequestGeneration = useRef(0);
  const contentShell = useRef<HTMLElement>(null);

  const selectedWorkspace =
    workspaces.find((item) => item.id === selectedWorkspaceId) ?? null;
  const isAdministrator = selectedWorkspace?.role === "system_admin";
  // Presentation only: the backend authorizes every execution log read.
  const canViewExecutionLogs =
    selectedWorkspace?.role === "system_admin" || selectedWorkspace?.role === "agent_admin";
  const canManageKnowledge =
    selectedWorkspace?.role === "system_admin" || selectedWorkspace?.role === "knowledge_admin";
  const productArea: ProductArea =
    ((requestedProductArea === "execution-logs" || requestedProductArea === "evaluation-datasets" || requestedProductArea === "bad-cases") && !canViewExecutionLogs) || (requestedProductArea === "knowledge-admin" && !canManageKnowledge)
      ? "workspace"
      : requestedProductArea;

  function clearSession(message?: string) {
    workspaceRequestGeneration.current += 1;
    setAccessToken(null);
    setCurrentUser(null);
    setWorkspaces([]);
    setSelectedWorkspaceId(null);
    setWorkspace(null);
    setMembers([]);
    setAgents([]);
    setAgentsPending(false);
    setAgentsError(null);
    setKnowledgeBases([]);
    setKnowledgeBasesError(null);
    setQaPending(false);
    setKnowledgePending(false);
    setPassword("");
    setNotice(null);
    setLoginError(message ?? null);
  }

  async function loadAgentsForWorkspace(
    workspaceId: string,
    token: string,
    requestGeneration: number,
  ) {
    setAgentsPending(true);
    setAgentsError(null);
    try {
      const agentResult = await listAgents(workspaceId, token);
      if (requestGeneration !== workspaceRequestGeneration.current) return;
      setAgents(agentResult);
    } catch (error) {
      if (requestGeneration !== workspaceRequestGeneration.current) return;
      if (error instanceof ApiError && error.status === 401) {
        clearSession("登录已过期，请重新登录。");
        return;
      }
      setAgentsError(
        error instanceof ApiError && error.status === 403
          ? {
              kind: "forbidden",
              message: "你没有访问当前空间智能体的权限。",
            }
          : {
              kind: "error",
              message:
                error instanceof ApiError
                  ? displayMessage(error.message, error.status)
                  : "无法加载当前空间的智能体。",
            },
      );
    } finally {
      if (requestGeneration === workspaceRequestGeneration.current) {
        setAgentsPending(false);
      }
    }
  }

  function handleApiError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.status === 401) {
      clearSession("登录已过期，请重新登录。");
      return;
    }

    setNotice({
      tone: "error",
      message: error instanceof ApiError ? displayMessage(error.message, error.status) : fallback,
    });
  }

  async function selectWorkspace(item: WorkspaceListItem, token: string) {
    const requestGeneration = ++workspaceRequestGeneration.current;
    setSelectedWorkspaceId(item.id);
    setWorkspace(null);
    setMembers([]);
    setAgents([]);
    setAgentsPending(true);
    setAgentsError(null);
    setKnowledgeBases([]);
    setKnowledgeBasesError(null);
    setNotice(null);
    setWorkspacePending(true);
    void loadAgentsForWorkspace(item.id, token, requestGeneration);

    try {
      const [workspaceResult, memberResult, knowledgeBaseResult] = await Promise.all([
        getWorkspace(item.id, token),
        item.role === "system_admin"
          ? listWorkspaceMembers(item.id, token)
          : Promise.resolve([]),
        listKnowledgeBases(item.id, token).then(
          (value) => ({ ok: true as const, value }),
          (error: unknown) => ({ ok: false as const, error }),
        ),
      ]);

      if (requestGeneration !== workspaceRequestGeneration.current) return;

      if (!knowledgeBaseResult.ok) {
        const error = knowledgeBaseResult.error;
        if (error instanceof ApiError && error.status === 401) {
          clearSession("登录已过期，请重新登录。");
          return;
        }

        setWorkspace(workspaceResult);
        setMembers(memberResult);
        setKnowledgeBasesError(
          error instanceof ApiError && error.status === 403
            ? {
                kind: "forbidden",
                message: "你没有访问当前空间知识库的权限。",
              }
            : {
                kind: "error",
                message:
                  error instanceof ApiError
                    ? displayMessage(error.message, error.status)
                    : "无法加载当前空间的知识库。",
              },
        );
        return;
      }

      setWorkspace(workspaceResult);
      setMembers(memberResult);
      setKnowledgeBases(knowledgeBaseResult.value);
    } catch (error) {
      if (requestGeneration !== workspaceRequestGeneration.current) return;

      if (error instanceof ApiError && error.status === 401) {
        clearSession("登录已过期，请重新登录。");
      } else {
        const message =
          error instanceof ApiError ? displayMessage(error.message, error.status) : "无法加载工作空间，请稍后重试。";
        setNotice({ tone: "error", message });
      }
    } finally {
      if (requestGeneration === workspaceRequestGeneration.current) {
        setWorkspacePending(false);
      }
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginPending(true);
    setLoginError(null);

    try {
      const session = await login(email, password);
      const [userResult, workspaceResult] = await Promise.all([
        getCurrentUser(session.access_token),
        listWorkspaces(session.access_token),
      ]);

      setAccessToken(session.access_token);
      setCurrentUser(userResult);
      setWorkspaces(workspaceResult);
      setPassword("");

      if (workspaceResult.length > 0) {
        await selectWorkspace(workspaceResult[0], session.access_token);
      }
    } catch (error) {
      clearSession();
      setLoginError(
        error instanceof ApiError ? displayMessage(error.message, error.status) : "登录失败，请检查账号和密码后重试。",
      );
    } finally {
      setLoginPending(false);
    }
  }

  async function refreshMembers(token: string, workspaceId: string) {
    const memberResult = await listWorkspaceMembers(workspaceId, token);
    setMembers(memberResult);
  }

  async function handleAddMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !selectedWorkspaceId) return;

    setMemberPending("new");
    setNotice(null);
    try {
      await createWorkspaceMember(
        selectedWorkspaceId,
        { user_id: newMemberId.trim(), role: newMemberRole },
        accessToken,
      );
      await refreshMembers(accessToken, selectedWorkspaceId);
      setNewMemberId("");
      setNewMemberRole("employee");
      setNotice({ tone: "success", message: "成员已添加，状态为待加入。" });
    } catch (error) {
      handleApiError(error, "无法添加成员，请检查用户 ID 后重试。");
    } finally {
      setMemberPending(null);
    }
  }

  async function handleMemberUpdate(
    member: WorkspaceMember,
    update: { role?: MembershipRole; status?: MembershipStatus },
  ) {
    if (!accessToken || !selectedWorkspaceId) return;

    setMemberPending(member.id);
    setNotice(null);
    try {
      await updateWorkspaceMember(selectedWorkspaceId, member.id, update, accessToken);
      await refreshMembers(accessToken, selectedWorkspaceId);
      setNotice({ tone: "success", message: `${member.name}的访问权限已更新。` });
    } catch (error) {
      handleApiError(error, "无法更新成员，请稍后重试。");
    } finally {
      setMemberPending(null);
    }
  }

  if (!accessToken || !currentUser) {
    return (
      <main className="login-shell">
        <section className="brand-panel" aria-labelledby="brand-title">
          <div className="brand-mark" aria-hidden="true">EA</div>
          <div>
            <p className="eyebrow">企业 AI 工作台</p>
            <h1 id="brand-title">让企业知识可问，业务操作可控。</h1>
            <p className="brand-summary">
              连接企业知识、业务查询与人工审批，让每一次 AI 操作都有依据、可追踪。
            </p>
          </div>
          <div className="trust-note">
            <span aria-hidden="true">●</span>
            独立工作空间 · 清晰的访问权限
          </div>
        </section>

        <section className="login-panel" aria-labelledby="login-title">
          <div className="login-card">
            <Link className="login-back" href="/">← 返回首页</Link>
            <p className="section-kicker">欢迎回来</p>
            <h2 id="login-title">登录企业 AI 工作台</h2>
            <p className="muted">使用管理员为你开通的账号登录。</p>

            <form className="stack-form" onSubmit={handleLogin}>
              <label htmlFor="email">工作邮箱</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />

              <label htmlFor="password">密码</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="请输入密码"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />

              {loginError && (
                <p className="form-message error-message" role="alert">
                  {loginError}
                </p>
              )}

              <button className="primary-button" type="submit" disabled={loginPending}>
                {loginPending ? "正在登录…" : "登录"}
              </button>
            </form>
            <p className="privacy-note">登录状态仅保留在当前页面，关闭或刷新后需重新登录。</p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="workspace-shell">
      <PlatformNavigation
        workspaces={workspaces} selectedId={selectedWorkspaceId} currentUser={currentUser}
        area={productArea} canManageOperations={canViewExecutionLogs} canManageKnowledge={canManageKnowledge} pending={qaPending || knowledgePending}
        onWorkspace={item => void selectWorkspace(item, accessToken)}
        onArea={area => { setProductArea(area); if (contentShell.current) contentShell.current.scrollTop = 0; }} onLogout={() => clearSession()}
      />

      <section className="content-shell" ref={contentShell} aria-label="功能内容">
        <header className="topbar">
          <div>
            <p className="section-kicker">
              {productArea === "assistant" ? "日常使用 / 智能助手" : productArea === "knowledge-qa" ? "日常使用 / 知识问答" : productArea === "knowledge-admin" ? "知识维护 / 知识管理" : productArea === "approvals" ? "日常使用 / 审批中心" : productArea === "execution-logs" ? "运营管理 / 执行日志" : productArea === "evaluation-datasets" ? "运营管理 / 评测数据集" : productArea === "bad-cases" ? "运营管理 / 问题案例" : "工作空间 / 空间与成员"}
            </p>
            <h1>{productArea === "assistant" ? "智能助手" : productArea === "knowledge-qa" ? "知识问答" : productArea === "knowledge-admin" ? "知识管理" : productArea === "approvals" ? "审批中心" : productArea === "execution-logs" ? "执行日志" : productArea === "evaluation-datasets" ? "评测数据集" : productArea === "bad-cases" ? "问题案例" : selectedWorkspace?.name ?? "工作空间"}</h1>
            {productArea !== "workspace" && selectedWorkspace && (
              <p className="topbar-context">{selectedWorkspace.name}</p>
            )}
          </div>
          {selectedWorkspace && (
            <div className="topbar-actions"><span className="role-badge">{formatEnumLabel(selectedWorkspace.role)}</span><Link href="/" className="topbar-home"><Icon name="home" />返回首页</Link></div>
          )}
        </header>

        <div className="content">
          {notice && (
            <p
              className={`notice ${notice.tone === "success" ? "success-notice" : "error-notice"}`}
              role={notice.tone === "error" ? "alert" : "status"}
            >
              {notice.message}
            </p>
          )}

          {workspaces.length === 0 ? (
            <section className="empty-state">
              <div className="empty-icon" aria-hidden="true">◇</div>
              <h2>暂无可访问的工作空间</h2>
              <p>
                你的账号暂无可访问的工作空间，请联系系统管理员开通访问权限。
              </p>
            </section>
          ) : workspacePending ? (
            <section className="loading-card" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              正在加载工作空间…
            </section>
          ) : workspace && selectedWorkspace && productArea === "assistant" ? (
            <Assistant
              key={workspace.id}
              workspaceId={workspace.id}
              workspaceName={workspace.name}
              agents={agents}
              agentsPending={agentsPending}
              agentsError={agentsError}
              knowledgeBases={knowledgeBases}
              knowledgeBasesError={knowledgeBasesError}
              accessToken={accessToken}
              onUnauthorized={() => clearSession("登录已过期，请重新登录。")}
              onPendingChange={setQaPending}
              onRetryAgents={() => void loadAgentsForWorkspace(
                workspace.id,
                accessToken,
                workspaceRequestGeneration.current,
              )}
            />
          ) : workspace && selectedWorkspace && productArea === "knowledge-admin" ? (
            <KnowledgeAdmin
              workspaceId={workspace.id} accessToken={accessToken} role={selectedWorkspace.role}
              onUnauthorized={() => clearSession("登录已过期，请重新登录。")}
              onPendingChange={setKnowledgePending}
              onBasesChange={((generation) => (items: KnowledgeBase[] | null) => {
                if (generation !== workspaceRequestGeneration.current) return;
                setKnowledgeBases(items ?? []);
                setKnowledgeBasesError(items ? null : { kind: "error", message: "知识库列表需要刷新，请进入知识管理刷新或重新选择工作空间。" });
              })(workspaceRequestGeneration.current)}
            />
          ) : workspace && selectedWorkspace && productArea === "knowledge-qa" ? (
            <KnowledgeQA
              key={workspace.id}
              workspaceId={workspace.id}
              workspaceName={workspace.name}
              knowledgeBases={knowledgeBases}
              knowledgeBasesPending={workspacePending}
              knowledgeBasesError={knowledgeBasesError}
              accessToken={accessToken}
              onUnauthorized={() => clearSession("登录已过期，请重新登录。")}
              onPendingChange={setQaPending}
            />
          ) : workspace && selectedWorkspace && productArea === "approvals" ? (
            <Approvals
              key={workspace.id}
              workspaceId={workspace.id}
              workspaceName={workspace.name}
              currentUserId={currentUser.id}
              canReview={isAdministrator}
              accessToken={accessToken}
              onUnauthorized={() => clearSession("登录已过期，请重新登录。")}
              onPendingChange={setQaPending}
            />
          ) : workspace && selectedWorkspace && productArea === "evaluation-datasets" ? (
            <EvaluationDatasets
              key={workspace.id}
              workspaceId={workspace.id}
              workspaceName={workspace.name}
              accessToken={accessToken}
              onUnauthorized={() => clearSession("登录已过期，请重新登录。")}
            />
          ) : workspace && selectedWorkspace && productArea === "bad-cases" ? (
            <BadCases workspaceId={workspace.id} accessToken={accessToken} onUnauthorized={() => clearSession("登录已过期，请重新登录。")} />
          ) : workspace && selectedWorkspace && productArea === "execution-logs" ? (
            <ExecutionLogs
              key={workspace.id}
              workspaceId={workspace.id}
              workspaceName={workspace.name}
              accessToken={accessToken}
              onUnauthorized={() => clearSession("登录已过期，请重新登录。")}
            />
          ) : workspace && selectedWorkspace ? (
            <>
              <section className="overview-grid" aria-label="工作空间概览">
                <article className="overview-card primary-overview">
                  <p className="section-kicker">工作空间</p>
                  <h2>{workspace.name}</h2>
                  <p className="workspace-slug">/{workspace.slug}</p>
                  <span className="status-pill active-status">
                    <span aria-hidden="true" />
                    {formatEnumLabel(workspace.status)}
                  </span>
                </article>
                <article className="overview-card">
                  <p className="section-kicker">你的角色</p>
                  <h2>{formatEnumLabel(selectedWorkspace.role)}</h2>
                  <p className="muted">
                    加入时间：{formatJoinedAt(selectedWorkspace.joined_at)}
                  </p>
                </article>
                <article className="overview-card">
                  <p className="section-kicker">成员数量</p>
                  <h2>{isAdministrator ? members.length : "—"}</h2>
                  <p className="muted">
                    {isAdministrator ? "管理员可查看成员列表" : "需系统管理员权限"}
                  </p>
                </article>
              </section>

              {isAdministrator ? (
                <section className="members-section" aria-labelledby="members-title">
                  <div className="section-heading">
                    <div>
                      <p className="section-kicker">成员与权限</p>
                      <h2 id="members-title">空间成员</h2>
                      <p className="muted">管理当前工作空间的成员角色与状态。</p>
                    </div>
                  </div>

                  <form className="add-member-form" onSubmit={handleAddMember}>
                    <div className="field-group grow-field">
                      <label htmlFor="new-member-id">已有用户 ID（UUID）</label>
                      <input
                        id="new-member-id"
                        value={newMemberId}
                        onChange={(event) => setNewMemberId(event.target.value)}
                        placeholder="00000000-0000-0000-0000-000000000000"
                        pattern="[0-9a-fA-F-]{36}"
                        required
                      />
                    </div>
                    <div className="field-group">
                      <label htmlFor="new-member-role">角色</label>
                      <select
                        id="new-member-role"
                        value={newMemberRole}
                        onChange={(event) => setNewMemberRole(event.target.value as MembershipRole)}
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>{formatEnumLabel(role)}</option>
                        ))}
                      </select>
                    </div>
                    <button className="primary-button compact-button" type="submit" disabled={memberPending === "new"}>
                      {memberPending === "new" ? "正在添加…" : "添加成员"}
                    </button>
                  </form>

                  <div className="member-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">成员</th>
                          <th scope="col">角色</th>
                          <th scope="col">状态</th>
                          <th scope="col">加入时间</th>
                        </tr>
                      </thead>
                      <tbody>
                        {members.map((member) => {
                          const isPending = memberPending === member.id;
                          return (
                            <tr key={member.id}>
                              <td>
                                <div className="member-identity">
                                  <span className="user-avatar" aria-hidden="true">{initials(member.name)}</span>
                                  <span>
                                    <strong>{member.name}</strong>
                                    <small>{member.email}</small>
                                  </span>
                                </div>
                              </td>
                              <td>
                                <label className="sr-only" htmlFor={`role-${member.id}`}>{member.name}的角色</label>
                                <select
                                  id={`role-${member.id}`}
                                  value={member.role}
                                  disabled={isPending}
                                  onChange={(event) => void handleMemberUpdate(member, { role: event.target.value as MembershipRole })}
                                >
                                  {ROLES.map((role) => (
                                    <option key={role} value={role}>{formatEnumLabel(role)}</option>
                                  ))}
                                </select>
                              </td>
                              <td>
                                <label className="sr-only" htmlFor={`status-${member.id}`}>{member.name}的状态</label>
                                <select
                                  id={`status-${member.id}`}
                                  className={`status-select status-${member.status}`}
                                  value={member.status}
                                  disabled={isPending}
                                  onChange={(event) => void handleMemberUpdate(member, { status: event.target.value as MembershipStatus })}
                                >
                                  {STATUSES.map((status) => (
                                    <option key={status} value={status}>{formatEnumLabel(status)}</option>
                                  ))}
                                </select>
                              </td>
                              <td className="joined-cell">{isPending ? "正在更新…" : formatJoinedAt(member.joined_at)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {members.length === 0 && (
                      <p className="table-empty">当前工作空间暂无成员。</p>
                    )}
                  </div>
                </section>
              ) : (
                <section className="permission-card">
                  <div aria-hidden="true">i</div>
                  <span>
                    <strong>成员管理需要管理员权限</strong>
                    <p>仅系统管理员可查看或修改空间成员。</p>
                  </span>
                </section>
              )}
            </>
          ) : (
            <section className="empty-state">
              <h2>工作空间暂不可用</h2>
              <p>请重新选择工作空间，或登录后重试。</p>
            </section>
          )}
        </div>
      </section>
    </main>
  );
}
